"""Deterministic pre-funnel routing: decides whether an inbound message should enter the
qualification funnel at all, and where it came from.

Everything here runs BEFORE any Gemini call, and none of it asks the model for something that
can be computed. Three jobs:

1. Warm contacts and human requests bypass the bot entirely. A referral or a friend of
   Hoshang's must never be interrogated for their budget by a robot — they are the highest
   probability leads he has, and qualifying them is both unnecessary and actively damaging.
2. Attribution is read off the first message rather than asked for. The website sends a
   different pre-filled message from each entry point (see lib/whatsapp.js on the site), so
   the source is already sitting in the text.
3. "Is this a bot?" gets answered even after the funnel has closed. Once a conversation
   reaches qualification_decision, human_takeover silences the bot entirely — correct for
   ordinary chatter, wrong for a direct question that deserves a truthful answer. On
   2026-08-22 a real, already-qualified lead asked "btw is this a bot?" twice after closing
   out and got total silence both times. This is answered deterministically (no Gemini call,
   no reopening the funnel) precisely because it must work even when nothing else does.
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


# --- "Is this a bot?" after the funnel has closed ---------------------------------------
#
# Deliberately narrow to genuine identity questions, not any mention of the word "bot"
# ("can you build me a chatbot" must NOT match — that is a real requirement, not a question
# about what they're talking to).
#
# Present-tense only originally, and it cost a real reply: a lead (Vikram Oberoi, 2026-08-22)
# asked "was that a bot answering me this whole time?" right after the conversation closed —
# past tense, referring back rather than asking in the moment — and every pattern here was
# written as "is"/"are", so none of them matched. Every present-tense pattern below now has
# a past-tense sibling (was/were alongside is/are) for exactly this reason: someone reflecting
# on a conversation that just ended is at least as likely to phrase it in the past as the
# present, and this check only runs post-handoff, where reflecting-back phrasing is the norm,
# not the exception.
_IDENTITY_QUESTION_PATTERNS = (
    r"\b(is|was|were) (this|that|it|the number) (a bot|an ai|automated)\b",
    r"\b(are|were) you (a )?bot\b",
    r"\b(are|were) you (an )?ai\b",
    r"\b(are|were) you (a )?real (person|human)\b",
    r"\b(are|were) you human\b",
    r"\b(am|was) i (talking|chatting|speaking) (to|with) (a |an )?(bot|real person|human|person|ai)\b",
    r"\b(is|was) (this|that) a real person\b",
    # "you're"/"you were" as a statement rather than a question ("so you're a bot",
    # "you were AI this whole time") — someone concluding out loud, not just asking.
    r"\byou'?re (a )?bot\b",
    r"\byou'?re (an )?ai\b",
    r"\byou were (a )?bot\b",
    r"\byou were (an )?ai\b",
)
_IDENTITY_QUESTION_RE = re.compile("|".join(_IDENTITY_QUESTION_PATTERNS), re.I)


def is_identity_question(text: str) -> bool:
    return bool(text) and bool(_IDENTITY_QUESTION_RE.search(text))


IDENTITY_QUESTION_REPLY = (
    "Yes, I'm Hoshang's AI assistant, not Hoshang himself! He has everything from our "
    "conversation and will follow up with you personally."
)


# --- Explicit request for Hoshang's own contact details ---------------------------------
#
# A lead asking to reach Hoshang directly (not "connect me" — an actual "what's his email /
# number") gets exactly one channel: his email, hoshangsheth@gmail.com. Never his phone or
# WhatsApp — those stay reserved for outbound calls Hoshang chooses to make himself, not
# inbound contact a stranger dials into unprompted. Narrow to "his/him", not any mention of
# "email" or "number" — asking to confirm THEIR OWN contact_preference ("this number is
# fine") must never match.
_CONTACT_INFO_PATTERNS = (
    r"\bhis (email|e-mail|number|phone|whatsapp|contact)\b",
    r"\b(email|call|whatsapp|message|reach|contact) him directly\b",
    r"\b(get|have) (his|hoshang'?s) (email|e-mail|number|phone|contact|whatsapp)\b",
    r"\bhoshang'?s (email|e-mail|number|phone|contact|whatsapp)\b",
    r"\bdoes he have an? email\b",
    r"\bwhat'?s his (email|e-mail|number|phone|contact)\b",
    r"\bhow (can|do) i (reach|contact|email|call) (him|hoshang)\b",
)
_CONTACT_INFO_RE = re.compile("|".join(_CONTACT_INFO_PATTERNS), re.I)


def is_contact_info_request(text: str) -> bool:
    return bool(text) and bool(_CONTACT_INFO_RE.search(text))


CONTACT_INFO_REPLY = (
    "Of course, you can reach him directly at hoshangsheth@gmail.com. I'll still pass along "
    "everything from our conversation so he has full context."
)


# Both open by identifying as the assistant. A bypassed lead skips the funnel, which is also
# the only place the AI disclosure was ever added (message_handler applies the opening frame
# on the funnel path only) — so until 2026-09-08 a referral or a "let me talk to a human"
# request was answered by a bot that never said it was one. Whether someone knows what
# they're talking to isn't conditional on which branch their message took.
BYPASS_REPLIES = {
    "warm": (
        "Thanks for reaching out! I'm Hoshang's AI assistant, and I'll pass this straight to "
        "him rather than ask you the usual questions, he'll message you personally shortly. "
        "What's your name, so he knows who to expect?"
    ),
    "human_request": (
        "Of course. I'm Hoshang's AI assistant, and I'll let him know right away so he can "
        "get back to you personally. Thanks for your patience! What's your name, so he knows "
        "who's asking?"
    ),
}
# A bypassed lead's handoff email previously carried nothing but a raw phone number — no way
# to know who's on the other end before opening WhatsApp. On 2026-08-24 this was flagged
# directly: "even though it's a referral or direct, AI should at least get the name."
#
# The bypass reply above now asks for it, but the reply to that ask is NOT reliably a clean
# name — the exact lead this was raised for came back with "Ok will wait for his call," not
# a name. Treating whatever comes back as a confident contact_name would silently corrupt
# the field with garbage. Instead the raw reply is forwarded to Hoshang labeled as exactly
# that — their reply to the name request — so he sees it as-is and judges for himself,
# rather than the system pretending certainty it doesn't have.


# --- Attribution ------------------------------------------------------------------------
#
# Mirrors the pre-filled text in the website's lib/whatsapp.js. If those strings change there,
# these must change here — kept as an explicit, greppable coupling rather than a fuzzy match
# that would silently mislabel every lead the day the site copy is edited.
_SOURCE_PATTERNS = (
    (re.compile(r"i just tried the (.+?) on your site", re.I), "Demo Space: {}"),
    (re.compile(r"i'?m exploring (.+?) for my business", re.I), "Service page: {}"),
    (re.compile(r"know more about your automation", re.I), "Website CTA"),
    (re.compile(
        r"\b(got|received|saw|following up on|following up regarding|"
        r"replying to|responding to|in response to|regarding) "
        r"(an |your |the |my )?email\b|\byou emailed me\b",
        re.I,
    ), "Outbound email reply"),
)


def detect_source(first_message: str) -> str:
    """Where this lead came from, read off their opening message.

    The site's WhatsApp links pre-fill a different message per entry point, so this is free
    and exact. Anything unrecognized was typed by hand — could be a referral, a saved
    contact, or outreach, but typing a message by hand is not itself evidence of a referral.
    On 2026-09-07 a real lead (Meera Kapoor) typed "Hi" with no connection to Hoshang at all
    and was labeled "Direct / referral (typed manually)" — the source is worth flagging as
    unconfirmed, but must NOT claim "referral" unless detect_bypass's _WARM_RE actually
    matched an explicit referral/personal-connection claim (see _WARM_PATTERNS above).
    """
    if not first_message:
        return "Unknown"
    for pattern, label in _SOURCE_PATTERNS:
        match = pattern.search(first_message)
        if match:
            return label.format(match.group(1).strip()) if "{}" in label else label
    return "Direct message (typed manually, source unconfirmed)"
