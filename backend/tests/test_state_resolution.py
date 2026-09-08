"""Tests for resolve_effective_state's forward walk.

2026-09-08: the greeting state was being skipped on the very first message of every real
conversation. message_handler stamps `lead_source` onto collected_fields before the engine
runs, and the walk's "has this conversation produced anything yet?" check was a bare
truthiness test on the dict — so it was always true, greeting auto-advanced, and the opening
question came from service_requirement's prompt instead. Every test that passed empty fields
showed the greeting working perfectly, which is why it survived so long.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation.ai_output_rules import resolve_effective_state  # noqa: E402


class TestGreetingIsNotSkippedBySystemMetadata:
    def test_lead_source_alone_does_not_advance_past_greeting(self):
        """lead_source is written by the system, not answered by the lead."""
        fields = {"lead_source": "Direct message (typed manually, source unconfirmed)"}
        assert resolve_effective_state("greeting", fields) == "greeting"

    def test_internal_bookkeeping_does_not_advance_past_greeting(self):
        fields = {"_notes_retry_count": 2, "_awaiting_bypass_name": True}
        assert resolve_effective_state("greeting", fields) == "greeting"

    def test_no_fields_at_all_stays_in_greeting(self):
        assert resolve_effective_state("greeting", {}) == "greeting"

    def test_a_real_answer_still_advances(self):
        """The original behaviour this check exists for must survive the fix."""
        fields = {
            "lead_source": "Website CTA",
            "service_type": "customer support",
            "requirement_summary": "answering repeat questions on WhatsApp",
        }
        assert resolve_effective_state("greeting", fields) == "business_context"

    def test_walk_stops_at_the_first_unsatisfied_state(self):
        fields = {
            "service_type": "document processing",
            "requirement_summary": "invoices from Gmail into a database",
            "company_name": "GB Bags",
            "business_size": "30-40 people",
        }
        assert resolve_effective_state("greeting", fields) == "budget"

    def test_additional_notes_is_never_auto_skipped(self):
        """It has no required fields of its own, so nothing proves its turn happened — the
        closing "anything else?" question must always actually get asked."""
        fields = {
            "service_type": "document processing",
            "requirement_summary": "invoices into a database",
            "company_name": "GB Bags",
            "business_size": "30-40 people",
            "budget_range": "50k",
            "timeline_expectation": "within a month",
            "contact_name": "Sam Shah",
            "contact_preference": "Phone call at 8838393930",
        }
        assert resolve_effective_state("greeting", fields) == "additional_notes"
