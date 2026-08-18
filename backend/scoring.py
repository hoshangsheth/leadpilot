# Rule-based lead scoring — deliberately not LLM-judged. An LLM-derived numeric score is
# opaque and hard to defend ("why did this lead score 72?"); a weighted rule set over
# collected fields is fully auditable. See full blueprint Section 10.

QUALIFIED_THRESHOLD = 50

KNOWN_SERVICE_TYPES = {
    "customer support",
    "sales/lead ops",
    "document processing",
    "internal knowledge/ops",
}


def score_lead(collected_fields: dict) -> dict:
    breakdown = {}

    service_type = (collected_fields.get("service_type") or "").strip().lower()
    has_clear_pain = bool(collected_fields.get("requirement_summary")) and service_type != "unclear"
    breakdown["clear_pain_point"] = 25 if has_clear_pain else 0

    budget = (collected_fields.get("budget_range") or "").strip().lower()
    has_budget = bool(budget) and budget != "not disclosed"
    breakdown["budget_disclosed"] = 25 if has_budget else 0

    timeline = (collected_fields.get("timeline_expectation") or "").strip().lower()
    if timeline == "urgent":
        breakdown["timeline_urgency"] = 25
    elif timeline:
        breakdown["timeline_urgency"] = 10
    else:
        breakdown["timeline_urgency"] = 0

    has_contact = bool(collected_fields.get("contact_name")) and bool(
        collected_fields.get("contact_preference")
    )
    breakdown["contact_verified"] = 25 if has_contact else 0

    total = sum(breakdown.values())
    return {
        "score": total,
        "breakdown": breakdown,
        "qualified": total >= QUALIFIED_THRESHOLD,
    }
