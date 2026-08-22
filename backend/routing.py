"""Deterministic pre-funnel routing: decides whether an inbound message should enter the
qualification funnel at all, and where it came from.

Everything here runs BEFORE any Gemini call, and none of it asks the model for something that
can be computed. Two jobs:

1. Warm contacts and human requests bypass the bot entirely. A referral or a friend of
   Hoshang's must never be interrogated for their budget by a robot — they are the highest
   probability leads he has, and qualifying them is both unnecessary and actively damaging.
2. Attribution is read off the first message rather than asked for. The website sends a
   different pre-filled message from each entry point (see lib/whatsapp.js on the site), so
   the source is already sitting in the text.
"""

import re

# --- Warm contact / human handoff -------------------------------------------------------
#
# Deliberately narrow. A false positive drops a real lead out of qualification entirely, so
# these match explicit claims of a personal connection, not loose mentions of Hoshang's name.
# "I know Hoshang builds AI systems" must NOT match; "I know Hoshang personally" must.
_WARM_PATTERNS = (
    r"\bfriend of hoshang\b",
    r"\bhoshang'?s friend\b",
    r"\bhoshang knows me\b",
    r"\bi know hoshang (personally|well)\b",
    r"\bwe know each other\b",
    r"\b(referred|recommended) (me|by|us)\b",
    r"\b(gave|shared|sent) me (your|his) (number|contact)\b",
    r"\btell hoshang\b",
    r"\blet hoshang know it'?s\b",
    r"\bwe (met|spoke) (at|in|last)\b",
    r"\bfrom (college|school|work) with hoshang\b",
)

# Someone explicitly asking for a person. Distinct from a warm contact — a cold lead is also
# entitled to reach a human instead of being funnelled, and refusing that reads badly.
_HUMAN_REQUEST_PATTERNS = (
    r"\b(talk|speak|connect) (to|with) hoshang\b",
    r"\bhoshang (directly|himself)\b",
    r"\b(talk|speak) to (a|an) (human|person|real person)\b",
    r"\bcan (he|hoshang) (call|message|whatsapp|contact) me\b",
    r"\bstop the bot\b",
    r"\bdon'?t want to (talk to|chat with) a bot\b",
)

_WARM_RE = re.compile("|".join(_WARM_PATTERNS), re.I)
_HUMAN_RE = re.compile("|".join(_HUMAN_REQUEST_PATTERNS), re.I)

# Warm detection only applies to the opening messages of a conversation. Mid-funnel, these
# phrases are far likelier to be incidental than a genuine "I know him, skip this" signal.
WARM_DETECTION_MESSAGE_LIMIT = 3


def detect_bypass(text: str, message_count: int) -> str | None:
    """Returns "warm" | "human_request" | None.

    message_count is this message's 1-based position in the conversation.
    """
    if not text:
        return None
    if _HUMAN_RE.search(text):
        return "human_request"
    if message_count <= WARM_DETECTION_MESSAGE_LIMIT and _WARM_RE.search(text):
        return "warm"
    return None


BYPASS_REPLIES = {
    "warm": (
        "Thanks for reaching out! I'll pass this straight to Hoshang rather than ask you "
        "the usual questions, he'll message you personally shortly."
    ),
    "human_request": (
        "Of course, I'll let Hoshang know right away and he'll get back to you personally. "
        "Thanks for your patience!"
    ),
}


# --- Attribution ------------------------------------------------------------------------
#
# Mirrors the pre-filled text in the website's lib/whatsapp.js. If those strings change there,
# these must change here — kept as an explicit, greppable coupling rather than a fuzzy match
# that would silently mislabel every lead the day the site copy is edited.
_SOURCE_PATTERNS = (
    (re.compile(r"i just tried the (.+?) on your site", re.I), "Demo Space: {}"),
    (re.compile(r"i'?m exploring (.+?) for my business", re.I), "Service page: {}"),
    (re.compile(r"know more about your automation", re.I), "Website CTA"),
)


def detect_source(first_message: str) -> str:
    """Where this lead came from, read off their opening message.

    The site's WhatsApp links pre-fill a different message per entry point, so this is free
    and exact. Anything unrecognized was typed by hand, which in practice means a referral,
    a saved contact, or outreach — all of which are worth distinguishing from site traffic.
    """
    if not first_message:
        return "Unknown"
    for pattern, label in _SOURCE_PATTERNS:
        match = pattern.search(first_message)
        if match:
            return label.format(match.group(1).strip()) if "{}" in label else label
    return "Direct / referral (typed manually)"
