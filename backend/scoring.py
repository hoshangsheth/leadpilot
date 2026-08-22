"""Rule-based lead scoring — deliberately not LLM-judged. An LLM-derived numeric score is
opaque and hard to defend ("why did this lead score 72?"); a weighted rule set over
collected fields is fully auditable. See full blueprint Section 10.

Weights were rebalanced on 2026-08-22 after a live test exposed two problems with the
original flat 25/25/25/25 split:

1. `contact_verified` was worth as much as the actual business signal, but it is very nearly
   free — every lead here arrives *inside a WhatsApp conversation*, so a usable contact is
   almost guaranteed the moment they give a name. A dimension that ~every lead passes cannot
   discriminate between leads, it just inflates everyone's score.
2. There was no scope dimension at all, so a lead asking for something the practice does not
   build scored identically to a perfect-fit lead. The AutoCAD-to-3D lead scored 85/100.

`scope_fit` is now the largest single dimension, because fit is the thing that most strongly
predicts whether a conversation can actually become a paid project.
"""

QUALIFIED_THRESHOLD = 50

# The practice's own published range, used to detect a budget that is really just an echo of
# the number we anchored the lead to rather than a figure they arrived at themselves.
_PUBLISHED_RANGE_MARKERS = ("35", "90")


def _budget_points(collected_fields: dict) -> int:
    """Full credit for a budget the lead actually owns, partial for one they merely agreed to.

    A lead who says "I don't know what this costs", gets quoted ₹35,000-₹90,000, and then says
    "that range works" has not disclosed a budget — they have accepted ours. That is a weaker
    buying signal than someone who names their own number, and it used to score identically.
    Detected deterministically by checking whether the captured range is essentially our own
    published bracket played back; anything else counts as genuinely self-stated.
    """
    budget = (collected_fields.get("budget_range") or "").strip().lower()
    if not budget or budget in ("not disclosed", "none", "unknown"):
        return 0

    digits_only = "".join(ch for ch in budget if ch.isdigit())
    echoes_published_range = all(marker in digits_only for marker in _PUBLISHED_RANGE_MARKERS)
    return 10 if echoes_published_range else 20


def _scope_points(collected_fields: dict) -> int:
    """How well the ask matches what Hoshang actually builds.

    An absent scope_fit scores as "unknown" (partial credit, 12) rather than 0 — the field is
    optional by design (see states/service_requirement.py), and a lead must never be penalised
    for the model forgetting to emit a key. Unknown lands mid-range so a missing field cannot
    silently promote a bad lead or bury a good one.
    """
    scope_fit = (collected_fields.get("scope_fit") or "").strip().lower()
    return {
        "in_scope": 25,
        "partial": 12,
        "out_of_scope": 0,
        "unclear": 6,
    }.get(scope_fit, 12)


def score_lead(collected_fields: dict) -> dict:
    breakdown = {}

    service_type = (collected_fields.get("service_type") or "").strip().lower()
    has_clear_pain = bool(collected_fields.get("requirement_summary")) and service_type != "unclear"
    breakdown["clear_pain_point"] = 25 if has_clear_pain else 0

    breakdown["scope_fit"] = _scope_points(collected_fields)
    breakdown["budget_disclosed"] = _budget_points(collected_fields)

    timeline = (collected_fields.get("timeline_expectation") or "").strip().lower()
    if timeline == "urgent":
        breakdown["timeline_urgency"] = 15
    elif timeline:
        breakdown["timeline_urgency"] = 7
    else:
        breakdown["timeline_urgency"] = 0

    has_contact = bool(collected_fields.get("contact_name")) and bool(
        collected_fields.get("contact_preference")
    )
    breakdown["contact_verified"] = 15 if has_contact else 0

    total = sum(breakdown.values())
    return {
        "score": total,
        "breakdown": breakdown,
        "qualified": total >= QUALIFIED_THRESHOLD,
        # Surfaced separately from the score so the notification email can lead with it.
        # A scope mismatch is not something Hoshang should have to infer from a number —
        # it changes how he opens the call.
        "scope_flag": (collected_fields.get("scope_fit") or "unknown").strip().lower(),
    }
