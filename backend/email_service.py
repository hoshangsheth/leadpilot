import logging

import resend

import config

resend.api_key = config.RESEND_API_KEY
logger = logging.getLogger("leadpilot.email")


def send_qualified_lead_email(wa_number: str, collected_fields: dict, score_result: dict) -> None:
    name = collected_fields.get("contact_name", "Unknown")
    service_type = collected_fields.get("service_type", "unclear")
    requirement = collected_fields.get("requirement_summary", "-")
    budget = collected_fields.get("budget_range", "not disclosed")
    timeline = collected_fields.get("timeline_expectation", "-")
    preference = collected_fields.get("contact_preference", "-")
    notes = collected_fields.get("additional_notes", "-")

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
