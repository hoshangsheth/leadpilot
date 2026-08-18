import html
import logging

import resend

import config

resend.api_key = config.RESEND_API_KEY
logger = logging.getLogger("leadpilot.email")


def send_qualified_lead_email(wa_number: str, collected_fields: dict, score_result: dict) -> None:
    # Every one of these fields ultimately comes from free text a stranger typed on WhatsApp,
    # then passed through the model into extracted_fields. Escaping before HTML interpolation
    # is required, not optional — an unescaped field is a real HTML/script injection vector
    # into an email that opens in Hoshang's own inbox.
    name = html.escape(collected_fields.get("contact_name", "Unknown"))
    service_type = html.escape(collected_fields.get("service_type", "unclear"))
    requirement = html.escape(collected_fields.get("requirement_summary", "-"))
    budget = html.escape(collected_fields.get("budget_range", "not disclosed"))
    timeline = html.escape(collected_fields.get("timeline_expectation", "-"))
    preference = html.escape(collected_fields.get("contact_preference", "-"))
    notes = html.escape(collected_fields.get("additional_notes", "-"))
    wa_number = html.escape(wa_number)

    subject = f"New Qualified Lead: {name} — {service_type}"
    html = f"""
    <h2>New Qualified Lead</h2>
    <p><strong>Score:</strong> {score_result['score']}/100</p>
    <ul>
        <li><strong>Name:</strong> {name}</li>
        <li><strong>WhatsApp:</strong> {wa_number}</li>
        <li><strong>Service type:</strong> {service_type}</li>
        <li><strong>Requirement:</strong> {requirement}</li>
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
            "html": html,
        })
    except Exception:
        logger.exception("Failed to send qualified-lead email for wa_number=%s", wa_number)
