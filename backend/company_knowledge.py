"""Factual reference for Hoshang's business — sourced directly from hoshangsheth.com
(lib/content.js, pricing page) so the assistant never invents numbers or positioning.
Kept as plain data, not prose baked into a prompt, so it's easy to keep in sync if the
site's pricing changes — update this file, not the state prompts.
"""

FLAGSHIP = {
    "name": "AI Automation & Agentic Systems",
    "one_liner": "AI-powered systems that automate repetitive, knowledge-heavy, multi-step business workflows",
    "price_range": "₹35,000 to ₹90,000",
    "timeline": "5 to 12 weeks",
}

APPLICATIONS = [
    {
        "name": "Sales & Lead Operations",
        "tagline": "Leads qualified, enriched, and followed up on before they go cold",
        "price_range": "₹35,000 to ₹70,000",
        "timeline": "5 to 8 weeks",
    },
    {
        "name": "Customer Support",
        "tagline": "Answers from your documents, with sources, and a clean handoff when it shouldn't answer",
        "price_range": "₹55,000 to ₹90,000",
        "timeline": "8 to 12 weeks",
    },
    {
        "name": "Document Processing",
        "tagline": "Invoices, forms, and contracts extracted, validated, and routed without manual re-entry",
        "price_range": "₹35,000 to ₹70,000",
        "timeline": "5 to 8 weeks",
    },
    {
        "name": "Internal Knowledge & Operations",
        "tagline": "Ask a question, get an answer, and let the system act on it",
        "price_range": "₹45,000 to ₹90,000",
        "timeline": "6 to 12 weeks",
    },
]

PAYMENT_TERMS = {
    "structure": "50% on proposal approval to begin work, 20% at working prototype, 30% before final handover",
    "notes": (
        "Fixed price agreed before any work begins, no hourly billing, no monthly retainer. "
        "Anything outside agreed scope is quoted separately and only starts once approved."
    ),
}

ALWAYS_INCLUDED = [
    "Full source code ownership on handover",
    "Deployment documentation and a recorded walkthrough",
    "30 days of post-launch support, included",
    "A live staging environment throughout the build",
    "No monthly fees, no vendor lock-in",
]

LINKS = {
    "services": "https://hoshangsheth.com/services",
    "pricing": "https://hoshangsheth.com/pricing",
}


def as_prompt_block() -> str:
    """Rendered once per Gemini call, so any state can answer an off-script
    'what do you do' / 'how does pricing work' question accurately."""
    apps = "\n".join(
        f"- {a['name']}: {a['tagline']} ({a['price_range']}, {a['timeline']})"
        for a in APPLICATIONS
    )
    included = ", ".join(ALWAYS_INCLUDED)
    return f"""COMPANY REFERENCE INFO (use only if the lead asks about services, pricing, or payment — otherwise ignore this):
Flagship: {FLAGSHIP['name']} — {FLAGSHIP['one_liner']}. Overall range {FLAGSHIP['price_range']}, {FLAGSHIP['timeline']}.
Four applications this gets pointed at:
{apps}
Payment: {PAYMENT_TERMS['structure']}. {PAYMENT_TERMS['notes']}
Always included: {included}.
Full details: {LINKS['services']} and {LINKS['pricing']}.

If asked what services/business/pricing/payment terms are: answer briefly and accurately using
the above, mention the relevant link for full depth, then return to what THIS state still
needs to find out — answering this does not replace or skip the qualification flow."""
