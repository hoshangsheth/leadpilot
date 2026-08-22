"""Collects the lead's name and a genuinely usable contact detail (not just a bare method
name), then closes by asking if there's anything else they'd like relayed to Hoshang."""

NAME = "contact_verification"

INSTRUCTIONS = """You are in the Contact Verification state. Get their name and preferred
contact method, AND the actual contact detail for that method, no matter which method they
name.

If you need to ask for their name/method fresh (neither is in FIELDS_COLLECTED yet), always
offer WhatsApp, a phone call, AND email as options, never just two. On 2026-08-22 the prior
state's own phrasing baked in "WhatsApp or a call" with no mention of email, so email was
never realistically offered as a channel — a lead who would have preferred it never got the
chance to say so.

Capture their name EXACTLY as fully as they gave it. If they write "Rohit save, whatsapp",
contact_name is "Rohit Save", not "Rohit" — fix casing, never drop a surname they took the
trouble to type. Only store a first name if a first name is genuinely all they gave. If they say "WhatsApp", still ask them to confirm the number to use (even though it
may match this conversation, always ask rather than assume). If they say "call" or "phone",
get the actual phone number. If they say "email", get the actual email address. A bare
method name alone, with no real number or address attached, is never enough, always ask for
the specific detail before moving on. Once genuinely complete (name, method, AND the real
contact detail), thank them warmly by name, and in the SAME reply ask if there's anything
else they'd like Hoshang to know before he follows up. Never send a reply that just thanks
them and stops. It must always end by asking something, since the conversation is not over
yet at this point."""

FEW_SHOT = """
Input: "Dr. Ameya Kulkarni, WhatsApp is fine"
Output: {"reply_text": "Thanks, Dr. Kulkarni. Just to confirm, is this the WhatsApp number to use?", "extracted_fields": {"contact_name": "Dr. Ameya Kulkarni"}, "next_state": "contact_verification", "confidence_flag": "low"}

Input: "Priya Nair, email works best for me"
Output: {"reply_text": "Thanks, Priya. What's the best email address to reach you at?", "extracted_fields": {"contact_name": "Priya Nair"}, "next_state": "contact_verification", "confidence_flag": "low"}

Input: "Yes this WhatsApp number is fine" (after being asked to confirm)
Output: {"reply_text": "Perfect, thank you. Before I let him know, is there anything else you'd like Hoshang to be aware of?", "extracted_fields": {"contact_preference": "WhatsApp, this number"}, "next_state": "additional_notes", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["contact_name", "contact_preference"]
# Defense-in-depth: the model sometimes extracts a natural-sounding key ("name") instead of
# the exact required key ("contact_name") despite the prompt/few-shot specifying it. Rather
# than trust the model to always comply, normalize known aliases deterministically before
# validation — this is a canonicalization step, not an LLM judgment call, so it doesn't
# compromise explainability.
ALIASES = {
    "name": "contact_name",
    "full_name": "contact_name",
    "lead_name": "contact_name",
    "phone": "contact_preference",
    "phone_number": "contact_preference",
    "email": "contact_preference",
    "email_address": "contact_preference",
    "contact_email": "contact_preference",
    "preferred_contact": "contact_preference",
}


def extra_check(merged_fields: dict) -> bool:
    """contact_preference being present isn't the same as being usable. A bare method name
    ("email", "call", "phone") with no actual detail attached is not genuinely complete —
    caught here deterministically rather than trusting the model to always remember to ask.
    WhatsApp is the one exception that can pass via a confirmation phrase instead of re-typed
    digits, since we already have a genuinely usable number for that method either way."""
    preference = (merged_fields.get("contact_preference") or "").lower()
    has_email_address = "@" in preference
    has_digits = any(ch.isdigit() for ch in preference)
    if has_email_address or has_digits:
        return True
    whatsapp_confirmed = "whatsapp" in preference and (
        "this number" in preference or "same number" in preference or "confirm" in preference
    )
    return whatsapp_confirmed
