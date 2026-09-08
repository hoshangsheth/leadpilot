"""Sends the qualified-lead notification email to Hoshang via Resend, with every
lead-controlled field HTML-escaped before interpolation into the email body.
"""

import html
import logging

import resend

import config

resend.api_key = config.RESEND_API_KEY
logger = logging.getLogger("leadpilot.email")

# Rendered as a banner at the very top of the email. A scope mismatch changes how Hoshang
# should open the call (honest "here's what I can and can't do" vs. straight into discovery),
# so it must be impossible to miss — not something to infer from a slightly lower score.
_SCOPE_BANNERS = {
    "in_scope": (
        "#1a7f37", "#e8f5ec",
        "In scope. Matches the usual automation workflows.",
    ),
    "partial": (
        "#9a6700", "#fff8e5",
        "Partial fit. The core ask sits outside the practice, but there may be an adjacent "
        "workflow worth building. Confirm what is actually feasible before scoping.",
    ),
    "out_of_scope": (
        "#b3261e", "#fdecea",
        "OUT OF SCOPE. This is not something the practice builds. The assistant did not "
        "promise otherwise, but open the call by being straight about that, then look for a "
        "workflow around the edges that IS a fit.",
    ),
    "unclear": (
        "#57606a", "#f3f4f6",
        "Scope unclear from the conversation. Establish what they actually need on the call.",
    ),
    # Never render silence. An unrecognized flag previously produced no banner at all, which
    # is indistinguishable from "everything is fine" — that is precisely how the 2026-08-22
    # normalization bug stayed invisible in the inbox. Say so explicitly instead.
    "unknown": (
        "#57606a", "#f3f4f6",
        "Scope was not classified for this lead. Treat fit as unverified and confirm on the call.",
    ),
}


def _scope_banner_html(scope_flag: str) -> str:
    color, background, message = _SCOPE_BANNERS.get(scope_flag, _SCOPE_BANNERS["unknown"])
    return (
        f'<p style="margin:0 0 16px;padding:12px 14px;border-left:4px solid {color};'
        f'background:{background};color:{color};font-weight:600;">{html.escape(message)}</p>'
    )


def _blockers_html(blockers: list[str]) -> str:
    """Hard commercial mismatches, rendered above the score.

    A high score with an unaffordable budget is actively misleading — the 2026-08-22 CA-firm
    lead scored 87/100 while capped at ₹15,000 against a ₹35,000 floor and wanting delivery in
    2 weeks against a 5-12 week build. Perfect fit on pain and scope, impossible on terms.
    Those facts decide whether the call is worth booking, so they are stated outright instead
    of being averaged into a number.
    """
    if not blockers:
        return ""
    items = "".join(f"<li>{html.escape(b)}</li>" for b in blockers)
    return (
        '<div style="margin:0 0 16px;padding:12px 14px;border-left:4px solid #b3261e;'
        'background:#fdecea;color:#b3261e;">'
        '<strong style="display:block;margin-bottom:6px;">BLOCKERS — resolve before scoping</strong>'
        f'<ul style="margin:0;padding-left:18px;">{items}</ul></div>'
    )


def send_handoff_email(wa_number: str, reason: str, first_message: str, source: str) -> None:
    """Fires when a warm contact or an explicit human request bypasses the funnel.

    This notification is not optional. The bot's number is not Hoshang's personal phone, so a
    bypassed conversation is one he cannot see — going silent without telling him would drop
    the highest-intent leads he gets (referrals, people who know him) into a void. Sent
    instead of the qualified-lead email, since there is no score and no funnel data.
    """
    wa_number = html.escape(wa_number)
    first_message = html.escape(first_message)
    source = html.escape(source)
    label = {
        "warm": "Warm contact — referral or personal connection",
        "human_request": "Asked to speak to you directly",
    }.get(reason, reason)

    subject = f"[REPLY PERSONALLY] {label} — {wa_number}"
    html_body = f"""
    <h2>Bot handed off — no qualification run</h2>
    <p style="margin:0 0 16px;padding:12px 14px;border-left:4px solid #1a7f37;background:#e8f5ec;
    color:#1a7f37;font-weight:600;">{html.escape(label)}. They were NOT put through the
    qualification questions. Reply to them yourself.</p>
    <ul>
        <li><strong>WhatsApp:</strong> {wa_number}</li>
        <li><strong>Source:</strong> {source}</li>
        <li><strong>They said:</strong> {first_message}</li>
    </ul>
    """
    try:
        resend.Emails.send({
            "from": "LeadPilot <onboarding@resend.dev>",
            "to": config.NOTIFY_EMAIL,
            "subject": subject,
            "html": html_body,
        })
    except Exception:
        logger.exception("Failed to send handoff email for wa_number=%s", wa_number)


def send_bypass_name_followup_email(wa_number: str, reply_text: str) -> None:
    """Fires once, the first time a bypassed lead replies after being asked their name (see
    routing.BYPASS_REPLIES). Deliberately does NOT claim the reply is a clean name — on
    2026-08-24 the lead this was built for replied "Ok will wait for his call," not a name.
    Labeled as their raw reply so Hoshang judges it himself rather than the system asserting
    a certainty it doesn't have.
    """
    wa_number = html.escape(wa_number)
    reply_text = html.escape(reply_text)
    try:
        resend.Emails.send({
            "from": "LeadPilot <onboarding@resend.dev>",
            "to": config.NOTIFY_EMAIL,
            "subject": f"Reply to name request — {wa_number}",
            "html": f"""
            <h2>Follow-up on a handed-off lead</h2>
            <p><strong>WhatsApp:</strong> {wa_number}</p>
            <p><strong>Replied to "what's your name":</strong> {reply_text}</p>
            """,
        })
    except Exception:
        logger.exception("Failed to send bypass name-followup email for wa_number=%s", wa_number)


def send_processing_failure_email(wa_number: str, error_summary: str) -> None:
    """Fires when handle_message raises before a reply could be sent — a DB blip, an
    unexpected exception, anything that isn't the normal Gemini-unreachable path (which
    already degrades gracefully by staying silent for one turn and retrying next message).

    This is the case those don't cover: something broke badly enough that no reply went out
    and the conversation state may not even be consistent. Without this email, that lead gets
    total silence and Hoshang has no way to know short of reading Render logs — the same
    "silent failure" class as the unqualified-lead and bypass-handoff bugs already fixed here,
    just triggered by infrastructure instead of conversation logic. Best-effort reply to the
    lead is out of scope here (the failure may be the DB itself, which a reply can't route
    around); the point is making sure Hoshang finds out and can follow up personally.
    """
    wa_number = html.escape(wa_number)
    error_summary = html.escape(error_summary)
    try:
        resend.Emails.send({
            "from": "LeadPilot <onboarding@resend.dev>",
            "to": config.NOTIFY_EMAIL,
            "subject": f"[ACTION NEEDED] Message processing failed — {wa_number}",
            "html": f"""
            <h2>A message could not be processed</h2>
            <p style="margin:0 0 16px;padding:12px 14px;border-left:4px solid #b3261e;background:#fdecea;
            color:#b3261e;font-weight:600;">No reply was sent for this message. The lead has
            received nothing. Please follow up with them directly.</p>
            <ul>
                <li><strong>WhatsApp:</strong> {wa_number}</li>
                <li><strong>Error:</strong> {error_summary}</li>
            </ul>
            """,
        })
    except Exception:
        logger.exception("Failed to send processing-failure alert for wa_number=%s", wa_number)


def send_undelivered_reply_email(wa_number: str, reply_text: str, error_summary: str) -> None:
    """Fires when a reply was generated successfully but could not be delivered to WhatsApp
    after every retry.

    Distinct from send_processing_failure_email: nothing went wrong with the conversation
    itself, so the state has already advanced and the transcript records a reply the lead
    never actually received. That is the dangerous part — from the lead's side the number
    simply went quiet mid-conversation, and their next message will land against a state that
    moved on without them. The undelivered text is included so Hoshang can just paste it to
    them himself and pick the conversation up where it stopped.
    """
    wa_number = html.escape(wa_number)
    error_summary = html.escape(error_summary)
    reply_text = html.escape(reply_text)
    try:
        resend.Emails.send({
            "from": "LeadPilot <onboarding@resend.dev>",
            "to": config.NOTIFY_EMAIL,
            "subject": f"[ACTION NEEDED] Reply not delivered — {wa_number}",
            "html": f"""
            <h2>A reply could not be delivered</h2>
            <p style="margin:0 0 16px;padding:12px 14px;border-left:4px solid #b3261e;background:#fdecea;
            color:#b3261e;font-weight:600;">The conversation advanced but this message never
            reached the lead. From their side the chat has gone silent. Send it to them
            yourself to pick it back up.</p>
            <ul>
                <li><strong>WhatsApp:</strong> {wa_number}</li>
                <li><strong>Error:</strong> {error_summary}</li>
            </ul>
            <p><strong>Undelivered message:</strong></p>
            <blockquote style="margin:0;padding:12px 14px;background:#f3f4f6;border-left:4px solid #57606a;
            white-space:pre-wrap;">{reply_text}</blockquote>
            """,
        })
    except Exception:
        logger.exception("Failed to send undelivered-reply alert for wa_number=%s", wa_number)


def send_stranded_messages_email(stranded: list[dict]) -> None:
    """Fires at startup when a conversation's last word was the lead's and no reply followed.

    In practice this means the process died between acking Meta and replying — a deploy or a
    restart — which nothing else can catch, because no exception was ever raised. See
    recovery.py for why an alert is the chosen fix rather than a durable queue.
    """
    rows = "".join(
        f"<li><strong>{html.escape(item['wa_number'])}</strong> — "
        f"{html.escape(str(item['received_at']))}<br>"
        f"<span style='color:#40464d;'>{html.escape(item['text'])}</span></li>"
        for item in stranded
    )
    count = len(stranded)
    try:
        resend.Emails.send({
            "from": "LeadPilot <onboarding@resend.dev>",
            "to": config.NOTIFY_EMAIL,
            "subject": f"[ACTION NEEDED] {count} message(s) awaiting a reply after restart",
            "html": f"""
            <h2>{count} conversation(s) never got a reply</h2>
            <p style="margin:0 0 16px;padding:12px 14px;border-left:4px solid #b3261e;background:#fdecea;
            color:#b3261e;font-weight:600;">These leads sent a message and heard nothing back,
            most likely because the service restarted mid-processing. Please reply to them
            directly.</p>
            <ul>{rows}</ul>
            """,
        })
    except Exception:
        logger.exception("Failed to send stranded-messages alert")


def send_lead_notification_email(wa_number: str, collected_fields: dict, score_result: dict) -> None:
    """Fires for every conversation that reaches qualification_decision — qualified or not.

    Until 2026-08-22 this only fired when score_result["qualified"] was True. A real lead
    (Sneha Thakkar, a Mumbai dryfruit store wanting a website) scored 35/100 — under scope,
    no budget given — and the bot's closing line "Perfect, that gives him everything he
    needs" went out as normal. It was a lie: Hoshang received nothing, ever, because the
    email was gated on the same threshold as the Calendly link. She messaged again 17
    minutes later asking when she'd hear back, into a conversation nobody but her had any
    visibility into.

    The threshold should decide whether a lead gets a Calendly link and self-service
    booking, not whether Hoshang finds out someone reached out. Those are different
    decisions.  This function now sends unconditionally; the qualified/not distinction is
    reflected on the email itself (subject prefix, banner, and whether the reply included a
    booking link) so he can act on judgment rather than being kept in the dark.
    """
    # Every one of these fields ultimately comes from free text a stranger typed on WhatsApp,
    # then passed through the model into extracted_fields. Escaping before HTML interpolation
    # is required, not optional — an unescaped field is a real HTML/script injection vector
    # into an email that opens in Hoshang's own inbox.
    name = html.escape(collected_fields.get("contact_name", "Unknown"))
    company_name = html.escape(collected_fields.get("company_name", "-"))
    service_type = html.escape(collected_fields.get("service_type", "unclear"))
    requirement = html.escape(collected_fields.get("requirement_summary", "-"))
    business_size = html.escape(collected_fields.get("business_size", "-"))
    budget = html.escape(collected_fields.get("budget_range", "not disclosed"))
    timeline = html.escape(collected_fields.get("timeline_expectation", "-"))
    preference = html.escape(collected_fields.get("contact_preference", "-"))
    notes = html.escape(collected_fields.get("additional_notes", "-"))
    lead_source = html.escape(collected_fields.get("lead_source", "Unknown"))
    wa_number = html.escape(wa_number)

    scope_flag = score_result.get("scope_flag", "unknown")
    blockers = score_result.get("blockers", [])
    qualified = score_result.get("qualified", False)

    # Prefixed into the subject line too, so status is visible from the inbox list without
    # opening the mail. Unqualified outranks everything else — that is the fact most likely
    # to change what Hoshang does with this email, since it means no Calendly link went out
    # and nothing happens next unless he acts on it himself.
    if not qualified:
        subject_prefix = "[UNQUALIFIED — NO AUTO FOLLOW-UP] "
    elif blockers:
        subject_prefix = "[BLOCKERS] "
    else:
        subject_prefix = {
            "out_of_scope": "[OUT OF SCOPE] ",
            "partial": "[PARTIAL FIT] ",
        }.get(scope_flag, "")

    lead_label = "New Qualified Lead" if qualified else "Lead Did Not Qualify"
    subject = f"{subject_prefix}{lead_label}: {name} — {service_type}"

    unqualified_banner = "" if qualified else (
        '<p style="margin:0 0 16px;padding:12px 14px;border-left:4px solid #57606a;'
        'background:#f3f4f6;color:#40464d;font-weight:600;">'
        f'Scored {score_result["score"]}/100 — below the qualifying threshold. '
        "No Calendly link was sent and the bot will not follow up further; the lead was "
        'still told "that gives him everything he needs," so if you want to reply, '
        "it has to be you, and they are currently waiting on it.</p>"
    )

    html_body = f"""
    <h2>{lead_label}</h2>
    {unqualified_banner}
    {_blockers_html(blockers)}
    {_scope_banner_html(scope_flag)}
    <p><strong>Score:</strong> {score_result['score']}/100</p>
    <ul>
        <li><strong>Name:</strong> {name}</li>
        <li><strong>Company:</strong> {company_name}</li>
        <li><strong>WhatsApp:</strong> {wa_number}</li>
        <li><strong>Source:</strong> {lead_source}</li>
        <li><strong>Service type:</strong> {service_type}</li>
        <li><strong>Requirement:</strong> {requirement}</li>
        <li><strong>Business size:</strong> {business_size}</li>
        <li><strong>Budget:</strong> {budget}</li>
        <li><strong>Timeline:</strong> {timeline}</li>
        <li><strong>Contact preference:</strong> {preference}</li>
        <li><strong>Additional notes:</strong> {notes}</li>
    </ul>
    <p><strong>Score breakdown:</strong> {score_result['breakdown']}</p>
    """

    try:
        resend.Emails.send({
            "from": "LeadPilot <onboarding@resend.dev>",
            "to": config.NOTIFY_EMAIL,
            "subject": subject,
            "html": html_body,
        })
    except Exception:
        logger.exception("Failed to send lead-notification email for wa_number=%s", wa_number)
