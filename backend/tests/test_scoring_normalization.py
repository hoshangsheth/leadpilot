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
from integrations.email_service import _scope_banner_html, send_lead_notification_email  # noqa: E402


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

    def test_absent_and_underivable_scope_fit_is_neutral_not_zero(self):
        """The field is optional by design — a forgotten key must not bury a real lead.

        Uses a service_type that cannot be derived (see TestScopeDerivedFromServiceType for
        the derivable case), so this exercises the genuine last-resort fallback.
        """
        result = scoring.score_lead({"service_type": "Other / Unsure", "requirement_summary": "x"})
        assert result["breakdown"]["scope_fit"] == 12
        assert result["scope_flag"] == "unknown"


class TestBudgetAnchoring:
    def test_echoing_our_published_range_scores_lower_than_a_real_number(self):
        anchored = scoring.score_lead({"budget_range": "35,000 to 90,000 INR"})["breakdown"]["budget_disclosed"]
        self_stated = scoring.score_lead({"budget_range": "1.2 lakhs"})["breakdown"]["budget_disclosed"]
        assert anchored < self_stated

    def test_undisclosed_budget_is_neither_rewarded_nor_treated_as_unaffordable(self):
        """Silence scores low but above a known-unaffordable number — a lead who won't say
        may still have money, whereas ₹15k against a ₹35k floor definitively does not."""
        for value in ("", "not disclosed", "unknown"):
            points = scoring.score_lead({"budget_range": value})["breakdown"]["budget_disclosed"]
            assert points == 5, value


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


class TestScopeDerivedFromServiceType:
    """2026-08-22: a textbook Document Processing lead (200+ invoices into Tally) came back
    "unclassified" because an earlier drift meant service_requirement finished its turn
    without scope_fit, and the funnel never revisits a passed state. service_type already
    held the answer."""

    def test_canonical_service_type_derives_in_scope(self):
        for service_type in ("Document Processing", "customer support",
                             "sales/lead ops", "Internal Knowledge & Ops"):
            result = scoring.score_lead({
                "service_type": service_type, "requirement_summary": "x",
            })
            assert result["scope_flag"] == "in_scope", service_type

    def test_model_emitted_scope_fit_wins_over_derivation(self):
        """An explicit out_of_scope must not be overridden by a tidy-looking service_type."""
        result = scoring.score_lead({
            "service_type": "document processing", "scope_fit": "Out of scope",
        })
        assert result["scope_flag"] == "out_of_scope"

    def test_non_canonical_service_type_stays_unknown(self):
        for service_type in ("Other / Unsure", "unclear", "3D/CAD rendering"):
            result = scoring.score_lead({"service_type": service_type})
            assert result["scope_flag"] == "unknown", service_type


class TestBudgetViability:
    """Stating a budget used to score full marks regardless of whether it could fund a build."""

    def test_parses_indian_formats(self):
        assert scoring.parse_budget_inr("15k INR max") == 15_000
        assert scoring.parse_budget_inr("1.2 lakhs") == 120_000
        assert scoring.parse_budget_inr("50-60k") == 60_000
        assert scoring.parse_budget_inr("not disclosed") is None

    def test_below_floor_scores_worse_than_saying_nothing(self):
        """₹15k cannot fund a ₹35k+ build; silence might still hide real money."""
        below = scoring.score_lead({"budget_range": "15k max"})["breakdown"]["budget_disclosed"]
        silent = scoring.score_lead({"budget_range": "not disclosed"})["breakdown"]["budget_disclosed"]
        viable = scoring.score_lead({"budget_range": "60k"})["breakdown"]["budget_disclosed"]
        assert below < silent < viable

    def test_below_floor_raises_a_blocker(self):
        blockers = scoring.score_lead({"budget_range": "15k INR max"})["blockers"]
        assert any("below the" in b for b in blockers)


class TestTimelineFeasibility:
    def test_parses_durations_to_weeks(self):
        assert scoring.parse_timeline_weeks("urgent, within 2 weeks") == 2.0
        assert scoring.parse_timeline_weeks("ASAP") == 1.0
        assert scoring.parse_timeline_weeks("1-2 months") > 8
        assert scoring.parse_timeline_weeks("flexible") is None

    def test_deadline_shorter_than_min_build_raises_a_blocker(self):
        blockers = scoring.score_lead({"timeline_expectation": "urgent, within 2 weeks"})["blockers"]
        assert any("typical build" in b for b in blockers)

    def test_realistic_deadline_raises_no_blocker(self):
        assert scoring.score_lead({"timeline_expectation": "2 months"})["blockers"] == []


class TestTheCAFirmLead:
    """The 2026-08-22 lead that scored 87/100 while being unable to pay or wait."""

    def test_perfect_fit_impossible_terms_is_flagged_not_averaged(self):
        result = scoring.score_lead({
            "service_type": "Document Processing",
            "requirement_summary": "200+ monthly vendor invoices into Tally",
            "business_size": "3 people",
            "budget_range": "15k INR max",
            "timeline_expectation": "urgent, within 2 weeks",
            "contact_name": "Meera Iyer",
            "contact_preference": "email, meera@example.com",
        })
        assert result["scope_flag"] == "in_scope", "genuinely a document-processing lead"
        assert result["breakdown"]["budget_disclosed"] == 0, "₹15k cannot fund a ₹35k+ build"
        assert len(result["blockers"]) == 2, "budget AND timeline are both dealbreakers"


class TestUnqualifiedLeadsAreNotified:
    """A real prospect (Sneha Thakkar, 2026-08-22) scored 35/100, and the notification email
    was gated on qualified=True, so Hoshang received nothing. The bot still told her "that
    gives him everything he needs" — a promise that was false, because the email that would
    have made it true never fired. She messaged again 17 minutes later asking when she'd hear
    back, into a conversation nobody but her could see.

    The threshold should decide whether a lead gets a self-service Calendly link, not whether
    Hoshang is told a real person reached out. These tests exist so an unqualified lead going
    silent can never again be an unintentional consequence of the qualified/not branch.
    """

    def test_the_exact_lead_that_went_unnotified(self):
        from unittest.mock import patch

        sneha_fields = {
            "service_type": "unclear", "requirement_summary": "looking to build a website",
            "scope_fit": "out_of_scope", "business_size": "12 people",
            "budget_range": "not disclosed", "timeline_expectation": "within a month",
            "contact_name": "Sneha Thakkar", "contact_preference": "Call / WhatsApp, same number",
        }
        result = scoring.score_lead(sneha_fields)
        assert not result["qualified"], "sanity check: this must reproduce the low score"

        with patch("integrations.email_service.resend.Emails.send") as mock:
            send_lead_notification_email("918850037690", sneha_fields, result)
            assert mock.called, "an unqualified lead must still generate a notification"
            subject = mock.call_args[0][0]["subject"]
            assert "UNQUALIFIED" in subject

    def test_qualified_lead_email_is_unaffected(self):
        from unittest.mock import patch

        good_fields = {
            "service_type": "customer support", "requirement_summary": "x",
            "budget_range": "70k", "timeline_expectation": "2 months",
            "contact_name": "P", "contact_preference": "p@q.com", "scope_fit": "in_scope",
        }
        result = scoring.score_lead(good_fields)
        assert result["qualified"]

        with patch("integrations.email_service.resend.Emails.send") as mock:
            send_lead_notification_email("919999999999", good_fields, result)
            subject = mock.call_args[0][0]["subject"]
            assert "UNQUALIFIED" not in subject
            assert "New Qualified Lead" in subject


class TestEmailBanner:
    def test_every_flag_renders_a_banner(self):
        for flag in ("in_scope", "partial", "out_of_scope", "unclear", "unknown"):
            assert _scope_banner_html(flag), flag

    def test_unrecognized_flag_is_never_silent(self):
        """Silence reads as 'all fine' — the exact reason the original bug went unnoticed."""
        assert "not classified" in _scope_banner_html("something-new")
