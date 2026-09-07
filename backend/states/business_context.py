"""Finds out the rough size/shape of the lead's operation (solo vs. multiple staff/locations)
and the name of the business itself."""

NAME = "business_context"

INSTRUCTIONS = """You are in the Business Context state. Find out two things: the name of
their business/company, and the rough size/shape of their operation — solo vs. multiple
staff/locations. Two fields: company_name (the business's name, exactly as given — if they
genuinely have no separate business name, e.g. a solo freelancer trading under their own
name, use their own name) and business_size (a short free-text description, e.g. "single
location, 2 staff"). Ask for both in one message if neither is known yet, don't split them
into two separate questions. Once both are captured, move on — do not interrogate for more
detail than needed."""

FEW_SHOT = """
Input: "It's called Kapoor Wellness, just one location, me and one assistant, one front desk person"
Output: {"reply_text": "Perfect, that's helpful. Rough ballpark, do you have a budget range in mind for something like this, even a loose one? No pressure to be exact.", "extracted_fields": {"company_name": "Kapoor Wellness", "business_size": "single location, 2 staff"}, "next_state": "budget", "confidence_flag": "high"}

Input: "Just one location, me and one assistant, one front desk person" (company name not yet given)
Output: {"reply_text": "Got it, thanks. And what's the name of your business?", "extracted_fields": {"business_size": "single location, 2 staff"}, "next_state": "business_context", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["company_name", "business_size"]