"""Optional closing question before handoff. No required fields, since "no, that's everything"
is a completely valid answer and must never block the conversation from closing.
"""

NAME = "additional_notes"

INSTRUCTIONS = """You are in the Additional Notes state. The previous state already asked the
lead if there's anything else they'd like Hoshang to know, so the message you're seeing now
IS their reaction to that question — but it is not necessarily their FINAL answer.

Important distinction: a QUESTION is not the same as a close-out answer. If the lead asks you
something (about the business, pricing, process, cancellation, anything), answer it directly
and accurately (use the COMPANY REFERENCE INFO above if relevant) — but do NOT treat
answering a question as the end of the conversation. The lead hasn't actually confirmed
they're done yet. In the SAME reply, re-ask whether there's anything else they'd like Hoshang
to know, and stay in this state (next_state stays additional_notes) so they get a real chance
to answer that. Never send the closing/handoff message in the same turn you're still
answering an open question.

Only advance to qualification_decision once the lead has given an actual close-out answer:
either they explicitly say there's nothing else (no, that's it, nothing else, thanks that's
all, etc.), or they volunteer a genuine note/requirement with no further question attached.
Do not put "asked about X" into additional_notes — a resolved question is not a note for
Hoshang. If they close out without a real extra note, additional_notes should be "none".

ANYTHING THAT BELONGS TO A REAL FIELD GOES TO THAT FIELD, NOT INTO additional_notes. If
what they say here answers or revises budget, timeline, company name, service type,
requirement, business size, or contact details, emit it under that canonical key (see
CANONICAL_FIELD_KEYS) — even if they declined to answer it earlier in the conversation.
additional_notes is only for genuinely field-less context, e.g. "prefers to be called after
6pm" or "has a partner who needs to approve". A budget figure filed as a note reaches
Hoshang as "Budget: not disclosed" with the real number buried underneath it, which is how
a qualified lead gets scoped wrong.

ALSO EMIT notes_turn_kind EVERY TIME you stay in this state, set to exactly one of:
- "substantive" — they asked a real question about the work, the business, pricing,
  process, timelines, ownership, cancellation, or anything else a serious buyer would
  reasonably want answered before a call. Also use this when they are still adding real
  context about their requirement.
- "chatter" — small talk, filler, a repeated question you have already answered, testing
  the bot, or anything that adds nothing to what Hoshang needs.

This is bookkeeping, not something you mention to the lead. It decides whether this round
counts toward the cap that eventually closes the conversation deterministically — a lead
asking genuine questions should never be cut off for it, and on 2026-09-08 that is exactly
what happened: three legitimate questions in a row (contact details, "is this a bot", an
out-of-scope aside) tripped the cap, and the lead's real close-out message got answered
with a canned "I don't want this to turn into an endless back-and-forth" instead."""

FEW_SHOT = """
Input: "Not really, that covers it"
Output: {"reply_text": "Perfect, that gives him everything he needs.", "extracted_fields": {"additional_notes": "none"}, "next_state": "qualification_decision", "confidence_flag": "high"}

Input: "Actually, what happens if I want to cancel partway through?"
Output: {"reply_text": "Since payment is split by milestone, you'd only ever be billed for what's actually been delivered, happy to walk through specifics on the call. Anything else you'd like him to know before he reaches out?", "extracted_fields": {"notes_turn_kind": "substantive"}, "next_state": "additional_notes", "confidence_flag": "high"}

Input: "No that covers it, thanks" (sent after the cancellation question above was answered)
Output: {"reply_text": "Perfect, that gives him everything he needs.", "extracted_fields": {"additional_notes": "none"}, "next_state": "qualification_decision", "confidence_flag": "high"}

Input: "Just so you know, I'd happily go above 70k if it actually removes the manual work" (budget_range was previously "not disclosed")
Output: {"reply_text": "Good to know, that's useful context for him. Anything else you'd like Hoshang to be aware of before he reaches out?", "extracted_fields": {"budget_range": "flexible, above 70k if it eliminates the manual work", "notes_turn_kind": "substantive"}, "next_state": "additional_notes", "confidence_flag": "high"}

Input: "lol ok cool"
Output: {"reply_text": "Anything else you'd like Hoshang to know before he reaches out?", "extracted_fields": {"notes_turn_kind": "chatter"}, "next_state": "additional_notes", "confidence_flag": "high"}
"""

REQUIRED_FIELDS: list[str] = []

# Deliberately optional, for the same reason as service_requirement.scope_fit: it is always
# asked for and always demonstrated in the few-shots, but gating the funnel on it would let
# one forgotten key trap a lead in this state. A missing value is treated as "substantive"
# by the caller (message_handler), which is the safe direction — a genuine question never
# gets cut off because the model dropped a bookkeeping field, and MAX_MESSAGES remains the
# real backstop against a runaway conversation.
OPTIONAL_FIELDS = ["notes_turn_kind"]

# Same enum-across-an-LLM-boundary reasoning as service_requirement.VALUE_ALIASES: never
# compare a model-produced enum with == and hope.
VALUE_ALIASES = {
    "notes_turn_kind": {
        "substantive": "substantive",
        "substantivequestion": "substantive",
        "genuine": "substantive",
        "genuinequestion": "substantive",
        "real": "substantive",
        "question": "substantive",
        "chatter": "chatter",
        "smalltalk": "chatter",
        "filler": "chatter",
        "chitchat": "chatter",
        "none": "chatter",
    }
}