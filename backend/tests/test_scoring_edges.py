"""Regression tests for three scoring bugs found in the 2026-09-08 audit.

All three shared a shape: the code did something subtly different from what its own comment
claimed, and the only symptom was a slightly wrong number or an odd line in an email that
nobody would think to question.

Run: venv/Scripts/python.exe -m pytest tests/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring import parse_budget_inr, score_lead  # noqa: E402

_BASE = {
    "requirement_summary": "extract vendor invoices from Gmail into a database",
    "service_type": "document processing",
    "contact_name": "Sam Shah",
    "contact_preference": "Phone call at 8838393930",
}


class TestBareNumberBudgets:
    """parse_budget_inr's comment said it only trusted explicit magnitudes; it didn't.
    "around 50" parsed as ₹50, scored 0 for budget, and produced the blocker
    "Budget ₹50 is below the ₹35,000 floor"."""

    def test_bare_shorthand_is_not_read_literally(self):
        for raw in ["15", "around 50", "50-60", "maybe 40"]:
            assert parse_budget_inr(raw) is None, raw

    def test_explicit_magnitudes_still_parse(self):
        assert parse_budget_inr("15k max") == 15_000
        assert parse_budget_inr("40 to 50k") == 50_000
        assert parse_budget_inr("2 lakhs") == 200_000

    def test_unambiguous_full_figures_still_parse(self):
        assert parse_budget_inr("50000") == 50_000

    def test_no_nonsense_blocker_for_shorthand(self):
        result = score_lead({**_BASE, "budget_range": "around 50"})
        assert result["blockers"] == []

    def test_a_real_lowball_is_still_blocked(self):
        result = score_lead({**_BASE, "budget_range": "15k max"})
        assert any("below" in b for b in result["blockers"])


class TestPublishedRangeEcho:
    """The echo check tested whether the digit string contained "35" and "90" anywhere, so
    genuine figures that happened to share those digits were marked down as if the lead had
    just read our own range back to us."""

    def test_echoing_our_range_is_discounted(self):
        result = score_lead({**_BASE, "budget_range": "35,000 to 90,000"})
        assert result["breakdown"]["budget_disclosed"] == 10

    def test_a_real_figure_sharing_digits_is_not(self):
        for raw in ["90350", "1,35,900"]:
            result = score_lead({**_BASE, "budget_range": raw})
            assert result["breakdown"]["budget_disclosed"] == 20, raw


class TestMissingServiceType:
    """An empty service_type simply isn't the literal string "unclear", so it passed the
    clear-pain check and scored the full 25 — a lead the model never classified scored the
    same as a perfectly classified one."""

    def test_missing_service_type_scores_zero_for_pain(self):
        result = score_lead({**_BASE, "service_type": ""})
        assert result["breakdown"]["clear_pain_point"] == 0

    def test_explicit_non_answers_score_zero_too(self):
        for value in ["unclear", "unknown", "n/a", "none"]:
            result = score_lead({**_BASE, "service_type": value})
            assert result["breakdown"]["clear_pain_point"] == 0, value

    def test_a_real_service_type_still_scores(self):
        result = score_lead(_BASE)
        assert result["breakdown"]["clear_pain_point"] == 25


class TestBlockerPhrasing:
    def test_timeline_blocker_reads_like_a_person(self):
        result = score_lead({**_BASE, "timeline_expectation": "within a month or so"})
        blocker = next(b for b in result["blockers"] if "delivery" in b)
        assert "about a month" in blocker
        assert "4.3" not in blocker
