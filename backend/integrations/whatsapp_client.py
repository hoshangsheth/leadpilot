"""Outbound WhatsApp sending via Meta's Cloud API — free-text messages only, gated by the
24-hour customer-service session window.
"""

from datetime import datetime, timezone, timedelta
import httpx
import config


def is_within_session_window(last_inbound_at: datetime) -> bool:
    now = datetime.now(timezone.utc)
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=timezone.utc)
    return now - last_inbound_at < timedelta(hours=config.WHATSAPP_SESSION_WINDOW_HOURS)


async def send_message(to: str, text: str, last_inbound_at: datetime, template_name: str | None = None):
    """Stage 1: free-text send only, within the 24h window. Template fallback is a v1.5 item
    per the lean blueprint (requires a Meta-approved template, deferred)."""
    if not is_within_session_window(last_inbound_at):
        raise ValueError(
            "Outside 24h session window — free-text send not allowed. "
            "Template fallback deferred to v1.5, see v1-leadpilot-blueprint.md."
        )

    url = f"https://graph.facebook.com/v21.0/{config.PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def send_document(to: str, link: str, filename: str, caption: str, last_inbound_at: datetime):
    """Sends a document by public link rather than uploading to Meta's Media API first — one
    fewer request, and the link approach is a straight substitution of send_message's payload
    shape, no separate upload/media-id lifecycle to manage. Same 24h session-window gate as
    every other outbound send; Meta fetches the link itself, so the URL must stay publicly
    reachable with no auth."""
    if not is_within_session_window(last_inbound_at):
        raise ValueError(
            "Outside 24h session window — free-text send not allowed. "
            "Template fallback deferred to v1.5, see v1-leadpilot-blueprint.md."
        )

    url = f"https://graph.facebook.com/v21.0/{config.PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {"link": link, "filename": filename, "caption": caption},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
