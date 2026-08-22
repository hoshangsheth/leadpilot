"""Central config: loads every environment variable this service needs from `.env` (or the
host's environment in production) into module-level constants used throughout the app.
"""

import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("leadpilot.config")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
APP_SECRET = os.getenv("APP_SECRET")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")
CALENDLY_LINK = os.getenv("CALENDLY_LINK")
MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"

WHATSAPP_SESSION_WINDOW_HOURS = 24

# Fail fast and loud at boot on a missing/typo'd env var, rather than a cryptic downstream
# crash on first real use (e.g. `config.APP_SECRET.encode()` raising AttributeError on the
# first webhook call, or `create_engine(None)` failing with no indication of which var was
# unset). Especially relevant during the upcoming production WhatsApp number credential
# rotation -- a single missed var should show up immediately in the deploy logs, not silently
# break the one code path that happens to touch it.
_REQUIRED = {
    "WHATSAPP_TOKEN": WHATSAPP_TOKEN,
    "PHONE_NUMBER_ID": PHONE_NUMBER_ID,
    "APP_SECRET": APP_SECRET,
    "VERIFY_TOKEN": VERIFY_TOKEN,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "DATABASE_URL": DATABASE_URL,
    "RESEND_API_KEY": RESEND_API_KEY,
    "NOTIFY_EMAIL": NOTIFY_EMAIL,
    "CALENDLY_LINK": CALENDLY_LINK,
}
_missing = [name for name, value in _REQUIRED.items() if not value]
if _missing:
    raise RuntimeError(
        f"Missing required environment variable(s): {', '.join(_missing)}. "
        "Set them in the environment (or backend/.env for local dev) before starting the app."
    )

# CALENDLY_LINK is the one env var whose *value* is sent verbatim to real leads, so a wrong
# one fails silently and expensively: every qualified lead gets a dead booking link and simply
# never books, with nothing in the logs to show for it. That is exactly what happened on
# 2026-08-22 — the link still pointed at a slug that no longer existed after the real Calendly
# event was created, and it was only caught by manually reading a transcript.
#
# Shape validation catches the empty/typo'd/wrong-domain cases at boot. It cannot know the
# correct slug, so the resolved link is also logged at startup: the deploy log now always
# states which booking URL this instance will hand out, making a stale value visible at deploy
# time instead of discoverable only through a lost lead.
if not CALENDLY_LINK.startswith("https://calendly.com/"):
    raise RuntimeError(
        f"CALENDLY_LINK must be a https://calendly.com/... URL, got: {CALENDLY_LINK!r}. "
        "This value is sent directly to leads, so it is validated at boot."
    )
logger.info("Booking link in use for qualified leads: %s", CALENDLY_LINK)
