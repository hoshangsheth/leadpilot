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
Hoshang. If they close out without a real extra note, additional_notes should be "none"."""

FEW_SHOT = """
Input: "Not really, that covers it"
Output: {"reply_text": "Perfect, that gives him everything he needs.", "extracted_fields": {"additional_notes": "none"}, "next_state": "qualification_decision", "confidence_flag": "high"}

Input: "Actually, what happens if I want to cancel partway through?"
Output: {"reply_text": "Since payment is split by milestone, you'd only ever be billed for what's actually been delivered, happy to walk through specifics on the call. Anything else you'd like him to know before he reaches out?", "extracted_fields": {}, "next_state": "additional_notes", "confidence_flag": "high"}

Input: "No that covers it, thanks" (sent after the cancellation question above was answered)
Output: {"reply_text": "Perfect, that gives him everything he needs.", "extracted_fields": {"additional_notes": "none"}, "next_state": "qualification_decision", "confidence_flag": "high"}
"""

REQUIRED_FIELDS: list[str] = []