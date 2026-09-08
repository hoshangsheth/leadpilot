"""Tests for pre-funnel routing: warm-contact bypass and free attribution.

The bypass patterns carry real asymmetric risk. A false NEGATIVE means a referral gets asked
for their budget by a robot — bad, but recoverable once Hoshang sees the transcript. A false
POSITIVE means a genuine cold lead is dropped out of qualification entirely and silently waits
on a human. Both directions are pinned here, with the deliberately-hard near-misses called out.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routing import detect_bypass, detect_source, BYPASS_REPLIES, is_identity_question  # noqa: E402
from conversation_engine import ensure_opening_frame  # noqa: E402


class TestIdentityQuestion:
    """2026-08-22: a real, already-qualified lead (Kunal Mehta) asked "btw is this a bot?"
    twice after the funnel closed and got total silence both times — human_takeover silences
    everything, with no exception for a direct question that deserves a truthful answer."""

    def test_genuine_identity_questions_match(self):
        for message in [
            "Btw is this a bot?", "are you a bot", "Are you AI?", "is this automated",
            "am I talking to a real person", "are you human", "is this a real person",
        ]:
            assert is_identity_question(message), message

    def test_past_tense_and_reflective_phrasing_matches(self):
        """2026-08-22: a real lead (Vikram Oberoi) asked "was that a bot answering me this
        whole time?" right after the conversation closed — reflecting back, not asking in
        the moment — and got zero reply, because every original pattern was present-tense
        only ("is"/"are"). This check runs post-handoff, where reflecting-back phrasing on
        a conversation that just ended is the norm, not the exception."""
        for message in [
            "wait, so was that a bot answering me this whole time?",
            "was that a bot", "were you a bot the whole time", "was I talking to an AI",
            "so you were AI this whole time", "so you're a bot then", "was that a real person",
            "am i chatting with a bot",
        ]:
            assert is_identity_question(message), message

    def test_real_requirements_mentioning_bots_do_not_match(self):
        """The near-miss that matters: wanting a bot built is a requirement, not a question
        about what they're currently talking to."""
        for message in [
            "Can you build me a chatbot for customer support",
            "I want an AI bot for my WhatsApp",
            "is this a good idea for automation",
            "are you able to build this in 2 weeks",
        ]:
            assert not is_identity_question(message), message


class TestOpeningFrame:
    """2026-08-22: a bare "hi" produced an opener with no bot disclosure at all. 2026-09-08:
    the two separate guards that fixed that (one prepending the disclosure, one appending the
    expectation-setting) produced a jumbled opener — disclosure before the greeting, "here's
    what happens next" stranded after the question. The frame is now composed in one place,
    in a fixed order."""

    def test_frame_is_prepended_to_a_bare_question(self):
        out = ensure_opening_frame("What process are you looking to automate?")
        assert out.startswith("Hi there, I'm Hoshang's AI assistant.")
        assert out.endswith("What process are you looking to automate?")

    def test_all_four_elements_present(self):
        out = ensure_opening_frame("What do you want to automate?").lower()
        for fragment in ["hi there", "ai assistant", "2 minutes", "24 hours"]:
            assert fragment in out

    def test_order_is_greeting_disclosure_expectation_then_question(self):
        out = ensure_opening_frame("What do you want to automate?").lower()
        assert out.index("hi there") < out.index("ai assistant") < out.index("24 hours") \
            < out.index("what do you want to automate")

    def test_model_written_frame_is_not_duplicated(self):
        """The exact jumble from the 2026-09-08 live test: the model introduced itself and
        set expectations on its own. Those fragments get stripped, not repeated."""
        reply = (
            "I'm Hoshang's AI assistant. Hi there! What kind of business process or workflow "
            "are you looking to automate? I'll ask a few quick questions, takes about 2 "
            "minutes, then he'll follow up with you personally within 24 hours."
        )
        out = ensure_opening_frame(reply)
        assert out.lower().count("ai assistant") == 1
        assert out.lower().count("24 hours") == 1
        assert out.startswith("Hi there, I'm Hoshang's AI assistant.")
        assert out.rstrip().endswith("automate?")

    def test_frame_only_reply_still_asks_something(self):
        out = ensure_opening_frame("I'm Hoshang's AI assistant.")
        assert out.rstrip().endswith("?")


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

    def test_outbound_email_reply(self):
        """Distinguishes a reply to Hoshang's own outreach email from an organic referral —
        both used to collapse into the same "Direct / referral" bucket, making it impossible
        to tell outreach conversion from organic contact in the notification email."""
        for message in [
            "Hi, got your email about AI work",
            "hey I received your email, curious to know more",
            "you emailed me about automation",
            "Hi Hoshang, saw your email today",
            "Hi, following up on your email",
            "following up on my email to you, curious to know more",
            "just replying to your email",
            "in response to your email about AI systems",
        ]:
            assert detect_source(message) == "Outbound email reply", message
