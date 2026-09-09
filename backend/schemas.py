"""Pydantic schema for the structured JSON Gemini must return each turn — the Step 1
(schema) half of the two-step AI output verification; see validation/ai_output_rules.py
for Step 2 (business-rule validation).
"""

import json
from typing import Literal

from pydantic import BaseModel, field_validator


class ConversationTurnResult(BaseModel):
    reply_text: str
    extracted_fields: dict[str, str]
    next_state: str  # proposed — validated against the deterministic transition table before trusting it
    confidence_flag: Literal["high", "low"]

    @field_validator("extracted_fields", mode="before")
    @classmethod
    def _coerce_scalar_values(cls, value):
        """Stringify scalar field values before validation.

        extracted_fields is typed dict[str, str] because every downstream consumer — scoring's
        text parsers, the notification email's html.escape — expects text. Pydantic v2 does
        not coerce int -> str, so a model that answered `{"budget_range": 50000}` or
        `{"business_size": 30}` failed the whole turn's schema validation. Both retries then
        failed the same way (same prompt, same shape), process_message returned None, and the
        lead got no reply at all while the failure showed up only as a `gemini_failed` log
        line — no alert, no follow-up. Found 2026-09-08 during a full audit.

        Numbers are the natural way to answer a question about money or headcount, so this is
        normalisation at the boundary, not leniency: the model's judgment was correct and only
        its JSON type was wrong. Nulls are dropped rather than turned into the string "None",
        which would otherwise be stored and shown to Hoshang as a real answer.
        """
        if not isinstance(value, dict):
            return value

        coerced = {}
        for key, raw in value.items():
            if raw is None:
                continue
            if isinstance(raw, str):
                coerced[key] = raw
            elif isinstance(raw, bool):
                coerced[key] = "true" if raw else "false"
            elif isinstance(raw, (int, float)):
                coerced[key] = str(raw)
            elif isinstance(raw, (dict, list)):
                coerced[key] = json.dumps(raw, ensure_ascii=False)
            else:
                coerced[key] = str(raw)
        return coerced


class WidgetTurnResult(BaseModel):
    """The website widget's structured output. No extracted_fields, no next_state — the
    widget answers questions only, it never runs the qualification state machine. `handoff`
    is the one decision it makes: true once the visitor is ready to talk about their own
    project, at which point the frontend surfaces a "Continue on WhatsApp" action."""
    reply_text: str
    handoff: bool
