# LeadPilot V1 — Lean Build Order

Derived from `whatsapp-lead-qualifier-blueprint.md` (the full Mini Build Blueprint) in this same folder — that document remains the source of truth for architecture, schema, API contract, and portfolio write-up. This file only compresses the *build order and MVP scope* down to something shippable in ~5-7 days part-time instead of 3-4 weeks, for the specific goal of getting a real, working lead qualifier live on hoshangsheth.com fast. Once live, it doubles as both a real lead-gen tool and a working case study for outreach.

**When to use which document:** build from this file day-to-day. Refer back to the full blueprint for any section not restated here (schema DDL, full API contract, deployment gotchas, risk register, free-tier budget) — nothing there is superseded, just deferred or trimmed for v1.

---

## What's cut from the full MVP scope for v1, and why

| Cut from full blueprint's MVP | Why safe to defer |
|---|---|
| n8n notify workflow (Section 4-6) | Adds a whole extra service to deploy for one job. Call Resend directly from FastAPI on handoff instead — same result, one less moving part. Add n8n back later only if you outgrow a direct call. |
| 24h-window template fallback (Section 11) | Requires a Meta-approved message template, which has its own approval lag. Most of your own conversations will complete within the window anyway. For v1: log stale conversations instead of auto re-engaging them. |
| Full Stage 5 hardening (edge case test matrix, structured logging polish) | Keep only the must-not-break items (see Day 5 below). Full test coverage lands after it's live and proven, not before. |
| Stage 7 polish (README, demo recording, portfolio write-up) | Content is already pre-written in the full blueprint's Section 14 — do it in an afternoon *after* launch. Doesn't block going live. |
| Full early-funnel state split (Service ID + Requirement Gathering + Business Context as 3 separate states) | You already know your own 4 services — merge Service Identification + Requirement Gathering into one state for v1. You're not discovering what you offer from a lead the way a generic client project would. |

## What's NOT cut, even in lean v1 (non-negotiable)

- Dedupe on `wa_message_id` — without it, Meta's retry behavior corrupts conversation state.
- Fast `200` ack before processing (background task pattern) — prevents Meta retry storms.
- **Business-rule validation, Step 2 (full blueprint Section 10)** — the check that stops a schema-valid-but-nonsensical state jump (e.g. reaching `qualification_decision` with `budget_range` still null). Cheap to build since the full blueprint already gives you the function — skipping it isn't leaner, it's just broken.
- Rule-based lead scoring — same explainability reasoning as the full blueprint, unchanged for v1.

---

## Day-by-day build order

**Day 0 — kick off the slow external dependency first**
Start Meta business verification *today*, in parallel with everything else — this is a 3-7 day lag outside your control (see full blueprint's Risk Register). Also complete Stage 0: repo, Postgres, Meta test app + test number, `.env`, skeleton files, confirm `MOCK_LLM=true` returns a typed `ConversationTurnResult`.
**Commit:** `chore: project scaffold, Meta webhook verified, Postgres schema, env config`

**Day 1 — Stage 1, Core Baseline**
Webhook receiver, signature verification, dedupe, hardcoded/stub reply — zero Gemini calls. Proves the webhook → DB → send loop works end-to-end.
**Commit:** `feat: core baseline — webhook receiver, dedupe, persistence (no AI)`

**Day 2 — Stage 2, compressed early funnel**
Greeting → (merged) Service+Requirement Identification → Business Context. Gemini wired in, schema + business-rule validation both in from day one. Buildable and testable entirely against `MOCK_LLM` while waiting on Meta verification.
**Commit:** `feat: early-funnel vertical slice (compressed) — Gemini wired, schema + business-rule validation`

**Day 3 — Stage 3, Qualification**
Budget → Timeline → Contact Verification → Qualification Decision, rule-based scoring. A lead can be fully qualified or disqualified end-to-end.
**Commit:** `feat: qualification vertical slice — scoring, decision logic`

**Day 4 — Stage 4, Meeting & Handoff (lean)**
Calendly link injection, handoff message to lead, direct Resend email to yourself on qualification (no n8n). Full happy path complete, locally.
**Commit:** `feat: meeting & handoff vertical slice (lean, no n8n) — full happy path complete`

**Day 5 — minimum viable hardening**
Only: fast-ack background task pattern, message cap (15 messages → forced handoff), top-level exception catch with basic logging (lead_id, state, outcome). Skip the rest of full Stage 5.
**Commit:** `feat: minimum hardening — fast ack, message cap, basic error logging`

**Day 6-7 — Deploy**
Render hosting, HTTPS webhook, re-register callback URL with Meta. If business verification hasn't cleared yet, soft-launch on the test number internally and flip to the real business number the moment it clears — don't let verification lag block finishing the build itself.
**Commit:** `chore: deployment — Render hosting, webhook re-registration`

---

## After it's live

Do full-blueprint Stage 7 polish (README, demo GIF, portfolio write-up) *after* launch, not before — that content is already drafted in the full blueprint's Section 14, so it's a copy-and-record afternoon, not a build task. This is also the point where it becomes genuinely dual-purpose: a real lead-gen tool live on your site, and a working demo/case study for outreach.

## V1.5 — first things to add back once v1 is proven live

Pull these back in from the full blueprint once the lean version is stable and generating real leads, roughly in this order:
1. 24h-window template fallback (Section 11) — once you have an approved Meta template
2. n8n notify workflow, if you outgrow calling Resend directly
3. Full Stage 5 hardening — complete edge case test matrix, structured logging depth
4. Stage 7 polish, if not already done post-launch

Everything past that (dashboard, multi-tenant, eval harness, Langfuse tracing) stays in the full blueprint's V2 Radar (Section 14) — genuinely not relevant until there's a real reason for it, not before.
