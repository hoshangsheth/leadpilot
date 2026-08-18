NAME = "contact_verification"

INSTRUCTIONS = """You are in the Contact Verification state. Get their name and preferred
contact method. Two fields: contact_name, contact_preference. If they say "WhatsApp" or
"call" as the method, that alone is fine, we already have their number from this
conversation. But if they say "email" (or anything that isn't WhatsApp/call), you must also
get the actual email address or phone number, a bare method name like "email" is not enough
to reach them. If they only give the method without the actual detail, ask for it before
moving on. Once genuinely complete, thank them warmly by name, and in the SAME reply ask if
there's anything else they'd like Hoshang to know before he follows up. Never send a reply
that just thanks them and stops. It must always end by asking something, since the
conversation is not over yet at this point."""

FEW_SHOT = """
Input: "Dr. Ameya Kulkarni, WhatsApp is fine, or a call works too"
Output: {"reply_text": "Wonderful, thank you Dr. Kulkarni. Before I let him know, is there anything else you'd like Hoshang to be aware of?", "extracted_fields": {"contact_name": "Dr. Ameya Kulkarni", "contact_preference": "WhatsApp or call"}, "next_state": "additional_notes", "confidence_flag": "high"}

Input: "Priya Nair, email works best for me"
Output: {"reply_text": "Thanks, Priya. What's the best email address to reach you at?", "extracted_fields": {"contact_name": "Priya Nair"}, "next_state": "contact_verification", "confidence_flag": "low"}
"""

REQUIRED_FIELDS = ["contact_name", "contact_preference"]
ALLOWED_NEXT = ["contact_verification", "additional_notes"]

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
    "preferred_contact": "contact_preference",
}


def extra_check(merged_fields: dict) -> bool:
    """contact_preference being present isn't the same as being usable. If it names a method
    other than WhatsApp/call (which we can already reach via the WhatsApp number itself)
    without an actual email address or phone number attached, it's not genuinely complete —
    caught here deterministically rather than trusting the model to always remember."""
    preference = (merged_fields.get("contact_preference") or "").lower()
    if "whatsapp" in preference or "call" in preference or "phone" in preference:
        return True
    has_email_address = "@" in preference
    has_digits = any(ch.isdigit() for ch in preference)
    return has_email_address or has_digits
