# Uses the `google-genai` SDK (google-generativeai is deprecated/EOL as of this build).
import json
import logging

from google import genai
from google.genai import types
from pydantic import ValidationError

import config
from schemas import ConversationTurnResult

logger = logging.getLogger("leadpilot.gemini")

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


async def call_gemini(prompt: str, system_instruction: str) -> ConversationTurnResult | None:
    """Returns None on unrecoverable failure (Section 9a, dependency failure — caller sends
    a filler message and retries later). Schema validation (Step 1) happens here; business-rule
    validation (Step 2) happens in the caller, since it needs conversation context this
    function doesn't have."""
    if config.MOCK_LLM:
        return ConversationTurnResult(
            reply_text="mock reply",
            extracted_fields={},
            next_state="greeting",
            confidence_flag="high",
        )

    for attempt in range(2):
        try:
            response = _get_client().models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                ),
            )
            raw = json.loads(response.text)
            return ConversationTurnResult(**raw)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Gemini output failed schema validation (attempt %d): %s", attempt + 1, e)
            continue
        except Exception:
            logger.exception("Gemini call failed (attempt %d)", attempt + 1)
            continue

    return None
