"""Business orchestration for an inbound WhatsApp message: persists it, runs it through the
conversation engine, scores/qualifies the lead, and triggers the outbound reply plus any
qualified-lead email. Kept separate from webhook.py so that file stays a thin HTTP transport
layer (signature verification, ack) with no persistence or orchestration logic of its own.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

from sqlalchemy import text as sql_text

import config
from db.db import SessionLocal
from db.models import Lead, Conversation, Message, Qualification
from integrations.whatsapp_client import send_message
from conversation_engine import process_message, MAX_MESSAGES, ensure_bot_disclosure
from scoring import score_lead
from integrations.email_service import send_qualified_lead_email, send_handoff_email
from observability.logger import log_transition
from routing import detect_bypass, detect_source, BYPASS_REPLIES

logger = logging.getLogger("leadpilot.webhook")

WELCOME_BACK_GAP_HOURS = 6
MAX_TEXT_LENGTH = 2000  # a legitimate WhatsApp reply is nowhere near this; bounds worst-case
# Gemini token cost per message and blocks unbounded text as a cheap abuse/DoS-via-cost vector.


def process_payload(payload: dict):
    """Runs after the 200 ack — Meta's retry behavior only cares about the ack (Section 9a,
    input vs. system failure classification), not this outcome."""
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    handle_message(msg)
    except Exception:
        logger.exception("Unhandled failure processing webhook payload")


def handle_message(msg: dict):
    """Persists one inbound WhatsApp message, advances the conversation state machine, and
    sends the reply (plus qualification email, if this turn just qualified the lead).

    Holds a Postgres advisory lock, keyed by wa_number, for the ENTIRE duration of processing
    — including the Gemini call — so two near-simultaneous messages from the same lead (a very
    common real pattern: "Hi" immediately followed by their actual question) can never race on
    creating the Lead/Conversation row or on the final state write. The lock only ever blocks
    messages from the SAME lead; unrelated leads process fully in parallel.
    """
    wa_message_id = msg["id"]
    wa_number = msg["from"]
    body_text = msg.get("text", {}).get("body", "")
    msg_type = msg.get("type")

    if msg_type != "text":
        logger.info("Ignoring unsupported message type=%s from=%s", msg_type, wa_number)
        # Real "text only for now" redirect reply is a Stage 5 hardening item.
        return

    if not body_text.strip():
        logger.info("Ignoring empty message body from=%s", wa_number)
        return

    if len(body_text) > MAX_TEXT_LENGTH:
        logger.warning("Truncating oversized message (%d chars) from=%s", len(body_text), wa_number)
        body_text = body_text[:MAX_TEXT_LENGTH]

    db = SessionLocal()
    try:
        db.execute(sql_text("SELECT pg_advisory_xact_lock(hashtext(:wa_number))"), {"wa_number": wa_number})

        if db.query(Message).filter_by(wa_message_id=wa_message_id).first() is not None:
            # Duplicate delivery of the same message (Meta retry). Checked up front, before
            # any real work or Gemini spend, now that the lock rules out this also being a
            # genuine concurrent race on the insert itself.
            db.rollback()
            logger.info("Duplicate message_id=%s, skipping", wa_message_id)
            return

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
            db.add(Message(
                conversation_id=conversation.id, wa_message_id=wa_message_id, direction="in", text=body_text
            ))
            db.commit()
            return

        # Capture the PREVIOUS inbound time before overwriting — used for the welcome-back
        # gap check. last_inbound_at was never actually being refreshed after conversation
        # creation until an earlier fix; kept as an explicit local, not re-read post-commit.
        previous_inbound_at = conversation.last_inbound_at
        now = datetime.now(timezone.utc)
        if previous_inbound_at.tzinfo is None:
            previous_inbound_at = previous_inbound_at.replace(tzinfo=timezone.utc)
        message_count_before_this = db.query(Message).filter_by(conversation_id=conversation.id).count()
        is_returning_after_gap = message_count_before_this > 0 and (
            now - previous_inbound_at
        ) > timedelta(hours=WELCOME_BACK_GAP_HOURS)

        db.add(Message(
            conversation_id=conversation.id, wa_message_id=wa_message_id, direction="in", text=body_text
        ))
        conversation.last_inbound_at = now

        current_state = conversation.state
        collected_fields = dict(conversation.collected_fields or {})

        # Attribution, read off the opening message rather than asked for. The site pre-fills
        # a different message per entry point, so the source is already in the text — see
        # routing.detect_source. Recorded once, on the first message only.
        if message_count_before_this == 0 and "lead_source" not in collected_fields:
            collected_fields["lead_source"] = detect_source(body_text)
            conversation.collected_fields = collected_fields

        # Warm contacts and explicit human requests never enter the funnel. Checked before the
        # Gemini call, so a referral costs nothing and, more importantly, is never asked for
        # their budget by a robot. See routing.detect_bypass.
        bypass = detect_bypass(body_text, message_count_before_this + 1)
        if bypass:
            reply_text = BYPASS_REPLIES[bypass]
            lead.human_takeover = True
            db.add(Message(
                conversation_id=conversation.id,
                wa_message_id=f"{wa_message_id}-reply",
                direction="out",
                text=reply_text,
            ))
            db.commit()
            logger.info("Lead %s bypassed funnel (%s) — handed to Hoshang", lead.id, bypass)
            send_handoff_email(wa_number, bypass, body_text, collected_fields.get("lead_source", "Unknown"))
            _send_reply(wa_number, reply_text, now)
            return
        history = [
            m.text
            for m in db.query(Message)
            .filter_by(conversation_id=conversation.id)
            .order_by(Message.id.desc())
            .limit(6)
            .all()
        ][::-1]
        lead_id = lead.id
        message_count = message_count_before_this + 1

        # Message cap — bounds worst-case Gemini spend per lead and forces a clean handoff
        # instead of an endless (and costly) back-and-forth. See blueprint Section 10.
        if message_count >= MAX_MESSAGES and current_state != "qualification_decision":
            reply_text, result = _apply_force_handoff(db, conversation, collected_fields)
            db.commit()
            log_transition(lead_id, current_state, "qualification_decision", None, "message_cap_forced")
            if result["qualified"]:
                send_qualified_lead_email(wa_number, collected_fields, result)
            _send_reply(wa_number, reply_text, now)
            return

        t0 = time.monotonic()
        outcome = asyncio.run(process_message(current_state, collected_fields, history, body_text))
        gemini_ms = int((time.monotonic() - t0) * 1000)

        if outcome is None:
            # Dependency failure (Section 9a) — Gemini unreachable/malformed after retry. No
            # reply is sent this turn; still commit the inbound message + last_inbound_at
            # update so the lock releases cleanly and the next attempt sees accurate history.
            db.commit()
            logger.error("Gemini call failed for conversation_id=%s, no reply sent", conversation.id)
            log_transition(lead_id, current_state, current_state, gemini_ms, "gemini_failed")
            return

        reply_text, new_state, updated_fields = outcome
        just_qualified = new_state == "qualification_decision" and current_state != "qualification_decision"
        should_email = False
        result = None

        # Enforced in code, not left to the prompt — see ensure_bot_disclosure. Applied to the
        # first outbound message of a conversation only; repeating it later would be noise.
        if message_count_before_this == 0:
            reply_text = ensure_bot_disclosure(reply_text)

        if is_returning_after_gap and current_state != "qualification_decision":
            reply_text = f"Welcome back! {reply_text}"

        conversation.state = new_state
        conversation.collected_fields = updated_fields

        if just_qualified:
            result = score_lead(updated_fields)
            _upsert_qualification(db, conversation.id, result)
            logger.info(
                "Conversation %s reached qualification_decision: score=%s qualified=%s",
                conversation.id, result["score"], result["qualified"],
            )
            # The conversational funnel is done either way — stop future auto-replies so a
            # disqualified lead messaging again doesn't trigger further (paid) Gemini calls.
            conversation.lead.human_takeover = True
            if result["qualified"]:
                # Calendly link is injected deterministically, never model-generated —
                # a hallucinated/malformed URL in a real lead's WhatsApp is not acceptable.
                reply_text = f"{reply_text}\n\nFeel free to grab a slot directly: {config.CALENDLY_LINK}"
                should_email = True

        db.add(Message(
            conversation_id=conversation.id,
            wa_message_id=f"{wa_message_id}-reply",
            direction="out",
            text=reply_text,
        ))
        db.commit()
    finally:
        db.close()

    if should_email:
        send_qualified_lead_email(wa_number, updated_fields, result)

    send_outcome = _send_reply(wa_number, reply_text, now)
    log_transition(lead_id, current_state, new_state, gemini_ms, send_outcome)


def _send_reply(wa_number: str, reply_text: str, last_inbound_at) -> str:
    """Sends the WhatsApp reply after the DB transaction (and advisory lock) has already
    released — no reason to hold either open for a network call that doesn't touch the DB."""
    try:
        asyncio.run(send_message(to=wa_number, text=reply_text, last_inbound_at=last_inbound_at))
        return "sent"
    except Exception:
        logger.exception("Failed to send reply to %s", wa_number)
        return "send_failed"


def _upsert_qualification(db, conversation_id: int, result: dict):
    """conversation_id is unique on qualifications — a conversation reaching qualification
    twice (e.g. re-triggered by a message-cap forced handoff after already qualifying, or a
    replayed/retried message) must update the existing row, not insert a duplicate and crash."""
    existing = db.query(Qualification).filter_by(conversation_id=conversation_id).first()
    if existing:
        existing.score = result["score"]
        existing.breakdown = result["breakdown"]
        existing.qualified = result["qualified"]
    else:
        db.add(
            Qualification(
                conversation_id=conversation_id,
                score=result["score"],
                breakdown=result["breakdown"],
                qualified=result["qualified"],
            )
        )


def _apply_force_handoff(db, conversation: Conversation, collected_fields: dict) -> tuple[str, dict]:
    """Message cap hit — no more Gemini calls for this conversation. Deterministic reply,
    force to qualification_decision with an 'incomplete' flag, hand off to Hoshang directly.
    See full blueprint Section 10/11 — forced handoff with partial data flagged incomplete.

    Still qualifies (and the caller still emails) if the fields actually collected genuinely
    score as qualified — "incomplete" only means additional_notes wasn't reached, it doesn't
    mean the real scoring fields are missing. A lead who answered everything real and just got
    cut off one exchange short still deserves the notification and the link.

    Mutates `conversation` in place on the caller's already-open session/transaction rather
    than opening its own — this used to run in a separate SessionLocal(), which meant it
    wasn't covered by the same advisory lock as the rest of this turn's processing.
    """
    reply_text = (
        "Thanks so much for the detail so far. I want to make sure Hoshang picks this up "
        "directly rather than keep you going back and forth here. He'll follow up with you shortly."
    )
    collected_fields = {**collected_fields, "incomplete": "true"}
    result = score_lead(collected_fields)

    if result["qualified"]:
        reply_text = f"{reply_text}\n\nFeel free to grab a slot directly: {config.CALENDLY_LINK}"

    conversation.state = "qualification_decision"
    conversation.collected_fields = collected_fields
    conversation.lead.human_takeover = True

    db.add(Message(
        conversation_id=conversation.id,
        wa_message_id=f"forced-handoff-{conversation.id}-{int(datetime.now(timezone.utc).timestamp())}",
        direction="out",
        text=reply_text,
    ))
    _upsert_qualification(db, conversation.id, result)
    logger.warning(
        "Conversation %s hit message cap (%d), forced handoff — score=%s qualified=%s",
        conversation.id, MAX_MESSAGES, result["score"], result["qualified"],
    )
    return reply_text, result
