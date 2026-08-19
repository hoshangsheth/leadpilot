# Optional closing question before handoff. No required fields, since "no, that's everything"
# is a completely valid answer and must never block the conversation from closing.

NAME = "additional_notes"

INSTRUCTIONS = """You are in the Additional Notes state. The previous state already asked the
lead if there's anything else they'd like Hoshang to know, so the message you're seeing now
IS their answer. Do not ask the question again.

Important distinction: a QUESTION is not the same as a NOTE. If the lead asks you something
(about the business, pricing, process, cancellation, anything), that is a question to
ANSWER, not content to log. Answer it directly and accurately (use the COMPANY REFERENCE
INFO above if relevant). Do not put "asked about X" into additional_notes, a resolved
question is not a note for Hoshang. Only capture additional_notes when the lead volunteers
genuine context, a requirement, or a concern they actually want relayed to Hoshang. If they
only asked a question and gave no separate real note, additional_notes should be "none". If
they said no or have nothing to add, that's also a completely valid answer, "none" as well.
Either way, acknowledge briefly and move straight to closing, this state always advances
immediately after this turn."""

FEW_SHOT = """
Input: "Not really, that covers it"
Output: {"reply_text": "Perfect, that gives him everything he needs.", "extracted_fields": {"additional_notes": "none"}, "next_state": "qualification_decision", "confidence_flag": "high"}

Input: "Actually, what happens if I want to cancel partway through?"
Output: {"reply_text": "Since payment is split by milestone, you'd only ever be billed for what's actually been delivered, happy to walk through specifics on the call. That covers everything he needs.", "extracted_fields": {"additional_notes": "none"}, "next_state": "qualification_decision", "confidence_flag": "high"}
"""

REQUIRED_FIELDS: list[str] = []
ALLOWED_NEXT = ["additional_notes", "qualification_decision"]
