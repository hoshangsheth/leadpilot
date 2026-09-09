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
from conversation_engine import (
    process_message, MAX_MESSAGES,
    ensure_opening_frame, ensure_closing_thanks,
)
from scoring import score_lead
from integrations.email_service import (
    send_lead_notification_email,
    send_handoff_email,
    send_bypass_name_followup_email,
    send_processing_failure_email,
    send_undelivered_reply_email,
)
from integrations.sheets_client import append_qualified_lead
from observability.logger import log_transition
from routing import (
    detect_bypass, detect_source, BYPASS_REPLIES,
    is_identity_question, IDENTITY_QUESTION_REPLY,
    is_contact_info_request, CONTACT_INFO_REPLY,
)

logger = logging.getLogger("leadpilot.webhook")

WELCOME_BACK_GAP_HOURS = 6
MAX_TEXT_LENGTH = 2000  # a legitimate WhatsApp reply is nowhere near this; bounds worst-case
# Gemini token cost per message and blocks unbounded text as a cheap abuse/DoS-via-cost vector.

# Max CHATTER rounds — small talk, filler, repeats — before "anything else?" stops being
# re-asked and the conversation closes deterministically. Rounds where the lead asked a
# genuine question do NOT count (see states/additional_notes.py notes_turn_kind): a serious
# buyer asking about cancellation terms, ownership, or running costs is doing exactly what
# this state exists for, and cutting them off for it costs a real lead. Raised 3 -> 6 on
# 2026-09-08 alongside that change, since the old limit was low enough that three ordinary
# questions could reach it on their own.
NOTES_RETRY_LIMIT = 6
# _notes_retry_count is internal bookkeeping, not a real lead fact — deliberately never added
# to conversation_engine.ALL_FIELD_KEYS (Gemini is never told this key exists and can't extract
# or corrupt it) and never read by email_service (it isn't in that file's field allowlist), so
# it can't leak into anything user- or Hoshang-facing by accident.


def process_payload(payload: dict):
    """Runs after the 200 ack — Meta's retry behavior only cares about the ack (Section 9a,
    input vs. system failure classification), not this outcome.

    Each message is handled and guarded independently: a payload can carry more than one
    message, and until 2026-09-07 a single unhandled exception (e.g. a DB connection blip)
    aborted the whole payload, silently dropping every other message in it too, with no reply
    to any of them and no alert to Hoshang. Now one message's failure can't take the rest down,
    and every failure — not just a caught one — triggers an alert with the actual wa_number so
    the lead can be followed up with personally instead of vanishing into the Render logs.
    """
    entries = payload.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                wa_number = msg.get("from", "unknown")
                try:
                    handle_message(msg)
                except Exception as exc:
                    logger.exception("Unhandled failure processing message from=%s", wa_number)
                    send_processing_failure_email(wa_number, f"{type(exc).__name__}: {exc}")


def conversation_fields_flag(collected_fields: dict, key: str) -> bool:
    """Internal, underscore-prefixed bookkeeping flags are stored alongside real lead facts
    in collected_fields (see _notes_retry_count, _awaiting_bypass_name). They are never
    advertised to Gemini and never read by the notification email, so they can't leak."""
    return bool(collected_fields.get(key))


NON_TEXT_REPLY = (
    "I'm Hoshang's AI assistant, and I can only read text messages at the moment, so I "
    "haven't been able to open that. Could you type it out instead? If it's a document or a "
    "screenshot you'd like Hoshang to look at, just say so and I'll flag it for him to ask "
    "you for directly."
)

# Placeholder stored for a non-text inbound message. The row has to exist so Meta's retry of
# the same media message is caught by the duplicate check (otherwise the lead gets the
# redirect two or three times), and so the transcript Hoshang reads doesn't have a silent
# hole where they sent something.
_NON_TEXT_PLACEHOLDER = "[{msg_type} message — not readable by the assistant]"


def _handle_non_text_message(wa_message_id: str, wa_number: str, msg_type: str):
    """Answer a voice note / image / document instead of ignoring it.

    Until 2026-09-08 these were dropped with a log line and nothing else: the lead got total
    silence. That is worst precisely where it is most likely to happen — a document
    processing prospect's first instinct is to send a sample invoice, and voice notes are
    completely normal on WhatsApp here. A lead who sends one and hears nothing back assumes
    the number is dead.

    No Gemini call: the reply is fixed, so an unsupported attachment costs nothing and can't
    be used to run up spend.
    """
    db = SessionLocal()
    try:
        db.execute(sql_text("SELECT pg_advisory_xact_lock(hashtext(:wa_number))"), {"wa_number": wa_number})

        if db.query(Message).filter_by(wa_message_id=wa_message_id).first() is not None:
            db.rollback()
            logger.info("Duplicate non-text message_id=%s, skipping", wa_message_id)
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

        now = datetime.now(timezone.utc)
        db.add(Message(
            conversation_id=conversation.id,
            wa_message_id=wa_message_id,
            direction="in",
            text=_NON_TEXT_PLACEHOLDER.format(msg_type=msg_type),
        ))
        conversation.last_inbound_at = now

        # Once the funnel has closed and Hoshang has taken over, the bot stays quiet here for
        # the same reason it stays quiet for ordinary text — see the human_takeover branch in
        # handle_message.
        if lead.human_takeover:
            db.commit()
            logger.info("Non-text message from=%s during human_takeover — logged, no reply", wa_number)
            return

        db.add(Message(
            conversation_id=conversation.id,
            wa_message_id=f"{wa_message_id}-reply",
            direction="out",
            text=NON_TEXT_REPLY,
        ))
        db.commit()
    finally:
        db.close()

    logger.info("Sent text-only redirect for type=%s from=%s", msg_type, wa_number)
    _send_reply(wa_number, NON_TEXT_REPLY, now)


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
        _handle_non_text_message(wa_message_id, wa_number, msg_type)
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
            existing_fields = dict(conversation.collected_fields or {})
            awaiting_bypass_name = existing_fields.pop("_awaiting_bypass_name", False)

            if awaiting_bypass_name:
                # Their reply to the "what's your name?" ask in the bypass message. NOT
                # trusted as a clean name (see send_bypass_name_followup_email's docstring —
                # the lead this was built for replied "Ok will wait for his call," not a
                # name), just forwarded to Hoshang labeled as their raw reply so he can judge
                # it himself. One-shot: the flag is cleared either way, so only the first
                # reply after a bypass gets this treatment.
                conversation.collected_fields = existing_fields
                db.add(Message(
                    conversation_id=conversation.id, wa_message_id=wa_message_id, direction="in", text=body_text
                ))
                db.commit()
                logger.info("Lead %s replied after bypass name request — forwarded to Hoshang", lead.id)
                send_bypass_name_followup_email(wa_number, body_text)
                return

            # A direct "is this a bot?" or an explicit ask for Hoshang's own contact details
            # are the two things that still get answered here. Everything else genuinely
            # should stay silent — no Gemini call, no reopening a closed funnel — but a
            # truthful answer to either of these costs nothing and shouldn't require Hoshang
            # to be online. On 2026-08-22 a real, already-qualified lead asked the identity
            # question twice and got silence both times.
            if is_identity_question(body_text):
                reply_text = IDENTITY_QUESTION_REPLY
            elif is_contact_info_request(body_text):
                reply_text = CONTACT_INFO_REPLY
            else:
                reply_text = None
            logger.info(
                "Lead %s has human_takeover set — %s",
                lead.id, f"answering ({reply_text[:30]}...)" if reply_text else "bot stays silent",
            )
            db.add(Message(
                conversation_id=conversation.id, wa_message_id=wa_message_id, direction="in", text=body_text
            ))
            if reply_text:
                db.add(Message(
                    conversation_id=conversation.id,
                    wa_message_id=f"{wa_message_id}-reply",
                    direction="out",
                    text=reply_text,
                ))
            db.commit()
            if reply_text:
                # This message just arrived, so it's trivially inside the 24h session window —
                # `now` isn't computed yet at this point in the function (that happens further
                # down, for the normal-flow path), so it's derived fresh here instead.
                _send_reply(wa_number, reply_text, datetime.now(timezone.utc))
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
            reply_text = ensure_closing_thanks(BYPASS_REPLIES[bypass])
            lead.human_takeover = True
            # The bypass reply now asks for their name (see routing.BYPASS_REPLIES) — this
            # flag makes their very next message get treated as the reply to that ask, rather
            # than silently dropped like everything else once human_takeover is set. Cleared
            # (and acted on) in the human_takeover branch above.
            collected_fields["_awaiting_bypass_name"] = True
            conversation.collected_fields = collected_fields
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
            reply_text, result = _apply_force_handoff(
                db, conversation, collected_fields,
                reply_text=(
                    "Thanks so much for the detail so far. I want to make sure Hoshang picks this up "
                    "directly rather than keep you going back and forth here. He'll follow up with you shortly."
                ),
                incomplete_reason="message_cap",
            )
            db.commit()
            log_transition(lead_id, current_state, "qualification_decision", None, "message_cap_forced")
            # Notified regardless of qualified — see send_lead_notification_email's docstring.
            # This is the message-cap path specifically: a lead cut off one exchange short of
            # finishing must not vanish any more than one who finishes and scores low.
            send_lead_notification_email(wa_number, collected_fields, result)
            if result["qualified"]:
                append_qualified_lead(wa_number, collected_fields, result)
            _send_reply(wa_number, reply_text, now)
            return

        notes_retries = int(collected_fields.get("_notes_retry_count", 0) or 0)

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
        should_email = False
        result = None

        # Additional Notes retry cap — this is the one state whose own instructions allow it
        # to loop indefinitely (re-asking "anything else?" for as long as the lead keeps
        # asking questions instead of closing out). Bounded only by the global MAX_MESSAGES
        # cap above, that's a very loose limit for one specific state, and every extra round
        # is a real Gemini cost for a conversation that has, in practice, already collected
        # everything scoring needs.
        #
        # This only overrides the model's OWN reply once NOTES_RETRY_LIMIT rounds are reached
        # AND the model is still stuck in additional_notes after processing the current
        # message — a close-out answer on any round, including the Nth, always gets evaluated
        # by Gemini first. Until 2026-09-07 this cap was checked BEFORE calling Gemini, using
        # only the count from PRIOR turns, so a genuine close-out arriving exactly on the Nth
        # round never got a chance: three earlier rounds that had each correctly answered a
        # real question (which additional_notes.py explicitly allows, and is not stalling)
        # tripped the same counter as actual stalling, and the very next message — a real
        # "that's all thanks" — was swallowed by the deterministic force-close before Gemini
        # ever saw it.
        #
        # Only CHATTER rounds count. A round the model classified as a genuine question
        # (notes_turn_kind, see states/additional_notes.py) leaves the counter untouched, so
        # a serious buyer working through cancellation terms, ownership, and running costs is
        # never cut off for asking. A missing/unrecognised value counts as substantive —
        # the safe direction, since MAX_MESSAGES above is the real backstop and a dropped
        # bookkeeping field must never be what closes a live conversation.
        if current_state == "additional_notes" and new_state == "additional_notes":
            if updated_fields.get("notes_turn_kind") == "chatter":
                notes_retries += 1
            if notes_retries >= NOTES_RETRY_LIMIT:
                new_state = "qualification_decision"
                reply_text = (
                    "I'll pass everything on to Hoshang now so he can pick this up with you "
                    "directly, he'll follow up personally. If anything else comes to mind in "
                    "the meantime, it's best saved for the call with him."
                )
                updated_fields["incomplete"] = "notes_retry_cap"
            else:
                updated_fields["_notes_retry_count"] = notes_retries

        just_qualified = new_state == "qualification_decision" and current_state != "qualification_decision"

        # The whole introduction (greeting, AI disclosure, what happens next) is owned by
        # code, not the prompt — see ensure_opening_frame. Applied once per conversation.
        #
        # Keyed on a flag rather than "is this the first message", because it isn't always:
        # a lead whose opening move is a voice note or a photo of an invoice has already had
        # one exchange (the text-only redirect) by the time they type anything, and would
        # otherwise never be introduced to properly.
        if not conversation_fields_flag(collected_fields, "_opened"):
            reply_text = ensure_opening_frame(reply_text)
            updated_fields["_opened"] = "1"

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
            # Notified regardless of qualified. Until 2026-08-22 this was gated on
            # result["qualified"], so an unqualified lead was told "that gives him everything
            # he needs" while Hoshang received nothing — see send_lead_notification_email's
            # docstring for the real lead this happened to. The threshold decides whether a
            # lead gets a self-service Calendly link, not whether Hoshang finds out at all.
            should_email = True
            # Enforced in code — see ensure_closing_thanks. Applied before the Calendly line,
            # so a qualified lead reads thanks, then the link, in that order.
            reply_text = ensure_closing_thanks(reply_text)
            if result["qualified"]:
                # Calendly link is injected deterministically, never model-generated —
                # a hallucinated/malformed URL in a real lead's WhatsApp is not acceptable.
                reply_text = f"{reply_text}\n\nFeel free to grab a slot directly: {config.CALENDLY_LINK}"

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
        send_lead_notification_email(wa_number, updated_fields, result)
        if result["qualified"]:
            append_qualified_lead(wa_number, updated_fields, result)

    send_outcome = _send_reply(wa_number, reply_text, now)
    log_transition(lead_id, current_state, new_state, gemini_ms, send_outcome)


SEND_RETRY_DELAYS_SECS = (1, 3)


def _send_reply(wa_number: str, reply_text: str, last_inbound_at) -> str:
    """Sends the WhatsApp reply after the DB transaction (and advisory lock) has already
    released — no reason to hold either open for a network call that doesn't touch the DB.

    Retries a couple of times, then alerts. Until 2026-09-08 a failed send was logged and
    nothing else: the conversation state had already been committed, so the bot believed it
    had replied, the lead saw nothing at all, and the only trace was a line in the Render
    logs nobody was watching. The lead's next message would then arrive against a state that
    had silently moved on without them. Most failures here are a transient blip on Meta's
    side or a momentary network drop, which a retry fixes; anything that survives all three
    attempts is something Hoshang needs to know about while the lead is still warm.
    """
    last_error = None
    for attempt, delay in enumerate((0, *SEND_RETRY_DELAYS_SECS), start=1):
        if delay:
            time.sleep(delay)
        try:
            asyncio.run(send_message(to=wa_number, text=reply_text, last_inbound_at=last_inbound_at))
            if attempt > 1:
                logger.info("Reply to %s sent on attempt %d", wa_number, attempt)
            return "sent"
        except Exception as exc:
            last_error = exc
            logger.warning("Send attempt %d to %s failed: %s", attempt, wa_number, exc)

    logger.error("All send attempts to %s failed", wa_number, exc_info=last_error)
    try:
        send_undelivered_reply_email(wa_number, reply_text, f"{type(last_error).__name__}: {last_error}")
    except Exception:
        # An alert that fails must not take down the turn that was otherwise fine.
        logger.exception("Failed to send undelivered-reply alert for %s", wa_number)
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


def _apply_force_handoff(
    db, conversation: Conversation, collected_fields: dict, reply_text: str, incomplete_reason: str,
) -> tuple[str, dict]:
    """A deterministic, non-Gemini close-out — used by both the global message cap and the
    additional_notes retry cap. Force to qualification_decision, hand off to Hoshang directly.
    See full blueprint Section 10/11 — forced handoff with partial data flagged incomplete.

    Still qualifies (and the caller still emails) if the fields actually collected genuinely
    score as qualified — "incomplete" only means additional_notes wasn't reached cleanly, it
    doesn't mean the real scoring fields are missing. Every scoring-relevant field (service
    type, scope, budget, timeline, contact) is collected in the states BEFORE additional_notes,
    which itself carries zero scoring weight — so by the time either cap fires, score_lead()
    already has everything it needs to be accurate. A lead who answered everything real and
    just got cut off — by hitting the message cap, or by looping past the notes retry limit —
    still deserves the same notification and, if they'd have qualified anyway, the same link.

    Mutates `conversation` in place on the caller's already-open session/transaction rather
    than opening its own — this used to run in a separate SessionLocal(), which meant it
    wasn't covered by the same advisory lock as the rest of this turn's processing.
    """
    collected_fields = {**collected_fields, "incomplete": incomplete_reason}
    result = score_lead(collected_fields)

    reply_text = ensure_closing_thanks(reply_text)
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
        "Conversation %s forced handoff (%s) — score=%s qualified=%s",
        conversation.id, incomplete_reason, result["score"], result["qualified"],
    )
    return reply_text, result
