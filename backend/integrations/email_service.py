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


def send_qualified_lead_email(wa_number: str, collected_fields: dict, score_result: dict) -> None:
    # Every one of these fields ultimately comes from free text a stranger typed on WhatsApp,
    # then passed through the model into extracted_fields. Escaping before HTML interpolation
    # is required, not optional — an unescaped field is a real HTML/script injection vector
    # into an email that opens in Hoshang's own inbox.
    name = html.escape(collected_fields.get("contact_name", "Unknown"))
    service_type = html.escape(collected_fields.get("service_type", "unclear"))
    requirement = html.escape(collected_fields.get("requirement_summary", "-"))
    business_size = html.escape(collected_fields.get("business_size", "-"))
    budget = html.escape(collected_fields.get("budget_range", "not disclosed"))
    timeline = html.escape(collected_fields.get("timeline_expectation", "-"))
    preference = html.escape(collected_fields.get("contact_preference", "-"))
    notes = html.escape(collected_fields.get("additional_notes", "-"))
    wa_number = html.escape(wa_number)

    scope_flag = score_result.get("scope_flag", "unknown")
    blockers = score_result.get("blockers", [])
    # Prefixed into the subject line too, so a mismatch is visible from the inbox list
    # without opening the mail. A blocker outranks the scope label: an in-scope lead who
    # cannot pay still needs flagging before the call gets booked.
    if blockers:
        subject_prefix = "[BLOCKERS] "
    else:
        subject_prefix = {
            "out_of_scope": "[OUT OF SCOPE] ",
            "partial": "[PARTIAL FIT] ",
        }.get(scope_flag, "")

    subject = f"{subject_prefix}New Qualified Lead: {name} — {service_type}"
    html_body = f"""
    <h2>New Qualified Lead</h2>
    {_blockers_html(blockers)}
    {_scope_banner_html(scope_flag)}
    <p><strong>Score:</strong> {score_result['score']}/100</p>
    <ul>
        <li><strong>Name:</strong> {name}</li>
        <li><strong>WhatsApp:</strong> {wa_number}</li>
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
        logger.exception("Failed to send qualified-lead email for wa_number=%s", wa_number)
