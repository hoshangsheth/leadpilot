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


_SCOPE_POINTS = {
    "in_scope": 25,
    "partial": 12,
    "out_of_scope": 0,
    "unclear": 6,
}
_UNKNOWN_SCOPE_POINTS = 12


def _canonical_scope(collected_fields: dict) -> str:
    """The canonical scope_fit key, or "unknown" if absent/unrecognized."""
    raw = (collected_fields.get("scope_fit") or "").strip().lower()
    reduced = "".join(ch for ch in raw if ch.isalnum())
    for canonical in _SCOPE_POINTS:
        if reduced == canonical.replace("_", ""):
            return canonical
    return "unknown"


def _scope_points(collected_fields: dict) -> int:
    """How well the ask matches what Hoshang actually builds.

    Values are canonicalized upstream (conversation_engine.normalize_field_values), but this
    reduction is repeated here rather than assumed: scoring also runs over rows written before
    that normalization existed, and over the message-cap forced-handoff path. Comparing an
    LLM-sourced enum with == is what caused the 2026-08-22 misscore in the first place.

    An unrecognized/absent scope_fit scores as "unknown" (partial credit) rather than 0 — the
    field is optional by design (see states/service_requirement.py), and a lead must never be
    penalised for the model forgetting a key. Unknown lands mid-range so a missing field can
    neither silently promote a bad lead nor bury a good one.
    """
    raw = (collected_fields.get("scope_fit") or "").strip().lower()
    reduced = "".join(ch for ch in raw if ch.isalnum())
    for canonical, points in _SCOPE_POINTS.items():
        if reduced == canonical.replace("_", ""):
            return points
    return _UNKNOWN_SCOPE_POINTS


# Checked before the urgent markers, so "no specific timeline, but not months away" is not
# scored urgent just because it contains the word "month".
_NOT_URGENT_MARKERS = (
    "flexible", "no specific", "no rush", "not urgent", "no timeline",
    "exploring", "just looking", "sometime", "no deadline", "whenever",
)
_URGENT_MARKERS = (
    "urgent", "asap", "immediate", "as soon as", "right away", "priority",
    "this week", "this month", "next month", "within a week", "within a month",
    "within 1 month", "within one month", "deadline", "audit", "launch",
    "before ", "by end of", "1 month", "one month", "2 week", "two week",
)


def _timeline_points(collected_fields: dict) -> int:
    """Urgency from free-text timeline, not an exact "urgent" string match.

    The model stores what the lead actually said ("within a month", "need it live before our
    audit"), not a normalized enum, so `timeline == "urgent"` only ever fired when the lead
    happened to use that exact word. A retail lead with a hard audit deadline one month out
    scored the same 7 points as someone with no timeline at all.
    """
    timeline = (collected_fields.get("timeline_expectation") or "").strip().lower()
    if not timeline or timeline in ("none", "not disclosed", "unknown"):
        return 0
    if any(marker in timeline for marker in _NOT_URGENT_MARKERS):
        return 7
    if any(marker in timeline for marker in _URGENT_MARKERS):
        return 15
    return 7


def score_lead(collected_fields: dict) -> dict:
    breakdown = {}

    service_type = (collected_fields.get("service_type") or "").strip().lower()
    has_clear_pain = bool(collected_fields.get("requirement_summary")) and service_type != "unclear"
    breakdown["clear_pain_point"] = 25 if has_clear_pain else 0

    breakdown["scope_fit"] = _scope_points(collected_fields)
    breakdown["budget_disclosed"] = _budget_points(collected_fields)
    breakdown["timeline_urgency"] = _timeline_points(collected_fields)

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
        # it changes how he opens the call. Canonicalized through the same reduction as the
        # points lookup, so the email's banner can never miss on a value the scorer matched.
        "scope_flag": _canonical_scope(collected_fields),
    }
