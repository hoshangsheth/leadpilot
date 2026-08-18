NAME = "contact_verification"

INSTRUCTIONS = """You are in the Contact Verification state. Get their name and preferred
contact method. Two fields: contact_name, contact_preference (e.g. "WhatsApp", "call",
"either"). Once both are captured, thank them warmly by name. Do not ask further qualifying
questions here, that's the next state's job, not yours."""

FEW_SHOT = """
Input: "Dr. Ameya Kulkarni, WhatsApp is fine, or a call works too"
Output: {"reply_text": "Wonderful, thank you Dr. Kulkarni.", "extracted_fields": {"contact_name": "Dr. Ameya Kulkarni", "contact_preference": "WhatsApp or call"}, "next_state": "additional_notes", "confidence_flag": "high"}
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
