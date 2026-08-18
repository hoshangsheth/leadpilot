# Optional closing question before handoff. No required fields, since "no, that's everything"
# is a completely valid answer and must never block the conversation from closing.

NAME = "additional_notes"

INSTRUCTIONS = """You are in the Additional Notes state. Ask the lead, in a warm and genuine
way, if there's anything else they'd like Hoshang to know before he follows up, any specific
note, concern, or detail worth flagging. If they share something, capture it in the field
additional_notes as a short summary in their words. If they say no or have nothing to add,
that's a completely valid answer, capture additional_notes as "none" and move on immediately.
Never ask this twice."""

FEW_SHOT = """
Input: "Not really, that covers it"
Output: {"reply_text": "Perfect, that gives him everything he needs.", "extracted_fields": {"additional_notes": "none"}, "next_state": "qualification_decision", "confidence_flag": "high"}
"""

REQUIRED_FIELDS: list[str] = []
ALLOWED_NEXT = ["additional_notes", "qualification_decision"]
