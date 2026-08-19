"""Asks for a rough budget range, accepting "not disclosed" as a valid, non-blocking answer."""

NAME = "budget"

INSTRUCTIONS = """You are in the Budget state. Ask for a rough budget range, even a loose one.
Make clear there's no pressure to be exact. One field: budget_range (free text, e.g. "15-20k INR"
or "not disclosed" if they decline to share, that's a valid answer too, do not push twice)."""

FEW_SHOT = """
Input: "Not really sure honestly, maybe 15-20k? Depends what it actually does"
Output: {"reply_text": "That's a totally reasonable range for this kind of build. And timing wise, is this something you'd want live soon, or more just exploring for now?", "extracted_fields": {"budget_range": "15-20k INR"}, "next_state": "timeline", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["budget_range"]
ALLOWED_NEXT = ["budget", "timeline"]
