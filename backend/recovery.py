"""Startup recovery sweep for messages stranded by a process restart.

The webhook acks Meta with a 200 immediately and then processes the message in a FastAPI
background task (see webhook.py). That is the right shape — Meta's retry logic only cares
about the ack, and holding the connection open across a multi-second Gemini call would
invite timeouts and duplicate deliveries — but it leaves one hole nothing else covers: if
the process dies between the ack and the reply (a deploy, an OOM, a platform restart), the
message is gone. Meta will not resend something it has already been told was received, and
no exception was ever raised for process_payload's per-message try/except to catch.

Every other silent-failure path in this system has been closed by making sure Hoshang finds
out (send_processing_failure_email, send_undelivered_reply_email, notifying on unqualified
leads). This closes the last one the same way rather than by building a durable queue: on
startup, look for conversations whose last word was the lead's, and tell him, so he can
follow up personally instead of the lead simply never hearing back.

A real queue (or persisting the raw payload before acking and replaying it) is the complete
fix and is deliberately deferred — it is a meaningful piece of infrastructure for a failure
that only happens on restart, and an alert recovers the lead just as well.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from db.db import SessionLocal
from db.models import Conversation, Lead, Message
from integrations.email_service import send_stranded_messages_email

logger = logging.getLogger("leadpilot.recovery")

# Only look at the recent past. An older unanswered inbound is far more likely to be a lead
# who simply sent a last message after the funnel closed (perfectly normal, and deliberately
# unanswered once human_takeover is set) than a genuine restart casualty.
STRANDED_LOOKBACK_HOURS = 24


def find_stranded_conversations(db, now: datetime | None = None) -> list[dict]:
    """Conversations whose most recent message is inbound, inside the lookback window.

    human_takeover conversations are excluded: the bot is *supposed* to be silent there, so
    an unanswered inbound is expected rather than a fault.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=STRANDED_LOOKBACK_HOURS)

    latest_message_id = (
        db.query(func.max(Message.id))
        .filter(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )

    rows = (
        db.query(Message, Lead)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(Lead, Conversation.lead_id == Lead.id)
        .filter(Message.id == latest_message_id)
        .filter(Message.direction == "in")
        .filter(Message.created_at >= cutoff)
        .filter(Lead.human_takeover.is_(False))
        .all()
    )

    return [
        {
            "wa_number": lead.wa_number,
            "text": message.text,
            "received_at": message.created_at,
        }
        for message, lead in rows
    ]


def sweep_stranded_messages() -> int:
    """Run once at startup. Returns how many stranded conversations were reported."""
    db = SessionLocal()
    try:
        stranded = find_stranded_conversations(db)
    except Exception:
        # Recovery is a safety net, never a reason the service fails to boot.
        logger.exception("Stranded-message sweep failed")
        return 0
    finally:
        db.close()

    if not stranded:
        logger.info("Startup sweep: no stranded messages")
        return 0

    logger.warning("Startup sweep found %d conversation(s) awaiting a reply", len(stranded))
    try:
        send_stranded_messages_email(stranded)
    except Exception:
        logger.exception("Failed to send stranded-message alert")
    return len(stranded)
