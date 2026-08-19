"""Merged Service Identification + Requirement Gathering, per the v1 lean blueprint
(Hoshang already knows his own 4 service categories — no need for a separate
discovery state the way a generic client project would need).
"""

NAME = "service_requirement"

INSTRUCTIONS = """You are in the Service + Requirement state. Find out two things:
1. What kind of pain/process they want automated (service_type — one or more of: customer
   support, sales/lead ops, document processing, internal knowledge/ops, or "unclear" if
   genuinely unclear). If the lead's need genuinely spans more than one of these categories
   (e.g. they want both a lead-qualification bot AND an internal SOP lookup bot), capture ALL
   of the relevant categories in service_type, joined together (e.g. "sales/lead ops and
   internal knowledge/ops") — never force a multi-service lead into a single category just to
   keep the field simple, that would hide real deal size from Hoshang.
2. A one-line description of the actual requirement in their words (requirement_summary),
   covering every distinct piece if there's more than one.
Do not advance until both fields are captured. Ask one focused follow-up if either is missing."""

FEW_SHOT = """
Input: "My front desk spends a lot of time answering the same appointment questions on WhatsApp"
Output: {"reply_text": "Appointment handling and repeat questions eating up front desk time, that's a really common one. Just to understand your setup a bit better, is it just your business, or multiple locations or staff sharing the same front desk?", "extracted_fields": {"service_type": "customer support", "requirement_summary": "front desk answering repeat appointment questions on WhatsApp"}, "next_state": "business_context", "confidence_flag": "high"}

Input: "I want a bot that follows up with bulk-order leads, and separately I want staff to be able to ask a bot for our SOPs instead of digging through WhatsApp groups"
Output: {"reply_text": "Lead follow-up and instant SOP lookup both make a lot of sense together. Just to understand your setup, how big is the team?", "extracted_fields": {"service_type": "sales/lead ops and internal knowledge/ops", "requirement_summary": "lead follow-up for bulk-order leads, plus an internal SOP lookup bot for staff"}, "next_state": "business_context", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["service_type", "requirement_summary"]