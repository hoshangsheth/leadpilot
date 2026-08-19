"""Finds out how urgent the lead's need is."""

NAME = "timeline"

INSTRUCTIONS = """You are in the Timeline state. Find out how urgent this is for them. One
field: timeline_expectation — capture as "urgent" if they indicate soon/pressing, "flexible"
if they're just exploring, or the free-text detail they gave if more specific (e.g. "within a month")."""

FEW_SHOT = """
Input: "Fairly soon actually, it's been a pain for months"
Output: {"reply_text": "Good to know, getting that sorted quickly makes sense. One last thing, what's the best name to note you down as, and is WhatsApp the best way to reach you, or do you prefer a call?", "extracted_fields": {"timeline_expectation": "urgent"}, "next_state": "contact_verification", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["timeline_expectation"]