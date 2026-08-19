"""Pydantic schema for the structured JSON Gemini must return each turn — the Step 1
(schema) half of the two-step AI output verification; see validation/ai_output_rules.py
for Step 2 (business-rule validation).
"""

from pydantic import BaseModel
from typing import Literal


class ConversationTurnResult(BaseModel):
    reply_text: str
    extracted_fields: dict[str, str]
    next_state: str  # proposed — validated against the deterministic transition table before trusting it
    confidence_flag: Literal["high", "low"]
