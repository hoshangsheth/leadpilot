"""Regression tests for the 2026-08-22 scope_fit normalization bug.

The model classified a CCTV/video-analytics lead correctly and emitted
scope_fit="Out of scope". Scoring compared it against a dict keyed "out_of_scope",
missed, and fell through to the neutral default: the lead scored 79 instead of 75,
and the notification email silently lost both its red banner and its subject prefix.
The model was right; the plumbing discarded the answer.

These tests exist because that failure was invisible — nothing errored, nothing logged,
and the only symptom was a number being slightly too high in an email. Any future change
that reintroduces == comparison on an LLM-sourced enum should fail here instead.

Run: venv/Scripts/python.exe -m pytest tests/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scoring  # noqa: E402
from conversation_engine import normalize_field_values  # noqa: E402
from integrations.email_service import _scope_banner_html  # noqa: E402


class TestScopeValueNormalization:
    """An enum crossing an LLM boundary must survive casing, spacing and punctuation."""

    def test_model_phrasing_variants_all_canonicalize(self):
        for raw in ["Out of scope", "out-of-scope", "OUT_OF_SCOPE", "OutOfScope", "outside scope"]:
            assert normalize_field_values({"scope_fit": raw})["scope_fit"] == "out_of_scope", raw

        for raw in ["In Scope", "in-scope", "IN_SCOPE", "fits"]:
            assert normalize_field_values({"scope_fit": raw})["scope_fit"] == "in_scope", raw

        for raw in ["Partial", "partial fit", "adjacent"]:
            assert normalize_field_values({"scope_fit": raw})["scope_fit"] == "partial", raw

        for raw in ["Unclear", "unknown", "Unsure", "TBD"]:
            assert normalize_field_values({"scope_fit": raw})["scope_fit"] == "unclear", raw

    def test_free_text_fields_are_never_rewritten(self):
        """Only registered enum fields get canonicalized; prose must pass through intact."""
        summary = "Out of scope means nothing here, this is free text"
        assert normalize_field_values({"requirement_summary": summary})["requirement_summary"] == summary

    def test_unrecognized_enum_value_passes_through(self):
        assert normalize_field_values({"scope_fit": "banana"})["scope_fit"] == "banana"


class TestScopeScoring:
    def test_the_exact_lead_that_misscored(self):
        """Raw un-normalized value, exactly as the model emitted it on 2026-08-22."""
        result = scoring.score_lead({
            "service_type": "Other / Unsure",
            "requirement_summary": "CCTV footfall counting and loitering flags across 4 stores",
            "budget_range": "1.2 lakhs",
            "timeline_expectation": "within a month",
            "contact_name": "Ajay Deshmukh",
            "contact_preference": "WhatsApp, this number",
            "scope_fit": "Out of scope",
        })
        assert result["breakdown"]["scope_fit"] == 0, "out-of-scope must score zero, not the default"
        assert result["scope_flag"] == "out_of_scope", "flag drives the email banner"

    def test_out_of_scope_never_outranks_in_scope(self):
        base = dict(
            service_type="customer support", requirement_summary="x", budget_range="60k",
            timeline_expectation="urgent", contact_name="A", contact_preference="a@b.com",
        )
        scores = {
            fit: scoring.score_lead({**base, "scope_fit": fit})["score"]
            for fit in ("in_scope", "partial", "unclear", "out_of_scope")
        }
        assert scores["in_scope"] > scores["partial"] > scores["unclear"] > scores["out_of_scope"]

    def test_absent_scope_fit_is_neutral_not_zero(self):
        """The field is optional by design — a forgotten key must not bury a real lead."""
        result = scoring.score_lead({"service_type": "customer support", "requirement_summary": "x"})
        assert result["breakdown"]["scope_fit"] == 12
        assert result["scope_flag"] == "unknown"


class TestBudgetAnchoring:
    def test_echoing_our_published_range_scores_lower_than_a_real_number(self):
        anchored = scoring.score_lead({"budget_range": "35,000 to 90,000 INR"})["breakdown"]["budget_disclosed"]
        self_stated = scoring.score_lead({"budget_range": "1.2 lakhs"})["breakdown"]["budget_disclosed"]
        assert anchored < self_stated

    def test_no_budget_scores_zero(self):
        for value in ("", "not disclosed", "unknown"):
            assert scoring.score_lead({"budget_range": value})["breakdown"]["budget_disclosed"] == 0


class TestTimelineUrgency:
    def test_deadline_language_counts_as_urgent_without_the_word_urgent(self):
        for value in ["within a month", "need it before our audit", "ASAP", "2 weeks"]:
            assert scoring._timeline_points({"timeline_expectation": value}) == 15, value

    def test_negations_are_not_misread_as_urgent(self):
        """'no rush but not months away' contains 'month' but is not a deadline."""
        for value in ["no specific timeline", "flexible", "no rush but not months away", "sometime next year"]:
            assert scoring._timeline_points({"timeline_expectation": value}) == 7, value

    def test_absent_timeline_scores_zero(self):
        assert scoring._timeline_points({}) == 0


class TestEmailBanner:
    def test_every_flag_renders_a_banner(self):
        for flag in ("in_scope", "partial", "out_of_scope", "unclear", "unknown"):
            assert _scope_banner_html(flag), flag

    def test_unrecognized_flag_is_never_silent(self):
        """Silence reads as 'all fine' — the exact reason the original bug went unnoticed."""
        assert "not classified" in _scope_banner_html("something-new")
