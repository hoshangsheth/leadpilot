NAME = "business_context"

INSTRUCTIONS = """You are in the Business Context state. Find out the rough size/shape of
their operation — solo vs. multiple staff/locations. One field: business_size (a short
free-text description, e.g. "single location, 2 staff"). Once captured, move on — do not
interrogate for more detail than needed."""

FEW_SHOT = """
Input: "Just one location, me and one assistant, one front desk person"
Output: {"reply_text": "Perfect, that's really helpful context, thank you.", "extracted_fields": {"business_size": "single location, 2 staff"}, "next_state": "business_context", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["business_size"]
# Day 3 extends this to ["business_context", "budget"] once the Budget state exists.
ALLOWED_NEXT = ["business_context"]
