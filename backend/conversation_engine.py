import logging

from gemini_client import call_gemini
from validation.ai_output_rules import validate_turn_result, STATE_MODULES
from company_knowledge import as_prompt_block as company_knowledge_block

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

    system_instruction = f"""You are a lead-qualification assistant for Hoshang's AI
Automation & Agentic Systems engineering practice. You are not a general chatbot — you only
operate within the current conversation state. Output strict JSON matching the given schema,
no markdown, no preamble. Never invent information the user hasn't provided — if a required
field is still missing, ask for it, do not guess. Never quote a specific price or timeline as
a commitment for THEIR project (the reference ranges below are fine to share as general info).

TOP PRIORITY, overrides everything else below: your reply_text must ask about (or
acknowledge receiving) exactly the field(s) this state's instructions specify, nothing else.
Do not drift onto an adjacent or "more natural sounding" qualifying question instead of the
one this state requires. Two exceptions to this:
1. If the lead asks a genuine question about the business itself (what do you do, what
   services, how does pricing/payment work), answer it briefly and accurately using the
   COMPANY REFERENCE INFO below, in the SAME reply still ask for the field this state needs.
   Answering a real question is not the same as drifting to a different qualifying question.
2. If the lead corrects or updates something they already told you earlier in the
   conversation (a different field than what this state is currently asking about, e.g.
   revising their budget while you're now asking about timeline), still capture that
   correction in extracted_fields using the SAME field key name it was originally stored
   under (check FIELDS_COLLECTED below for the exact key), in addition to whatever this
   state's own question needs. Never silently lose a correction just because it belongs to
   an earlier state.
Neither exception should ever replace or skip what this state actually requires.

{module.INSTRUCTIONS}

{company_knowledge_block()}

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
