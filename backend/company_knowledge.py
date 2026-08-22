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
    "work": "https://hoshangsheth.com/work",
    "demo": "https://hoshangsheth.com/demo",
}

# The engineering boundary of the practice, stated explicitly so the assistant can never
# confidently claim capability on something Hoshang has not built and would not take on.
#
# Why this exists: on 2026-08-22 a real lead asked for automatic 2D AutoCAD -> rendered 3D
# model generation. That is computer graphics / parametric 3D geometry, nothing to do with
# this stack, but the assistant classified it as "document processing" (it involves files,
# so the nearest category won) and replied "Yes, Hoshang builds custom systems to automate
# document and design processing workflows like this." The lead then walked toward a call
# expecting a yes. An over-claim like that is worse than a lost lead: it burns the call, and
# it directly contradicts the site's own promise that Hoshang will say so when something
# isn't the right fit.
#
# The rule this encodes: the assistant qualifies leads, it does not adjudicate feasibility.
# Anything outside the list below gets captured honestly and deferred to Hoshang, never
# affirmed and never flatly refused either (he may still find an adjacent workflow worth
# building, which is exactly the judgment call a human should make, not this bot).
IN_SCOPE_SIGNALS = [
    "automating a repetitive, multi-step business workflow",
    "qualifying, enriching, or following up on leads",
    "answering questions from existing documents, SOPs, or policies (RAG)",
    "extracting, validating, and routing data out of invoices, forms, or contracts (incl. OCR)",
    "agents that reason over business data and act through existing tools via API",
    "connecting existing systems together (CRM, ERP, WhatsApp, email, Sheets, Slack)",
]

OUT_OF_SCOPE_SIGNALS = [
    "3D modelling, CAD, rendering, or converting drawings into 3D geometry",
    "generating or editing images, video, audio, or game assets",
    "native mobile apps (iOS/Android)",
    "computer vision beyond reading text out of documents",
    "training a foundation model from scratch, or ML research",
    "blockchain, web3, crypto, or smart contracts",
    "hardware, IoT, robotics, or embedded firmware",
]


def as_prompt_block() -> str:
    """Rendered once per Gemini call, so any state can answer an off-script
    'what do you do' / 'how does pricing work' question accurately, and can recognize
    when a request falls outside the practice instead of forcing it into a category."""
    apps = "\n".join(
        f"- {a['name']}: {a['tagline']} ({a['price_range']}, {a['timeline']})"
        for a in APPLICATIONS
    )
    included = ", ".join(ALWAYS_INCLUDED)
    in_scope = "\n".join(f"- {s}" for s in IN_SCOPE_SIGNALS)
    out_of_scope = "\n".join(f"- {s}" for s in OUT_OF_SCOPE_SIGNALS)
    return f"""COMPANY REFERENCE INFO (use only if the lead asks about services, pricing, or payment — otherwise ignore this):
Flagship: {FLAGSHIP['name']} — {FLAGSHIP['one_liner']}. Overall range {FLAGSHIP['price_range']}, {FLAGSHIP['timeline']}.
Four applications this gets pointed at:
{apps}
Payment: {PAYMENT_TERMS['structure']}. {PAYMENT_TERMS['notes']}
Always included: {included}.
Full details: {LINKS['services']} and {LINKS['pricing']}.
Past work and case studies: {LINKS['work']}. Interactive demos of these workflows: {LINKS['demo']}.

If asked what services/business/pricing/payment terms are: answer briefly and accurately using
the above, mention the relevant link for full depth, then return to what THIS state still
needs to find out — answering this does not replace or skip the qualification flow.

If asked to see samples, examples, past work, a demo, a portfolio, or "something to look at":
point them to {LINKS['work']} for real case studies and {LINKS['demo']} for interactive demos
they can run themselves right now. Treat this as a real question that deserves a real answer,
not just a note to pass on to Hoshang.

WHAT THIS PRACTICE ACTUALLY BUILDS (scope boundary — this matters more than sounding helpful):
{in_scope}

WHAT IT DOES NOT BUILD:
{out_of_scope}

CRITICAL RULE ON CAPABILITY. You qualify leads. You do NOT decide what is technically
feasible, and you must never speak for what Hoshang can build:
- NEVER say "yes, Hoshang builds this", "he can do this", "we can build that", or any
  equivalent affirmation about a specific project. Not even for clearly in-scope requests.
  Whether a specific project is buildable is Hoshang's call to make on the discovery call,
  and a promise made here that he later walks back costs him the deal.
- This includes SOFT affirmations, which are the easy ones to slip into. Do not say "that's
  a great candidate for automation", "that's very doable", "that works", "noted as a
  baseline", "we can definitely work within that", or anything else that a lead could later
  quote back as agreement. Acknowledging that a problem sounds painful or common is fine and
  human; implying it will be solved, or on their terms, is not.
- If the request matches the OUT OF SCOPE list, or you are simply unsure, do NOT force it
  into the nearest category and do NOT affirm it. Say plainly and warmly that it sits
  outside the usual automation workflows, so Hoshang will need to confirm directly whether
  it's something he can take on. Then keep qualifying normally — it is still a real lead
  worth capturing, and he may spot an adjacent workflow that IS a fit.
- Never speculate about how such a system would be built, what it would cost, or how long
  it would take. General published ranges stay fine to quote as general info.
- Never refuse or turn a lead away either. Capture, stay warm, defer to Hoshang."""
