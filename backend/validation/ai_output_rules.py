"""Business-rule validation, run after schema validation. Catches schema-valid but
nonsensical proposed transitions — e.g. Gemini proposing to advance past a state without
the fields that state requires. See full blueprint Section 10."""

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


def validate_turn_result(
    result: ConversationTurnResult, current_state: str, collected_fields: dict
) -> ConversationTurnResult:
    module = STATE_MODULES.get(current_state)
    if module is None:
        # Unknown state — reject any transition, hold in place, force low confidence.
        result.next_state = current_state
        result.confidence_flag = "low"
        return result

    if result.next_state not in module.ALLOWED_NEXT:
        result.next_state = current_state
        result.confidence_flag = "low"
        return result

    if result.next_state != current_state:
        merged = {**collected_fields, **result.extracted_fields}
        missing = [f for f in module.REQUIRED_FIELDS if f not in merged or not merged[f]]
        if missing:
            result.next_state = current_state
            result.confidence_flag = "low"
        elif hasattr(module, "extra_check") and not module.extra_check(merged):
            # Required fields are all present but content-quality checks failed — e.g.
            # contact_preference says "email" with no actual email address attached.
            # Presence isn't the same as usable.
            result.next_state = current_state
            result.confidence_flag = "low"

    return result
