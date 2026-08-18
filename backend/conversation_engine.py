import logging

from gemini_client import call_gemini
from validation.ai_output_rules import validate_turn_result, STATE_MODULES

logger = logging.getLogger("leadpilot.engine")

MAX_MESSAGES = 50  # message cap, per blueprint Section 10 guardrails — enforced in Day 5.
# Raised 15 -> 30 -> 50 across tonight's live testing: the additional_notes state added a
# 7th non-terminal step, and real conversations run longer than the theoretical minimum once
# clarification questions (e.g. contact detail confirmation) are added in. Real cost per
# extra exchange is trivial (a few paisa), so bias toward completing naturally over cutting
# a nearly-finished conversation off.


def build_prompt(state_name: str, collected_fields: dict, history: list[str], user_text: str) -> tuple[str, str]:
    module = STATE_MODULES[state_name]
    missing = [f for f in module.REQUIRED_FIELDS if f not in collected_fields or not collected_fields[f]]

    system_instruction = f"""You are a lead-qualification assistant for Hoshang's freelance
AI/ML engineering services. You are not a general chatbot — you only operate within the
current conversation state. Output strict JSON matching the given schema, no markdown, no
preamble. Never invent information the user hasn't provided — if a required field is still
missing, ask for it, do not guess. Never quote prices or timelines as commitments.

TOP PRIORITY, overrides everything else below: your reply_text must ask about (or
acknowledge receiving) exactly the field(s) this state's instructions specify, nothing else.
Do not drift onto an adjacent or "more natural sounding" question. The instructions below
about tone only change HOW you phrase it, never WHAT you ask for.

{module.INSTRUCTIONS}

Tone (secondary to the above): brief, warm, genuinely human, not scripted. Under 10 words
of acknowledgment, no restating what the user said, no em dash or " - " as a sentence break
(use periods/commas instead), don't repeat "Hoshang" every message.

Example:
{module.FEW_SHOT}"""

    user_prompt = f"""CURRENT_STATE: {state_name}
FIELDS_COLLECTED: {collected_fields}
FIELDS_MISSING: {missing}
REQUIRED_FIELD_KEY_NAMES (use these EXACT keys in extracted_fields, no synonyms): {module.REQUIRED_FIELDS}
CONVERSATION_HISTORY: {history[-6:]}
LATEST_USER_MESSAGE: {user_text}

Generate the next reply and extract any new fields from the latest message."""

    return system_instruction, user_prompt


async def process_message(state_name: str, collected_fields: dict, history: list[str], user_text: str):
    """Returns (reply_text, new_state, updated_collected_fields) or None on unrecoverable failure."""
    system_instruction, user_prompt = build_prompt(state_name, collected_fields, history, user_text)

    result = await call_gemini(user_prompt, system_instruction)
    if result is None:
        return None

    # Deterministic alias normalization before validation — see states/contact_verification.py
    # for why this exists.
    module = STATE_MODULES[state_name]
    aliases = getattr(module, "ALIASES", {})
    if aliases:
        result.extracted_fields = {
            aliases.get(k, k): v for k, v in result.extracted_fields.items()
        }

    result = validate_turn_result(result, state_name, collected_fields)

    updated_fields = {**collected_fields, **result.extracted_fields}
    return result.reply_text, result.next_state, updated_fields
