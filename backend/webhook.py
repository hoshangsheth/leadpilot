import hashlib
import hmac
import logging

from fastapi import APIRouter, Request, Response, BackgroundTasks
from sqlalchemy.exc import IntegrityError

import config
from db import SessionLocal
from models import Lead, Conversation, Message
from whatsapp_client import send_message

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
        # Stage 2+ will send the "text only for now" redirect reply; stub reply covers this in Stage 1.
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

        message = Message(
            conversation_id=conversation.id,
            wa_message_id=wa_message_id,
            direction="in",
            text=text,
        )
        db.add(message)
        db.commit()
        last_inbound_at = conversation.last_inbound_at  # read while session is still open
    except IntegrityError:
        # Duplicate wa_message_id — Meta retried delivery. Already processed, safe to skip.
        db.rollback()
        logger.info("Duplicate message_id=%s, skipping", wa_message_id)
        return
    finally:
        db.close()

    _send_stub_reply(wa_number, last_inbound_at)


def _send_stub_reply(wa_number: str, last_inbound_at):
    import asyncio

    try:
        asyncio.run(
            send_message(
                to=wa_number,
                text="Thanks for your message — LeadPilot is still being built, real replies coming soon.",
                last_inbound_at=last_inbound_at,
            )
        )
    except Exception:
        logger.exception("Failed to send stub reply to %s", wa_number)
