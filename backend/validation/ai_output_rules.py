"""Business-rule validation, run after schema validation. Catches schema-valid but
nonsensical proposed transitions — e.g. Gemini proposing to advance past a state without
the fields that state (or any state it would skip over) requires. See full blueprint
Section 10.
"""

from schemas import ConversationTurnResult
from states import (
    greeting,
    service_requirement,
    business_context,
    budget,
    timeline,
    contact_verification,
    additional_notes,
    qualification_decision,
)

STATE_MODULES = {
    "greeting": greeting,
    "service_requirement": service_requirement,
    "business_context": business_context,
    "budget": budget,
    "timeline": timeline,
    "contact_verification": contact_verification,
    "additional_notes": additional_notes,
    "qualification_decision": qualification_decision,
}

# Canonical funnel order. A conversation only ever moves forward through this list —
# never backward, and never to a state outside it.
STATE_ORDER = list(STATE_MODULES.keys())


def _fields_satisfied(state_name: str, merged_fields: dict) -> bool:
    module = STATE_MODULES[state_name]
    missing = [f for f in module.REQUIRED_FIELDS if f not in merged_fields or not merged_fields[f]]
    if missing:
        return False
    if hasattr(module, "extra_check"):
        return module.extra_check(merged_fields)
    return True


def validate_turn_result(
    result: ConversationTurnResult, current_state: str, collected_fields: dict
) -> ConversationTurnResult:
    if current_state not in STATE_ORDER:
        # Unknown state — reject any transition, hold in place, force low confidence.
        result.next_state = current_state
        result.confidence_flag = "low"
        return result

    current_idx = STATE_ORDER.index(current_state)
    proposed_idx = STATE_ORDER.index(result.next_state) if result.next_state in STATE_ORDER else None

    if proposed_idx is None or proposed_idx < current_idx:
        # Unknown or backward proposal — hold in place. Extracted fields still get merged
        # by the caller regardless of what next_state ends up being.
        result.next_state = current_state
        result.confidence_flag = "low"
        return result

    # A real lead often volunteers several answers in one message (e.g. describing two
    # services and their business in the same breath). Rejecting the whole turn back to
    # current_state the moment the model proposes jumping ahead left conversations
    # permanently stuck (see 2026-08-19 live test — state never left `greeting` for an
    # entire 9-message conversation because every proposed multi-hop jump kept getting
    # clamped back to square one, and greeting's empty REQUIRED_FIELDS meant the model was
    # never even told the real field key names for what it was extracting).
    #
    # Instead, walk forward through every state between current and proposed, advancing
    # only as far as the merged fields genuinely support — so a lead who over-answers still
    # makes real progress, but the funnel can't be skipped past a state whose required
    # fields (under their exact canonical keys) haven't actually been captured.
    merged = {**collected_fields, **result.extracted_fields}
    furthest_reachable = current_idx
    for idx in range(current_idx, proposed_idx):
        if not _fields_satisfied(STATE_ORDER[idx], merged):
            break
        furthest_reachable = idx + 1

    result.next_state = STATE_ORDER[furthest_reachable]
    if furthest_reachable < proposed_idx:
        result.confidence_flag = "low"
    return result
