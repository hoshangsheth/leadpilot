"""Appends every QUALIFIED lead to a Google Sheet, as a running list of leads worth calling.

Deliberately narrower than send_lead_notification_email: that fires for every conversation
that reaches qualification_decision (qualified or not, see its own docstring for why), the
sheet only gets a row when score_result["qualified"] is True, per what was asked for. The
email is still the source of truth for unqualified/blocked leads, this is a convenience view
on top of it, not a replacement.

Auth is a Google service account, not OAuth — no browser sign-in, no token to refresh, works
headlessly from Render. config.GOOGLE_SERVICE_ACCOUNT_JSON holds the service account's key
file contents verbatim (the whole JSON object, not a path to it), and the target spreadsheet
must be shared with that service account's client_email as an Editor, exactly like sharing it
with another person.
"""

import json
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger("leadpilot.sheets")

_SPREADSHEET_ID = "1bDgeDNjrACIxMXBYizcf3M7yy9edDdFpd4--IP4my4Y"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_HEADER_ROW = [
    "Timestamp (UTC)", "Name", "Company", "WhatsApp", "Source", "Service Type",
    "Requirement", "Business Size", "Budget", "Timeline", "Contact Preference",
    "Additional Notes", "Score", "Scope", "Blockers",
]

_client = None


def _get_worksheet():
    """Lazily authorizes once per process, then re-opens the sheet by key on every call —
    gspread's own client is cheap to reuse, the open_by_key call is what confirms the service
    account still has access, so a revoked share shows up as a normal logged exception on the
    next lead rather than a stale handle silently failing later."""
    global _client
    if _client is None:
        creds_info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(creds_info, scopes=_SCOPES)
        _client = gspread.authorize(creds)

    sheet = _client.open_by_key(_SPREADSHEET_ID).sheet1
    if not sheet.row_values(1):
        sheet.append_row(_HEADER_ROW)
    return sheet


def append_qualified_lead(wa_number: str, collected_fields: dict, score_result: dict) -> None:
    """Best-effort only, same as every other integration here: a Sheets outage must never
    block the WhatsApp reply or the email notification, which already carries this same data
    and is sent first."""
    if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        logger.info("GOOGLE_SERVICE_ACCOUNT_JSON not set, skipping sheet append for wa_number=%s", wa_number)
        return

    try:
        sheet = _get_worksheet()
        row = [
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            collected_fields.get("contact_name", "Unknown"),
            collected_fields.get("company_name", "-"),
            wa_number,
            collected_fields.get("lead_source", "Unknown"),
            collected_fields.get("service_type", "unclear"),
            collected_fields.get("requirement_summary", "-"),
            collected_fields.get("business_size", "-"),
            collected_fields.get("budget_range", "not disclosed"),
            collected_fields.get("timeline_expectation", "-"),
            collected_fields.get("contact_preference", "-"),
            collected_fields.get("additional_notes", "-"),
            score_result.get("score"),
            score_result.get("scope_flag", "unknown"),
            "; ".join(score_result.get("blockers", [])) or "-",
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        logger.exception("Failed to append qualified lead to Google Sheet for wa_number=%s", wa_number)
