"""Rule-based lead scoring — deliberately not LLM-judged. An LLM-derived numeric score is
opaque and hard to defend ("why did this lead score 72?"); a weighted rule set over
collected fields is fully auditable. See full blueprint Section 10.

Two revisions, both driven by live tests:

2026-08-22 (a): weights were a flat 25/25/25/25 with no scope dimension, so a lead asking for
something the practice does not build scored identically to a perfect-fit lead. Added
`scope_fit`, and cut `contact_verified` — every lead here arrives *inside a WhatsApp
conversation*, so a usable contact is near-guaranteed and cannot discriminate between leads.

2026-08-22 (b): the rubric measured *engagement*, not *viability*. A CA firm with a real
₹15,000 ceiling against a ₹35,000 floor, wanting delivery in 2 weeks against a 5-12 week
build, scored 87/100 — because stating a budget scored full marks regardless of whether the
number was workable, and urgency scored full marks regardless of whether the date was
achievable. Budget and timeline are now checked against the practice's actual limits, and
hard blockers are surfaced explicitly rather than being averaged away into a number.
"""

import re

QUALIFIED_THRESHOLD = 50

# The practice's real commercial floor and minimum build time, from company_knowledge /
# hoshangsheth.com. A lead below either isn't necessarily dead, but Hoshang must know before
# the call rather than discover it mid-conversation.
MIN_PROJECT_BUDGET_INR = 35_000
MIN_DELIVERY_WEEKS = 5

# The practice's own published range, used to detect a budget that is really just an echo of
# the number we anchored the lead to rather than a figure they arrived at themselves.
_PUBLISHED_RANGE_MARKERS = ("35", "90")

_SCOPE_POINTS = {
    "in_scope": 25,
    "partial": 12,
    "out_of_scope": 0,
    "unclear": 6,
}
_UNKNOWN_SCOPE_POINTS = 12

# service_type values that map unambiguously onto one of the four published applications.
# Used to derive scope_fit deterministically when the model didn't emit it — see
# _canonical_scope. Matched against an alphanumeric reduction, so "Document Processing",
# "document_processing" and "document processing" all hit the same entry.
_SERVICE_TYPE_TO_SCOPE = (
    ("customersupport", "in_scope"),
    ("support", "in_scope"),
    ("salesleadops", "in_scope"),
    ("leadops", "in_scope"),
    ("sales", "in_scope"),
    ("documentprocessing", "in_scope"),
    ("document", "in_scope"),
    ("internalknowledgeops", "in_scope"),
    ("internalops", "in_scope"),
    ("internalknowledge", "in_scope"),
    # Not one of the four applications, but real, delivered work (see company_knowledge.py
    # ADJACENT_OFFERINGS and hoshangsheth.com/work) — a website request must never be scored
    # as out-of-scope. See the 2026-08-22 Sneha Thakkar lead this was missing for.
    ("website", "in_scope"),
    ("webdevelopment", "in_scope"),
    ("webdesign", "in_scope"),
)

_MULTIPLIERS = (
    ("crore", 10_000_000), ("cr", 10_000_000),
    ("lakhs", 100_000), ("lakh", 100_000), ("lacs", 100_000), ("lac", 100_000),
    ("thousand", 1_000), ("k", 1_000),
)
_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(crore|cr|lakhs|lakh|lacs|lac|thousand|k)?", re.I)

# Below this, a number with no magnitude attached ("15", "around 50") is shorthand, not a
# rupee figure — see parse_budget_inr. A bare "50000" is unambiguous and still trusted.
_BARE_NUMBER_FLOOR = 1_000

_WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "couple": 2, "three": 3, "few": 3,
                 "four": 4, "five": 5, "six": 6}
_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?|a|an|one|two|couple|three|few|four|five|six)\s*(day|week|month|year)s?",
    re.I,
)
_WEEKS_PER = {"day": 1 / 7, "week": 1.0, "month": 4.345, "year": 52.0}
# "ASAP" carries no number but unambiguously means sooner than any real build could ship.
_IMMEDIATE_MARKERS = ("asap", "immediate", "right away", "yesterday", "tomorrow")


def _reduce(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def parse_budget_inr(raw: str) -> int | None:
    """Best-effort rupee value from free text ("15k INR max", "1.2 lakhs", "50-60k").

    Returns the LARGEST amount mentioned — the most generous reading of what the lead can
    spend. If even their ceiling is under the floor, the mismatch is real and not an artifact
    of parsing the low end of a range. Returns None when no number is present at all
    ("not disclosed"), which is deliberately different from "stated, and too low".
    """
    if not raw:
        return None
    text = raw.replace(",", "").lower()
    if not any(ch.isdigit() for ch in text):
        return None

    amounts = []
    for number, multiplier in _AMOUNT_RE.findall(text):
        try:
            value = float(number)
        except ValueError:
            continue
        if multiplier:
            for name, factor in _MULTIPLIERS:
                if multiplier == name:
                    value *= factor
                    break
        elif value < _BARE_NUMBER_FLOOR:
            # A bare "15" or "around 50" means 15k/50k to every Indian SMB owner who types
            # it, but reading it literally is worse than not reading it at all: until
            # 2026-09-08 this returned ₹50 for "around 50", scored the lead 0 for budget,
            # and put "Budget ₹50 is below the ₹35,000 floor" in Hoshang's notification.
            # Guessing the magnitude would be worse still (this file's whole point is being
            # defensible), so an ambiguous figure is simply not treated as a figure — it
            # falls through to "not disclosed", which is the honest reading.
            continue
        amounts.append(value)

    if not amounts:
        return None
    return int(max(amounts))


def parse_timeline_weeks(raw: str) -> float | None:
    """Best-effort deadline in weeks. Returns the LONGEST duration mentioned, so a lead
    saying "1 to 2 months" is judged on the outer bound they'd actually accept."""
    if not raw:
        return None
    text = raw.lower()
    durations = []
    for amount, unit in _DURATION_RE.findall(text):
        value = _WORD_NUMBERS.get(amount) if amount in _WORD_NUMBERS else float(amount)
        if value is None:
            continue
        durations.append(value * _WEEKS_PER[unit])
    if durations:
        return max(durations)
    if any(marker in text for marker in _IMMEDIATE_MARKERS):
        return 1.0
    return None


def _canonical_scope(collected_fields: dict) -> str:
    """The canonical scope_fit key, or "unknown".

    Falls back to deriving scope from service_type when the model didn't emit scope_fit.
    On 2026-08-22 a textbook Document Processing lead (invoices into Tally) was scored
    "unclassified" purely because an earlier drift meant the service_requirement turn
    finished without the field, and the funnel never revisits a passed state. service_type
    was literally "Document Processing" — one of the four published applications — so the
    answer was already sitting in the data. Don't ask the model for what you can compute.
    """
    raw = _reduce(collected_fields.get("scope_fit") or "")
    for canonical in _SCOPE_POINTS:
        if raw == canonical.replace("_", ""):
            return canonical

    service_type = _reduce(collected_fields.get("service_type") or "")
    if service_type and service_type not in ("unclear", "unknown", "other", "otherunsure"):
        for marker, scope in _SERVICE_TYPE_TO_SCOPE:
            if marker in service_type:
                return scope
    return "unknown"


def _scope_points(collected_fields: dict) -> int:
    """An unrecognized/underivable scope scores as "unknown" (partial credit) rather than 0 —
    a lead must never be penalised for a field the model forgot. Unknown lands mid-range so a
    missing field can neither silently promote a bad lead nor bury a good one."""
    return _SCOPE_POINTS.get(_canonical_scope(collected_fields), _UNKNOWN_SCOPE_POINTS)


def _budget_points(collected_fields: dict) -> int:
    """Rewards a budget that can actually fund the work, not merely the act of naming one.

    A stated-but-unaffordable budget used to score the same 20 as a healthy one. It is now
    the weakest outcome of all — worse than staying silent, because silence might still hide
    real money whereas ₹15,000 against a ₹35,000 floor cannot.

    A lead who says "I don't know", gets quoted ₹35,000-₹90,000, then agrees to that range,
    has not disclosed a budget: they accepted ours. Scored between the two.
    """
    raw = (collected_fields.get("budget_range") or "").strip().lower()
    if not raw or raw in ("not disclosed", "none", "unknown", "n/a"):
        return 5

    amount = parse_budget_inr(raw)
    if amount is not None and amount < MIN_PROJECT_BUDGET_INR:
        return 0

    digits_only = "".join(ch for ch in raw if ch.isdigit())
    if all(marker in digits_only for marker in _PUBLISHED_RANGE_MARKERS):
        return 10
    return 20


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
    """Urgency from free text, not an exact "urgent" string match.

    The model stores what the lead actually said ("within a month", "before our audit"), so
    `timeline == "urgent"` only ever fired when they happened to use that exact word.

    Urgency stays a positive signal even when the date is unachievable — a motivated buyer is
    still a buyer, and they may well move their date once they hear the real timeline. The
    infeasibility is reported as a blocker instead, so it reaches Hoshang as a fact to raise
    on the call rather than as a silent deduction he can't see.
    """
    timeline = (collected_fields.get("timeline_expectation") or "").strip().lower()
    if not timeline or timeline in ("none", "not disclosed", "unknown"):
        return 0
    if any(marker in timeline for marker in _NOT_URGENT_MARKERS):
        return 7
    if any(marker in timeline for marker in _URGENT_MARKERS):
        return 15
    return 7


def _blockers(collected_fields: dict) -> list[str]:
    """Hard commercial mismatches, stated plainly for the notification email.

    A single number cannot express "perfect fit, cannot pay" — averaging a dealbreaker into a
    score just hides it. These are the things that decide whether a call is worth booking, so
    they get surfaced as their own list rather than inferred from the total.
    """
    blockers = []

    amount = parse_budget_inr(collected_fields.get("budget_range") or "")
    if amount is not None and amount < MIN_PROJECT_BUDGET_INR:
        blockers.append(
            f"Budget ₹{amount:,} is below the ₹{MIN_PROJECT_BUDGET_INR:,} floor"
        )

    weeks = parse_timeline_weeks(collected_fields.get("timeline_expectation") or "")
    if weeks is not None and weeks < MIN_DELIVERY_WEEKS:
        rounded = int(weeks) if float(weeks).is_integer() else round(weeks, 1)
        blockers.append(
            f"Wants delivery in ~{rounded} week(s); typical build is {MIN_DELIVERY_WEEKS}-12 weeks"
        )

    if _canonical_scope(collected_fields) == "out_of_scope":
        blockers.append("Request is outside what the practice builds")

    return blockers


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
        # Surfaced separately from the score so the notification email can lead with them.
        # Neither is something Hoshang should have to infer from a number — both change how
        # he opens the call, or whether he takes it at all.
        "scope_flag": _canonical_scope(collected_fields),
        "blockers": _blockers(collected_fields),
    }
