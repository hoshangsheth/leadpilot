import asyncio
import hashlib
import hmac
import logging

from fastapi import APIRouter, Request, Response, BackgroundTasks
from sqlalchemy.exc import IntegrityError

import config
from db import SessionLocal
from models import Lead, Conversation, Message
from whatsapp_client import send_message
from conversation_engine import process_message

router = APIRouter()
logger = logging.getLogger("leadpilot.webhook")


@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == config.VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()

    if not _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256", "")):
        return Response(status_code=403)

    payload = await request.json()
    background_tasks.add_task(_process_payload, payload)
    return {}


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(config.APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def _process_payload(payload: dict):
    """Runs after the 200 ack — Meta's retry behavior only cares about the ack (Section 9a,
    input vs. system failure classification), not this outcome."""
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    _handle_message(msg)
    except Exception:
        logger.exception("Unhandled failure processing webhook payload")


def _handle_message(msg: dict):
    wa_message_id = msg["id"]
    wa_number = msg["from"]
    text = msg.get("text", {}).get("body", "")
    msg_type = msg.get("type")

    if msg_type != "text":
        logger.info("Ignoring unsupported message type=%s from=%s", msg_type, wa_number)
        # Real "text only for now" redirect reply is a Stage 5 hardening item.
        return

    if not text.strip():
        logger.info("Ignoring empty message body from=%s", wa_number)
        return

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter_by(wa_number=wa_number).first()
        if lead is None:
            lead = Lead(wa_number=wa_number)
            db.add(lead)
            db.flush()

        conversation = (
            db.query(Conversation)
            .filter_by(lead_id=lead.id)
            .order_by(Conversation.id.desc())
            .first()
        )
        if conversation is None:
            conversation = Conversation(lead_id=lead.id)
            db.add(conversation)
            db.flush()

        if lead.human_takeover:
            logger.info("Lead %s has human_takeover set — bot stays silent", lead.id)
            message = Message(
                conversation_id=conversation.id, wa_message_id=wa_message_id, direction="in", text=text
            )
            db.add(message)
            db.commit()
            return

        message = Message(
            conversation_id=conversation.id,
            wa_message_id=wa_message_id,
            direction="in",
            text=text,
        )
        db.add(message)
        db.commit()

        # Read everything needed while the session is still open — avoids the detached-instance
        # bug hit in Stage 1 (accessing ORM attributes after db.close()).
        last_inbound_at = conversation.last_inbound_at
        current_state = conversation.state
        collected_fields = dict(conversation.collected_fields or {})
        history = [
            m.text
            for m in db.query(Message)
            .filter_by(conversation_id=conversation.id)
            .order_by(Message.id.desc())
            .limit(6)
            .all()
        ][::-1]
        conversation_id = conversation.id
    except IntegrityError:
        # Duplicate wa_message_id — Meta retried delivery. Already processed, safe to skip.
        db.rollback()
        logger.info("Duplicate message_id=%s, skipping", wa_message_id)
        return
    finally:
        db.close()

    outcome = asyncio.run(process_message(current_state, collected_fields, history, text))

    if outcome is None:
        # Dependency failure (Section 9a) — Gemini unreachable/malformed after retry.
        # Day 5 hardening adds a proper filler-message + retry-queue; log for now.
        logger.error("Gemini call failed for conversation_id=%s, no reply sent", conversation_id)
        return

    reply_text, new_state, updated_fields = outcome

    db = SessionLocal()
    try:
        conversation = db.get(Conversation, conversation_id)
        conversation.state = new_state
        conversation.collected_fields = updated_fields
        db.add(
            Message(
                conversation_id=conversation_id,
                wa_message_id=f"{wa_message_id}-reply",
                direction="out",
                text=reply_text,
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        asyncio.run(send_message(to=wa_number, text=reply_text, last_inbound_at=last_inbound_at))
    except Exception:
        logger.exception("Failed to send reply to %s", wa_number)
