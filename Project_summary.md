# LeadPilot — Project Summary

WhatsApp AI lead-qualification system built for hoshangsheth.com, doubling as a real business tool and a portfolio case study. Built end-to-end across one extended session (2026-08-18 evening through 2026-08-19 midday IST).

## What it is

A FastAPI backend that receives WhatsApp messages via Meta's Cloud API, runs them through a state-machine conversation engine backed by Gemini 3.6 Flash, extracts structured lead data, scores leads with a deterministic rule-based scorer, and on qualification sends Hoshang an email summary plus a Calendly link to the lead. Full architecture in `System Blueprint & Documents/whatsapp-lead-qualifier-blueprint.md`; the lean v1 build order actually followed is in `v1-leadpilot-blueprint.md`.

## Build status: complete and live

- **Deployed:** `https://leadpilot-9lo8.onrender.com`, GitHub repo `hoshangsheth/leadpilot` (private), Supabase Postgres (pooled connection, IPv4 — direct connection fails on Render due to IPv6-only resolution).
- **WhatsApp:** currently on Meta's free test number (`+1 555 201-2573`, App mode: Live). Production number pending — see Pending below.
- **Gemini:** `gemini-3.6-flash`, billing enabled (₹300 spend cap set on Google Cloud), permanent System User token (never expires) after early sessions kept hitting 24h temp-token expiry.
- **Conversation funnel:** `greeting → service_requirement → business_context → budget → timeline → contact_verification → additional_notes → qualification_decision`. Message cap 50 (raised from 15→30→50 as the funnel grew and real conversations proved longer than the theoretical minimum).
- **Cost:** ~₹1.34 per full completed conversation; realistic blended average likely ₹0.50-0.80 accounting for abandoned/tire-kicker chats. Well within budget.

## Everything built, in order

**Day 0-1:** Repo scaffold, Meta app + WhatsApp test number, Supabase Postgres, webhook receiver with HMAC signature verification, dedupe on `wa_message_id`, fast-ack background-task pattern.

**Day 2-3:** Gemini wired in per-state (system prompt + few-shot per state module in `states/`), schema validation (Pydantic) + business-rule validation (`validation/ai_output_rules.py`) as two-step AI output verification, deterministic rule-based scoring (`scoring.py`, no LLM judging), field-alias normalization to catch model naming drift.

**Day 4-5:** Calendly link injection (deterministic, never model-generated), Resend email notification, message-cap cost control with forced deterministic handoff, structured per-transition logging (`observability/logger.py`) — caught a bug where logging was silently misconfigured since Day 1.

**Day 6 — Deployment:** GitHub push, Render web service, fixed a broken `requirements.txt` (orphaned `google-generativeai` transitive deps conflicting under Render's Python), fixed Supabase IPv6 connection failure by switching to the pooler connection string, fixed WABA webhook subscription gap (`POST /{WABA_ID}/subscribed_apps` — the actual missing step that silently blocked all message delivery despite correct dashboard config), Privacy Policy URL requirement to go Live.

**Tone/UX pass:** No em-dashes anywhere in bot output (scrubbed from every few-shot, not just instructed), explicit "I'm Hoshang's AI assistant" introduction, warmer/human phrasing, `additional_notes` closing step added before handoff.

**Company knowledge (this session):** Assistant can now accurately answer "what do you do / pricing / payment terms" using real data sourced from `hoshangsheth.com/lib/content.js` and the pricing page (`company_knowledge.py`) — 4 applications with real price ranges, 50/20/30 payment structure. Fixed inaccurate "AI/ML" wording → "AI Automation & Agentic Systems" (site's actual positioning; ML is a minor footnote, not the specialization). Deliberately did NOT add the full FAQ (process steps, "what if you disappear," etc.) to avoid prompt bloat/diluted focus — scope was kept to services/pricing/payment only.

## Real bugs found via live testing (all fixed)

1. Detached-SQLAlchemy-session bug (Day 1)
2. Field-name drift ("name" vs "contact_name") — fixed with deterministic alias normalization
3. Logging silently misconfigured since Day 1 (no `logging.basicConfig`)
4. Duplicate-qualification crash (`UniqueViolation` on `conversation_id`) — fixed with upsert
5. `contact_verification` left conversations in a dead end (thanked the lead, never asked the next question)
6. `contact_preference` could complete with a bare method name and no actual usable contact detail (e.g. "email works best" with no address) — now requires the real detail, with WhatsApp allowed to complete via explicit confirmation instead of re-typed digits
7. **Severe:** `UnboundLocalError` crash on every single qualified lead — a local variable named `html` shadowed the `import html` module for the entire function, breaking the *final* step of every conversation (no closing message, no Calendly, no email) for the whole period after the HTML-escape security fix landed until caught
8. Budget (or any earlier-state field) corrections mid-conversation were silently lost — fixed by explicitly instructing the model to capture corrections under their original field key even from a later state
9. A resolved question asked during `additional_notes` was being logged as if it were a note for Hoshang — clarified that questions get answered, not logged; notes are only for genuine volunteered context

## Security/audit pass (this session)

- HTML-escaped every lead-controlled field before interpolating into the notification email (real injection vector into Hoshang's inbox — caught before it was ever exploited)
- Capped inbound message length at 2000 chars (cost/abuse protection)
- Confirmed: no secrets ever committed, signature verification is timing-safe, no SQL injection surface (ORM throughout)
- Documented but deliberately not fixed tonight (too risky to rush): no per-conversation locking (race condition if a lead double-texts fast), no retry on WhatsApp send failure, no global daily spend/volume guard beyond the per-conversation cap and the Google Cloud hard spend cap

## Pending / next steps

1. **Production WhatsApp number** — new Airtel SIM ordered (`9004862840`), arriving 2026-08-20 or 2026-08-21. Once active: complete Meta's "Step 2: Production setup," generate fresh permanent credentials for that number, re-wire webhook/Calendly/email config.
2. **Update the website's WhatsApp floating icon** to point at the production number — currently correctly left untouched (test number can't serve real visitors; recipient-restricted).
3. Consider whether to expand the assistant's company knowledge to the fuller FAQ (deferred, not decided against — just not done).
4. Standing, not LeadPilot-specific: outreach to real prospects is still the actual bottleneck — none of the business toolkit (cold outreach templates, discovery-call script, etc.) has been used on a real prospect yet. LinkedIn revamp copy also still not pasted into his actual profile.
5. LeadPilot itself has no remaining known build gaps — it's a complete, tested, deployed v1.
