"""Central config: loads every environment variable this service needs from `.env` (or the
host's environment in production) into module-level constants used throughout the app.
"""

import os
from dotenv import load_dotenv

load_dotenv()

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
