NAME = "business_context"

INSTRUCTIONS = """You are in the Business Context state. Find out the rough size/shape of
their operation — solo vs. multiple staff/locations. One field: business_size (a short
free-text description, e.g. "single location, 2 staff"). Once captured, move on — do not
interrogate for more detail than needed."""

FEW_SHOT = """
Input: "Just one location, me and one assistant, one front desk person"
Output: {"reply_text": "Perfect, that's helpful. Rough ballpark — do you have a budget range in mind for something like this, even a loose one? No pressure to be exact.", "extracted_fields": {"business_size": "single location, 2 staff"}, "next_state": "budget", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["business_size"]
ALLOWED_NEXT = ["business_context", "budget"]
