"""Merged Service Identification + Requirement Gathering, per the v1 lean blueprint
(Hoshang already knows his own 4 service categories — no need for a separate
discovery state the way a generic client project would need).
"""

NAME = "service_requirement"

INSTRUCTIONS = """You are in the Service + Requirement state. Find out two things:
1. What kind of pain/process they want automated (service_type — one of: customer support,
   sales/lead ops, document processing, internal knowledge/ops, or "unclear" if genuinely unclear)
2. A one-line description of the actual requirement in their words (requirement_summary)
Do not advance until both fields are captured. Ask one focused follow-up if either is missing."""

FEW_SHOT = """
Input: "My front desk spends a lot of time answering the same appointment questions on WhatsApp"
Output: {"reply_text": "Appointment handling and repeat questions eating up front desk time, that's a really common one. Just to understand your setup a bit better, is it just your business, or multiple locations or staff sharing the same front desk?", "extracted_fields": {"service_type": "customer support", "requirement_summary": "front desk answering repeat appointment questions on WhatsApp"}, "next_state": "business_context", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["service_type", "requirement_summary"]