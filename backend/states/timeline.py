"""Finds out how urgent the lead's need is."""

NAME = "timeline"

INSTRUCTIONS = """You are in the Timeline state. Find out how urgent this is for them. One
field: timeline_expectation — capture as "urgent" if they indicate soon/pressing, "flexible"
if they're just exploring, or the free-text detail they gave if more specific (e.g. "within a month").

Once you have it, in the SAME reply ask for their name and contact preference (this hands off
to Contact Verification next). ALWAYS name all three channels explicitly — WhatsApp, a call,
and email — never a vague "how would you prefer to be reached" or a two-way choice. On
2026-08-22 a real lead was only ever offered WhatsApp or a call; email was technically
accepted if volunteered, but never actually presented as an option, so nobody who would have
preferred it ever got the chance to say so. Whichever exact wording you use, all three names
must appear."""

FEW_SHOT = """
Input: "Fairly soon actually, it's been a pain for months"
Output: {"reply_text": "Good to know, getting that sorted quickly makes sense. One last thing, what's the best name to note you down as, and would WhatsApp, a call, or email work best to reach you?", "extracted_fields": {"timeline_expectation": "urgent"}, "next_state": "contact_verification", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["timeline_expectation"]