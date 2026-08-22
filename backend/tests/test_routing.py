"""Tests for pre-funnel routing: warm-contact bypass and free attribution.

The bypass patterns carry real asymmetric risk. A false NEGATIVE means a referral gets asked
for their budget by a robot — bad, but recoverable once Hoshang sees the transcript. A false
POSITIVE means a genuine cold lead is dropped out of qualification entirely and silently waits
on a human. Both directions are pinned here, with the deliberately-hard near-misses called out.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routing import detect_bypass, detect_source, BYPASS_REPLIES  # noqa: E402
from conversation_engine import ensure_bot_disclosure  # noqa: E402


class TestBotDisclosure:
    """2026-08-22: a bare "hi" produced an opener with no bot disclosure at all — the model
    traded it away against the general brevity rule. Whether someone knows they are talking
    to a bot is not a style choice, so it is enforced in code."""

    def test_missing_disclosure_is_injected(self):
        reply = "Hi there! What process are you looking to automate?"
        assert "ai assistant" in ensure_bot_disclosure(reply).lower()

    def test_existing_disclosure_is_left_alone(self):
        reply = "Hi there, I'm Hoshang's AI assistant. What do you want to automate?"
        assert ensure_bot_disclosure(reply) == reply

    def test_detection_is_case_insensitive(self):
        reply = "Hi, I am Hoshang's ai assistant here to help."
        assert ensure_bot_disclosure(reply) == reply


class TestWarmContactBypass:
    def test_personal_connection_bypasses(self):
        for message in [
            "Hi, I am a friend of Hoshang",
            "Rahul gave me your number",
            "tell hoshang its Priya from Mulund",
            "Hoshang knows me, we met at the meetup",
            "Amit referred me",
            "we know each other from college",
        ]:
            assert detect_bypass(message, 1) == "warm", message

    def test_talking_about_hoshang_is_not_knowing_him(self):
        """The near-miss that matters: 'I know Hoshang builds AI' must stay in the funnel.
        Dropping a cold lead out of qualification is worse than qualifying a warm one."""
        for message in [
            "I know Hoshang builds AI systems, saw the site",
            "I want to know what Hoshang charges",
            "Hi Hoshang, I would like to know more about your Automation services",
            "We run a clinic and need automation",
            "my cousin said n8n is cheaper long term",
        ]:
            assert detect_bypass(message, 1) is None, message

    def test_warm_signals_only_count_early(self):
        """Mid-funnel, these phrases are far likelier to be incidental."""
        assert detect_bypass("Amit referred me", 1) == "warm"
        assert detect_bypass("Amit referred me", 8) is None


class TestHumanRequest:
    def test_asking_for_a_person_bypasses_at_any_point(self):
        for message in [
            "can I talk to Hoshang directly?",
            "I dont want to chat with a bot",
            "can he call me instead?",
            "speak to a real person please",
        ]:
            assert detect_bypass(message, 1) == "human_request", message
        # Unlike warm signals, this must still work deep into the conversation.
        assert detect_bypass("can I talk to Hoshang directly?", 9) == "human_request"

    def test_every_bypass_reason_has_a_reply(self):
        for reason in ("warm", "human_request"):
            assert BYPASS_REPLIES.get(reason)


class TestAttribution:
    """Mirrors the pre-filled text in the website's lib/whatsapp.js. If these fail, the site
    copy changed and routing._SOURCE_PATTERNS needs updating with it."""

    def test_website_cta(self):
        assert detect_source(
            "Hi Hoshang, I'd like to know more about your Automation & Agentic services."
        ) == "Website CTA"

    def test_service_page_captures_which_service(self):
        source = detect_source(
            "Hi Hoshang, I'm exploring AI Automation & Agentic Systems for my business "
            "and would like to talk about whether it fits what we need."
        )
        assert source.startswith("Service page:")
        assert "AI Automation" in source

    def test_demo_space_captures_which_demo(self):
        source = detect_source(
            "Hi Hoshang, I just tried the Lead Automation demo on your site. "
            "I'd like to talk about setting up something like this for my business."
        )
        assert source.startswith("Demo Space:")
        assert "Lead Automation" in source

    def test_hand_typed_message_is_direct_or_referral(self):
        for message in ("hi", "need some automation stuff for my business", ""):
            assert "Direct" in detect_source(message) or detect_source(message) == "Unknown"
