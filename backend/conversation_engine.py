"""Core conversation engine: builds the per-state Gemini prompt, calls the model, normalizes
known field-name aliases, runs business-rule validation, and returns the merged conversation
state for the caller to persist.
"""

import logging
import re

from integrations.gemini_client import call_gemini
from validation.ai_output_rules import validate_turn_result, resolve_effective_state, STATE_MODULES
from company_knowledge import as_prompt_block as company_knowledge_block

logger = logging.getLogger("leadpilot.engine")

MAX_MESSAGES = 50  # message cap, per blueprint Section 10 guardrails — enforced in Day 5.
# Raised 15 -> 30 -> 50 across tonight's live testing: the additional_notes state added a
# 7th non-terminal step, and real conversations run longer than the theoretical minimum once
# clarification questions (e.g. contact detail confirmation) are added in. Real cost per
# extra exchange is trivial (a few paisa), so bias toward completing naturally over cutting
# a nearly-finished conversation off.

# Every field key name that exists anywhere in the funnel, not just the current state's own
# REQUIRED_FIELDS. A real lead frequently volunteers information before the state that would
# normally ask for it (e.g. describing budget while still answering the greeting) — if the
# model is only ever told the current state's own field names, whatever it volunteers early
# gets extracted under an invented key instead of the canonical one, and the funnel can never
# credit that answer later. See validation/ai_output_rules.py's forward-walk validation,
# which depends on exact key matches to know how far a conversation has genuinely progressed.
ALL_FIELD_KEYS = list(dict.fromkeys(
    [field for module in STATE_MODULES.values() for field in module.REQUIRED_FIELDS] + ["additional_notes"]
))

# Same idea for alias normalization — merged across every state, not just the current one,
# so a field named off-script anywhere in the conversation still gets canonicalized.
ALL_ALIASES: dict[str, str] = {}
for _module in STATE_MODULES.values():
    ALL_ALIASES.update(getattr(_module, "ALIASES", {}))

# The prompt already instructs no em dash, but an LLM occasionally ignores a style rule
# under load. Rather than trust compliance, strip it deterministically -- same reasoning as
# the Calendly link being injected in code instead of model-generated, and every field being
# HTML-escaped instead of trusted: never rely on the model alone for something enforceable.
_DASH_BREAK_RE = re.compile(r"\s*[—–]\s*")


def _strip_dashes(reply_text: str) -> str:
    return _DASH_BREAK_RE.sub(", ", reply_text).strip()


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

If the lead volunteers information belonging to a LATER state than the one you're in (e.g.
mentions their budget while you're still on the greeting), extract it now under its correct
canonical key from CANONICAL_FIELD_KEYS below rather than inventing a key or discarding it —
you do not need to ask about it again once it's already been given.

{module.INSTRUCTIONS}

{company_knowledge_block()}

Tone (secondary to the above): brief, warm, genuinely human, not scripted. Under 10 words
of acknowledgment, no restating what the user said, no em dash or " - " as a sentence break
(use periods/commas instead), don't repeat "Hoshang" every message.

Example:
{module.FEW_SHOT}"""

    user_prompt = f"""CURRENT_STATE: {state_name}
FIELDS_COLLECTED: {collected_fields}
FIELDS_MISSING (required for the CURRENT state): {missing}
REQUIRED_FIELD_KEY_NAMES for the current state (use these EXACT keys, no synonyms): {module.REQUIRED_FIELDS}
CANONICAL_FIELD_KEYS for the WHOLE funnel (use the exact matching key if the lead volunteers
any of this early, even before you'd normally ask): {ALL_FIELD_KEYS}
CONVERSATION_HISTORY: {history[-6:]}
LATEST_USER_MESSAGE: {user_text}

Generate the next reply and extract any new fields from the latest message."""

    return system_instruction, user_prompt


async def process_message(state_name: str, collected_fields: dict, history: list[str], user_text: str):
    """Returns (reply_text, new_state, updated_collected_fields) or None on unrecoverable failure."""
    # Catch the persisted state up to what the already-collected fields actually support
    # BEFORE building the prompt — see resolve_effective_state's docstring for why this
    # can't just be left to the model to notice turn over turn.
    state_name = resolve_effective_state(state_name, collected_fields)
    system_instruction, user_prompt = build_prompt(state_name, collected_fields, history, user_text)

    result = await call_gemini(user_prompt, system_instruction)
    if result is None:
        return None

    result.reply_text = _strip_dashes(result.reply_text)

    # Deterministic alias normalization before validation — merged across every state (not
    # just the current one) since a field can now legitimately be volunteered and extracted
    # before its "home" state is reached. See states/contact_verification.py for why this
    # exists in the first place.
    result.extracted_fields = {
        ALL_ALIASES.get(k, k): v for k, v in result.extracted_fields.items()
    }

    result = validate_turn_result(result, state_name, collected_fields)

    updated_fields = {**collected_fields, **result.extracted_fields}
    return result.reply_text, result.next_state, updated_fields
