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
Do not advance until both fields are captured. Ask one focused follow-up if either is missing.

ALSO extract a third field, scope_fit, every time you extract service_type. Compare what they
actually described against the scope boundary in the COMPANY REFERENCE INFO above and set it
to exactly one of:
- "in_scope" — clearly matches one or more of the four applications.
- "partial" — the core ask is outside the practice, but a real automation workflow sits
  next to it that Hoshang could plausibly help with (e.g. they want 3D renders generated,
  which is out of scope, but routing/approval/revision tracking around those files is not).
- "out_of_scope" — the ask is squarely something this practice does not build.
- "unclear" — not enough detail yet to tell.

service_type must reflect what they genuinely need, NOT the nearest available label. If the
core request does not actually match any of the four categories, do not force-fit it: set
service_type to "unclear" or name the real domain plainly (e.g. "3D/CAD rendering, outside
the four categories"), and let scope_fit carry the judgment. Forcing an unrelated request
into "document processing" just because it involves files hides the mismatch from Hoshang
and sets up a wasted call.

When scope_fit is "partial" or "out_of_scope", your reply must stay warm but must NOT affirm
that Hoshang builds it (see the CRITICAL RULE ON CAPABILITY above). Say honestly that it sits
outside the usual automation workflows and he'll confirm directly, then continue qualifying."""

FEW_SHOT = """
Input: "My front desk spends a lot of time answering the same appointment questions on WhatsApp"
Output: {"reply_text": "Appointment handling and repeat questions eating up front desk time, that's a really common one. Just to understand your setup a bit better, is it just your business, or multiple locations or staff sharing the same front desk?", "extracted_fields": {"service_type": "customer support", "requirement_summary": "front desk answering repeat appointment questions on WhatsApp", "scope_fit": "in_scope"}, "next_state": "business_context", "confidence_flag": "high"}

Input: "I want a bot that follows up with bulk-order leads, and separately I want staff to be able to ask a bot for our SOPs instead of digging through WhatsApp groups"
Output: {"reply_text": "Lead follow-up and instant SOP lookup both make a lot of sense together. Just to understand your setup, how big is the team?", "extracted_fields": {"service_type": "sales/lead ops and internal knowledge/ops", "requirement_summary": "lead follow-up for bulk-order leads, plus an internal SOP lookup bot for staff", "scope_fit": "in_scope"}, "next_state": "business_context", "confidence_flag": "high"}

Input: "I'm an interior designer, I want a system where I upload my 2D AutoCAD designs and AI generates rendered 3D models of the layouts"
Output: {"reply_text": "That's a genuinely useful thing to want, though I should be straight with you: generating 3D models out of CAD drawings sits outside the automation workflows Hoshang usually builds, so he'll need to confirm directly whether it's something he can take on. Worth flagging either way. Just so he has the full picture, how big is your team?", "extracted_fields": {"service_type": "3D/CAD rendering, outside the four categories", "requirement_summary": "wants 2D AutoCAD designs automatically converted into rendered 3D models/visuals", "scope_fit": "out_of_scope"}, "next_state": "business_context", "confidence_flag": "high"}

Input: "Can you build me an Android app for my delivery boys to mark attendance?"
Output: {"reply_text": "Thanks for explaining. A native mobile app itself is outside what Hoshang builds, so he'd want to confirm that directly, though the attendance tracking and reporting side around it may well be workable. How many people would be using it?", "extracted_fields": {"service_type": "unclear", "requirement_summary": "wants an Android app for delivery staff attendance marking", "scope_fit": "partial"}, "next_state": "business_context", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["service_type", "requirement_summary"]
OPTIONAL_FIELDS = ["scope_fit"]
# scope_fit is deliberately NOT in REQUIRED_FIELDS. It is always requested in INSTRUCTIONS and
# demonstrated in every few-shot above, but gating the funnel on it would mean one forgotten
# key from the model traps the conversation in this state re-asking a question the lead has
# already answered. Scoring treats an absent scope_fit as "unknown" and neither rewards nor
# punishes it, so a miss degrades to the old behaviour instead of breaking the conversation.

# Value-level canonicalization, the direct counterpart to ALIASES (which canonicalizes field
# KEYS in contact_verification.py). Same defense-in-depth reasoning, applied one level down.
#
# Why: on 2026-08-22 the model classified a CCTV/video-analytics lead perfectly and emitted
# scope_fit="Out of scope" — correct judgment, human-readable capitalization. Scoring looked it
# up in a dict keyed "out_of_scope", missed, and silently fell through to the neutral default.
# The lead scored 79 instead of 67, and the email lost both its red banner and its subject
# prefix. The model was right and the plumbing threw the answer away.
#
# An enum crossing an LLM boundary must never be compared with ==. Reduce to alphanumerics
# only, so spacing, casing, hyphens and underscores all collapse to the same key.
VALUE_ALIASES = {
    "scope_fit": {
        "inscope": "in_scope",
        "fits": "in_scope",
        "fit": "in_scope",
        "outofscope": "out_of_scope",
        "outsidescope": "out_of_scope",
        "outside": "out_of_scope",
        "notinscope": "out_of_scope",
        "nofit": "out_of_scope",
        "partial": "partial",
        "partialfit": "partial",
        "partiallyinscope": "partial",
        "adjacent": "partial",
        "unclear": "unclear",
        "unknown": "unclear",
        "unsure": "unclear",
        "tbd": "unclear",
    }
}