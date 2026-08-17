# Mini Build Blueprint — WhatsApp AI Lead Qualification System

**Assumptions:**
- n8n is demoted from "conversation engine" to optional glue (email send, calendar webhook) — the state machine lives in FastAPI, not n8n nodes. Reasoning stated above the blueprint.
- "Dashboard" mentioned in your flow diagram is out of MVP scope — V2 item. MVP CRM is queryable via API + raw PostgreSQL, no UI.
- Meeting booking = Calendly link injection (not a custom scheduler) for MVP.
- You personally take over via your own WhatsApp Business app after handoff — no separate "agent dashboard" needed for one operator.
- **Build methodology:** follows the Universal Build Flow — vertical slices, not horizontal layers. Each stage after Core Baseline is a complete, demoable segment of the conversation funnel (webhook → state logic → Gemini → persistence → reply), not "all state machine code, then all messaging code." Supporting principles applied and called out explicitly: Business Models over raw dicts, Single Source of Truth in Postgres, AI output passes schema validation *and* business-rule validation before being trusted, deterministic-first reasoning stated per design choice, and failure-type classification (input/business/dependency/system) over generic error handling.

---

## 0. STAGE TABLE

Restructured around vertical slices of the conversation funnel — each stage after Core Baseline is a complete, demoable segment (webhook → state logic → Gemini → persistence → WhatsApp reply), not "all state machine code" as one block.

| Stage | Name | Purpose |
|-------|------|---------|
| 0 | Project Foundation | Repo, env, Meta App + WhatsApp Cloud API registration, Postgres schema, config — nothing functional yet |
| 1 | Core Baseline (deterministic, no AI) | Webhook receiver, signature verification, dedupe, persist raw inbound message, send a hardcoded/stub reply. Proves the webhook→DB→send loop works with zero Gemini calls |
| 2 | Vertical Slice — Early Funnel | Gemini wired in for Greeting → Service Identification → Requirement Gathering → Business Context. A lead can hold a real, state-tracked conversation up to (not including) qualifying questions |
| 3 | Vertical Slice — Qualification | Budget → Timeline → Contact Verification → Qualification Decision, plus rule-based scoring. A lead can be fully qualified or disqualified end-to-end |
| 4 | Vertical Slice — Meeting & Handoff | Meeting Offer, Calendly injection, human handoff message, email summary, n8n notify-only ping. Full happy path complete |
| 5 | Harden | Two-step AI output verification, failure-type handling, 24h-window edge cases, structured logging |
| 6 | Deployment | Render hosting, webhook HTTPS, env vars, n8n (notifications only) |
| 7 | Polish & Portfolio | README, demo recording (screen-recorded WhatsApp thread), edge cases, GitHub, final review |

---

## 1. PROJECT SNAPSHOT

| Field | Detail |
|-------|--------|
| Project name | LeadPilot — AI WhatsApp Lead Qualifier |
| One-line description | An AI agent that qualifies inbound WhatsApp leads from your portfolio site before you ever see them |
| Core capability | State-driven conversational lead qualification over WhatsApp, with structured CRM handoff |
| Target build time | 3–4 weeks solo, part-time |
| Portfolio tags | Agentic, Gemini, FastAPI, PostgreSQL, WhatsApp Cloud API, State Machines, Vertical Slice Delivery |
| AI/ML category | Agentic / Structured Conversation (not RAG — no retrieval corpus involved) |

---

## 2. WHAT IT SOLVES

**Problem.** Every portfolio WhatsApp inquiry currently demands your full manual attention from message one — even tire-kickers, vague "hi, interested" pings, and people who vanish after two replies. You're doing triage work an agent should front-run.

**Why it's non-trivial:**
- Conversation must be *state-driven*, not a free-form chatbot — the LLM has to know what's collected, what's missing, and when to stop, which means every Gemini call is constrained by an explicit state object, not just chat history.
- WhatsApp's 24-hour session window forces explicit handling of stale conversations — this isn't optional plumbing, it's core to whether leads silently die.
- Lead scoring has to be explainable (you'll defend it in interviews) — not a black-box LLM confidence number.
- Idempotent webhook handling — Meta retries delivery on non-200 responses, so duplicate message processing is a real failure mode, not a hypothetical.
- **Verifying AI output requires two distinct checks, not one** — a Gemini response can be schema-valid JSON and still reach a nonsensical state (e.g. `next_state: qualification_decision` while `budget_range` is still null) — see Section 10.

---

## 3. MVP SCOPE

**Features included:**
- Inbound WhatsApp webhook receiver with signature verification
- State machine: Greeting → Service ID → Requirements → Business Context → Budget → Timeline → Contact Verification → Qualification Decision → Meeting Offer → Handoff
- Gemini-driven response generation constrained to current state's allowed outputs
- PostgreSQL persistence of every lead, conversation, message, and qualification result — the single source of truth for conversation state (see Section 4)
- Lead scoring (rule-based, explainable — see Section 10)
- Email summary on qualification complete (SMTP or Resend free tier)
- Calendly link offer when lead is qualified + serious
- Human handoff message to lead + notification email/Slack to you
- **Business-rule validation** on every Gemini output, distinct from schema validation (see Section 9a and Section 10)
- **Basic structured logging** of every state transition (lead_id, from_state, to_state, gemini_call_ms, outcome) — not deferred to V2

**Features deliberately excluded (V2):**
- Multi-business / multi-tenant support
- Admin dashboard UI
- Voice note transcription
- Multi-language support
- A/B testing of prompts
- Automated meeting confirmation parsing from Calendly webhooks back into CRM
- Full trace-level observability (Langfuse) — basic structured logs are MVP, Langfuse tracing is a V2 upgrade

**Acceptance criteria:**
- [ ] Sending the portfolio's predefined WhatsApp message triggers a greeting reply within 5s
- [ ] A full happy-path conversation (8–10 turns) ends in a qualification record written to PostgreSQL
- [ ] Lead score is visible in the DB row and traceable to specific scoring factors
- [ ] Summary email arrives within 10s of qualification completion
- [ ] Sending the same webhook payload twice does not create duplicate messages in DB
- [ ] A lead going silent for 25+ hours cannot receive a free-text re-engagement (template-only enforced)
- [ ] A Gemini response that is schema-valid but reaches `qualification_decision` with a required field still null is caught by business-rule validation and does not advance state
- [ ] The project was built and committed in vertical slices (Stage 1 → 4), each independently demoable — verified by `git log --oneline`

---

## 4. ARCHITECTURE

```
                    ┌─────────────────────┐
                    │  hoshangsheth.com    │
                    │  (WhatsApp CTA btn)  │
                    └──────────┬───────────┘
                               │ wa.me link w/ predefined text
                               ▼
                    ┌─────────────────────┐
                    │  WhatsApp Cloud API   │
                    │  (Meta)               │
                    └──────────┬───────────┘
                  webhook POST │  ▲ send message (Graph API)
                               ▼  │
                    ┌─────────────────────┐
                    │   FastAPI Backend     │
                    │  /webhook/whatsapp    │
                    │  - sig verification   │
                    │  - dedupe by msg_id    │
                    └──────────┬───────────┘
                               ▼
                    ┌─────────────────────┐
                    │  Conversation Engine  │
                    │  (state machine,      │
                    │   Python, in FastAPI) │
                    └──────────┬───────────┘
                               ▼
                    ┌─────────────────────┐
                    │   Gemini API          │
                    │  (gemini-3.6-flash,   │
                    │   JSON mode)          │
                    └──────────┬───────────┘
                               ▼
                    ┌─────────────────────┐
                    │  Schema + Business    │
                    │  Rule Validation       │
                    │  (validation/)         │
                    └──────────┬───────────┘
                               ▼
                    ┌─────────────────────┐
                    │   PostgreSQL          │
                    │  leads / conversations│
                    │  / messages / scores  │
                    │  — SINGLE SOURCE OF   │
                    │  TRUTH for state       │
                    └──────────┬───────────┘
                               ▼
              ┌────────────────┴────────────────┐
              ▼                                  ▼
    ┌─────────────────┐              ┌──────────────────────┐
    │  Email Service    │              │  n8n (notify-only)   │
    │  (Resend free tier)│              │  Slack/email ping to │
    │  summary → you     │              │  you on handoff      │
    └─────────────────┘              └──────────────────────┘
```

**Request flow:**
1. Visitor clicks WhatsApp CTA → opens chat with predefined service-interest text
2. Visitor sends message → Meta POSTs to `/webhook/whatsapp`
3. FastAPI verifies signature, dedupes on `message_id`, loads/creates `lead` + `conversation` — **the DB row loaded here, not any in-memory cache, is authoritative for current state**
4. Conversation Engine determines current state from the persisted row, builds constrained prompt with state context
5. Gemini returns structured JSON (next message text + extracted fields + state transition signal)
6. Output passes schema validation, then business-rule validation (Section 10) — only a result that passes both advances state
7. Engine persists message, updates conversation state, updates lead record — this write is what makes the new state authoritative, not the in-memory result object
8. FastAPI sends reply via WhatsApp Graph API (`POST /messages`)
9. On reaching `Qualification Decision` state: compute lead score, write qualification record
10. On qualified: trigger email summary + Calendly offer + handoff message + notify you
11. You take over manually in WhatsApp Business app — system stops auto-responding (flag on lead)

**Where AI/ML inference happens:** Every inbound message triggers exactly one Gemini call inside the Conversation Engine, which both extracts structured fields from free text and generates the next state-appropriate reply in a single JSON-mode response.

**Key design decisions:**

| Decision | Rationale |
|----------|-----------|
| State machine in Python, not n8n | Debuggable, testable, version-controlled; n8n nodes can't express conditional state logic cleanly at this complexity |
| Single Gemini call does extraction + reply generation | Halves API calls vs. separate extract/generate steps — critical given free-tier rate limits |
| Dedupe by `wa_message_id` at webhook layer | Meta retries on non-200/slow response; without this, duplicate processing corrupts conversation state |
| `human_takeover` boolean flag on lead, checked before every auto-reply | Hard stop so the bot never talks over you mid-handoff |
| Rule-based lead score, not LLM-judged score | Explainable in interviews; LLM scoring is non-deterministic and hard to defend — see Section 10's deterministic-first reasoning |
| **The `leads`/`conversations` Postgres rows are the single source of truth** | Every webhook invocation is a fresh process — nothing about conversation state may live only in memory between requests. The DB row loaded at the top of the handler is authoritative; the handler never trusts a cached or passed-in state object |
| **Dependency direction is one-way**: `webhook.py` depends on `conversation_engine.py`, which depends on `gemini_client.py`/`scoring.py`/repositories — never the reverse | A code-review checklist item: `gemini_client.py` never imports from `webhook.py`, `states/*.py` never issue raw SQL directly (goes through a repository function) |
| Gemini output validated in two steps (schema, then business-rule) before any state advance | A schema-valid response can still be nonsensical — e.g. reaching `qualification_decision` with `budget_range` still null. See Section 10 |

---

## 5. TECH STACK

| Tool | Role | Why over alternatives |
|------|------|-----------------------|
| WhatsApp Cloud API | Messaging channel | Required by spec — official Meta API, free tier covers low volume |
| FastAPI | Backend + conversation engine | Async-native, fits webhook + LLM I/O pattern; replaces n8n as the brain |
| PostgreSQL | CRM persistence, single source of truth | Relational integrity for leads↔conversations↔messages↔qualification — not a NoSQL fit |
| Gemini API (`gemini-3.6-flash`) | LLM | Free tier (15 RPM, 1500 req/day) sufficient for MVP volume; JSON mode supports structured extraction |
| Pydantic | Schema validation for Gemini output + typed models everywhere (no raw dicts crossing layers) | Enforces shape at the boundary; paired with a separate business-rule validation step |
| n8n (self-hosted, free) | Notification glue only | Demoted from orchestration; used for Slack/email pings on handoff — swap-out friendly if abandoned later |
| Resend (free tier, 100 emails/day) | Email summaries | Simpler than raw SMTP, generous free tier, good deliverability |
| Render | Backend hosting | Free tier web service, HTTPS out of the box (required by Meta for webhooks) |
| Calendly (free tier) | Meeting booking | No custom scheduler needed for MVP; embed link only |

**Flagged paid-risk dependency:** WhatsApp Cloud API itself is free for the first 1,000 conversations/month (service conversations), then billed per-conversation by Meta. At expected portfolio inquiry volume this stays free, but it is not unconditionally free like Gemini's quota — note this explicitly in the README.

---

## 6. FOLDER STRUCTURE

**Split repo decision:** Single repo (monorepo) — there's no separate frontend to deploy, so a split repo adds no isolation benefit and only adds overhead for a solo dev.

**Dependency direction, stated explicitly:** `webhook.py` → `conversation_engine.py` → (`gemini_client.py`, `scoring.py`, `states/*.py`) → repositories/`db.py`. Nothing downstream imports upstream — `gemini_client.py` never imports from `webhook.py`, and `states/*.py` never issue raw SQL directly.

```
leadpilot/
├── backend/
│   ├── main.py                  # FastAPI app, route registration, CORS/webhook setup
│   ├── config.py                # env loading, constants
│   ├── models.py                # SQLAlchemy models: Lead, Conversation, Message, Qualification, MeetingRequest, EmailLog — the single source of truth
│   ├── schemas.py                # Pydantic request/response schemas + typed models for Gemini output (no raw dicts)
│   ├── db.py                     # engine, session, init_db
│   ├── webhook.py                # /webhook/whatsapp receiver + Meta signature verification
│   ├── whatsapp_client.py        # send_message(), template handling, 24h window check
│   ├── conversation_engine.py    # state machine core: get_state(), advance_state(), build_prompt()
│   ├── states/
│   │   ├── greeting.py
│   │   ├── service_identification.py
│   │   ├── requirement_gathering.py
│   │   ├── business_context.py
│   │   ├── budget.py
│   │   ├── timeline.py
│   │   ├── contact_verification.py
│   │   ├── qualification_decision.py
│   │   ├── meeting_offer.py
│   │   └── handoff.py
│   ├── gemini_client.py          # Gemini call wrapper, JSON mode, retry/backoff — returns a typed ConversationTurnResult, never a raw dict
│   ├── validation/
│   │   └── ai_output_rules.py    # business-rule validation, run after schema validation — see Section 10
│   ├── observability/
│   │   └── logger.py             # structured logging helper — one line per state transition
│   ├── scoring.py                # rule-based lead scoring
│   ├── email_service.py          # Resend integration, summary template
│   ├── seed.py                   # test data
│   ├── tests/
│   │   ├── test_state_transitions.py
│   │   └── test_validation.py    # business-rule validation catches inconsistent Gemini output
│   ├── requirements.txt
│   └── .env
├── n8n/
│   └── handoff-notify-workflow.json   # exported n8n workflow (notify-only)
├── Makefile
└── README.md
```

---

## 7. BUILD PHASES

| Phase | Stage | What gets built | Output | Commit checkpoint | Unblocks |
|-------|-------|----------------|--------|--------------------|----------|
| 0 — Foundation | Stage 0 | Repo, Meta App + WhatsApp Cloud API setup, Postgres schema, config | Working scaffold, webhook verified by Meta | `chore: project scaffold, Meta webhook verified, Postgres schema, env config` | Phase 1 |
| 1 — Core Baseline | Stage 1 | Webhook receiver, signature verification, dedupe, persistence, hardcoded/stub reply — **no Gemini call** | Webhook receives, persists, and replies with zero AI involved | `feat: core baseline — webhook receiver, dedupe, persistence (no AI)` | Phase 2 |
| 2 — Vertical Slice: Early Funnel | Stage 2 | Gemini wired in for Greeting → Business Context, schema + business-rule validation | A lead can hold a real state-tracked conversation through business context | `feat: early-funnel vertical slice — Gemini wired, schema + business-rule validation` | Phase 3 |
| 3 — Vertical Slice: Qualification | Stage 3 | Budget → Qualification Decision states, rule-based scoring | A lead can be fully qualified/disqualified end-to-end | `feat: qualification vertical slice — scoring, decision logic` | Phase 4 |
| 4 — Vertical Slice: Meeting & Handoff | Stage 4 | Meeting Offer, Calendly injection, handoff message, email summary, n8n notify | Full happy path complete, locally | `feat: meeting & handoff vertical slice — full happy path complete` | Phase 5 |
| 5 — Harden | Stage 5 | Failure-type handling (Section 9a), 24h-window edge cases, structured logging | System behaves correctly when things go wrong, not just on the happy path | `feat: hardening — failure-type handling, 24h window edge cases, structured logging` | Phase 6 |
| 6 — Deployment | Stage 6 | Render hosting, HTTPS webhook, n8n notify workflow | Live system reachable by Meta | `chore: deployment — Render hosting, webhook re-registration, n8n notify workflow` | Phase 7 |
| 7 — Polish | Stage 7 | README, demo recording, edge cases, final review | Portfolio-ready repo | `docs: README, demo recording, final review` | — |

**Commit rule:** commit at the end of every vertical slice — never batch phases into one dump commit. Given the Meta business-verification lag (Section A, Risk Register) and the multi-week timeline, this history also proves the project was built incrementally over the stated 3–4 weeks, not assembled the night before a portfolio review.

---

## 8. STAGE 0 — PROJECT FOUNDATION

### Prerequisites Table

| Tool | Required Version | Check Command |
|------|-----------------|---------------|
| Python | 3.11+ | `python --version` |
| PostgreSQL | 15+ | `psql --version` |
| Meta Developer Account | n/a | manual — developers.facebook.com |
| ngrok (local webhook testing) | latest | `ngrok version` |
| n8n (self-hosted, optional) | latest | `npx n8n --version` |

### Meta / WhatsApp Cloud API Setup (do this before any code)

1. Create a Meta App at developers.facebook.com → add "WhatsApp" product
2. Get a test phone number (free, Meta-provided) for dev — register your real business number only at deploy time
3. Generate a temporary access token (24h) for dev; generate a permanent System User token before Stage 6
4. Note: `PHONE_NUMBER_ID`, `WABA_ID`, `APP_SECRET`, `VERIFY_TOKEN` (you define this string yourself)
5. Webhook URL during dev: ngrok tunnel pointed at `localhost:8000/webhook/whatsapp`
6. Subscribe webhook to `messages` field only — not the full event firehose

### Repo Initialisation

```bash
mkdir leadpilot && cd leadpilot
git init
```

`.gitignore`:
```
__pycache__/
*.pyc
.env
venv/
*.egg-info/
.DS_Store
n8n_data/
```

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv \
            google-generativeai httpx pydantic[email] resend pytest
pip freeze > requirements.txt
```

`.env`:
```
# WhatsApp Cloud API
WHATSAPP_TOKEN=              # permanent system user token (temp token in dev)
PHONE_NUMBER_ID=              # from Meta App dashboard
WABA_ID=                      # WhatsApp Business Account ID
APP_SECRET=                   # for webhook signature verification
VERIFY_TOKEN=leadpilot_verify_2026   # you define this; used in webhook GET handshake

# LLM
GEMINI_API_KEY=                # aistudio.google.com, free tier

# DB
DATABASE_URL=postgresql://user:pass@localhost:5432/leadpilot

# Email
RESEND_API_KEY=                 # resend.com free tier
NOTIFY_EMAIL=hoshangsheth@gmail.com

# Meeting
CALENDLY_LINK=https://calendly.com/hoshangsheth/intro-call
```

### PostgreSQL Schema (Stage 0 — created before logic, see full DDL in Section 7)

```bash
createdb leadpilot
psql leadpilot -f schema.sql
```

### Skeleton Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app instance, route mounting, startup DB init |
| `config.py` | env var loading |
| `db.py` | SQLAlchemy engine/session |
| `models.py` | ORM models — empty class stubs initially |
| `webhook.py` | GET (verification handshake) + POST (message receiver) stubs |
| `conversation_engine.py` | `process_message(lead_id, text) -> reply` stub |
| `gemini_client.py` | `call_gemini(prompt, schema) -> ConversationTurnResult` stub, `MOCK_LLM` toggle |
| `validation/ai_output_rules.py` | Business-rule validation stub, run after schema validation |
| `observability/logger.py` | Structured logging helper stub |

### config.py

```python
import os
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
APP_SECRET = os.getenv("APP_SECRET")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")
CALENDLY_LINK = os.getenv("CALENDLY_LINK")
MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"

WHATSAPP_SESSION_WINDOW_HOURS = 24
```

### Test / Seed Data

| Filename | Fields / Columns | Tests which stage |
|----------|-----------------|-------------------|
| `seed_leads.json` | name, phone, service_interest, full transcript array | Stage 3 happy path |
| `seed_webhook_payload.json` | raw Meta webhook POST body shape | Stage 1 webhook parsing |
| `seed_edge_cases.json` | empty message, emoji-only, 25h-stale conversation, schema-valid-but-inconsistent Gemini fixture | Stage 5 hardening |

### Local Dev Shortcuts

```python
# gemini_client.py
from schemas import ConversationTurnResult

async def call_gemini(prompt: str, schema: dict) -> ConversationTurnResult:
    if config.MOCK_LLM:
        return ConversationTurnResult(
            reply_text="mock reply", extracted_fields={}, next_state="greeting", confidence_flag="high"
        )  # typed model, not a raw dict — see Section 4's Business Models decision
    # real call below
```

Makefile:
```makefile
dev:
	cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000

tunnel:
	ngrok http 8000

seed:
	cd backend && python seed.py

test:
	cd backend && pytest tests/ -v
```

### Stage 0 Completion Checklist

- [ ] Meta App created, test WhatsApp number working, webhook verified via GET handshake
- [ ] Git repo initialised, `.gitignore` committed, no `.env` in history
- [ ] Backend venv created, all packages installed, `requirements.txt` frozen
- [ ] `.env` present with all keys stubbed
- [ ] PostgreSQL DB created, schema applied
- [ ] `config.py` loads without error
- [ ] All skeleton files created, including `validation/` and `observability/`
- [ ] ngrok tunnel reachable from Meta webhook test tool
- [ ] `MOCK_LLM=true` confirmed working, returns a typed `ConversationTurnResult`
- [ ] Makefile `make dev` starts uvicorn clean
- [ ] Phase 0 commit made: `chore: project scaffold, Meta webhook verified, Postgres schema, env config`

---

## 9. API CONTRACT

### `GET /webhook/whatsapp` — Meta verification handshake

| Field | Detail |
|-------|--------|
| Query params | `hub.mode`, `hub.verify_token`, `hub.challenge` |
| Success response | Plain text echo of `hub.challenge` (200) if token matches `VERIFY_TOKEN` |
| Error responses | 403 if token mismatch |
| Auth | `VERIFY_TOKEN` match only |

### `POST /webhook/whatsapp` — incoming message receiver

| Field | Detail |
|-------|--------|
| Content-Type | `application/json` |
| Request body | Meta webhook payload (entry → changes → value → messages[]) |
| Success response | `200 {}` immediately (Meta requires fast ack) — processing happens async after ack |
| Error responses | `403` on signature mismatch (`X-Hub-Signature-256` HMAC check) |
| Streaming | No |
| Auth | HMAC-SHA256 signature verification using `APP_SECRET` |

### `GET /leads/{lead_id}` — internal CRM read

| Field | Detail |
|-------|--------|
| Success response | `{lead, conversation_state, qualification, score, messages[]}` |
| Error responses | `404` if not found |
| Auth | Bearer token (simple static API key for MVP — single operator) |

### `POST /leads/{lead_id}/handoff` — manual override

| Field | Detail |
|-------|--------|
| Request body | `{"reason": "string"}` |
| Success response | `{"status": "handed_off"}` — sets `human_takeover=true` |
| Auth | Bearer token |

### `GET /health`

| Field | Detail |
|-------|--------|
| Success response | `{"status": "ok"}` |
| Auth | None |

---

## 9a. Error Handling — Failure Types

| Type | Example in this project | Response |
|---|---|---|
| **Input failure** | Malformed webhook payload, missing `entry`/`changes` structure | `403`/`400` — logged, acked to Meta anyway (Meta doesn't retry on our validation errors, only on non-200) |
| **Business failure** | Lead's message doesn't map cleanly to any expected field (garbage/emoji-only input) | Not an error — state machine asks a clarifying question (max 2 per state, Section 10), conversation continues |
| **Dependency failure** | Gemini API times out or hits 429 | Retry with backoff (max 2 — WhatsApp UX can't tolerate long delays); on exhaustion, send a filler message and queue for retry, never leave the lead without a reply |
| **System failure** | Unhandled exception inside `conversation_engine.py` | Caught at the webhook handler's top level, logged with full context via `observability/logger.py`, lead flagged for manual review — never a silent drop |

This classification is why Section 9's `POST /webhook/whatsapp` always returns `200` fast regardless of downstream outcome — Meta's retry behavior only cares about the ack, not the business result, so failure handling happens entirely inside the async processing path, not in the response Meta sees.

---

## 10. AI/ML DESIGN

### Deterministic vs. Probabilistic Processing — the cheapest-valid-solution ladder

Checked against the ladder (rule → deterministic algorithm → classical ML → LLM) before committing to Gemini for each piece of this system:

- **Lead scoring: fully rule-based, no LLM.** Considered and rejected an LLM-judged score — a numeric score derived from an opaque model call is nearly impossible to defend in an interview or explain to a client ("why did this lead score 72?"). A weighted rule set over collected fields (budget disclosed? timeline urgent? contact verified?) is fully auditable and was the correct choice, not a shortcut.
- **State transition logic: deterministic, not LLM-decided.** The state machine's allowed transitions are hardcoded in `states/*.py` — Gemini's `next_state` output is a *proposed* transition validated against the deterministic transition table (Section 11), never trusted blindly. This is the business-rule validation step below.
- **Conversation reply + field extraction: LLM, deliberately.** This is the one place semantic reasoning is genuinely required — free-text answers like "probably around 1-2 lakhs, not totally fixed" need to be parsed into structured fields, which a rule-based parser can't reliably do across the range of ways a real person phrases an answer.

**Net result: 1 of 3 major decisions in this system (reply generation + extraction) needs an LLM.** Scoring and state-transition validity are both deterministic — worth stating explicitly in the portfolio write-up (Stage 7) as a sign of engineering judgment, not just AI usage.

### Model Selection

| Model | Provider | Free Tier Limits | Role | Why over alternatives |
|-------|----------|------------------|------|------------------------|
| `gemini-3.6-flash` | Google | 15 RPM, 1500 req/day, 1M TPM | Conversation reply + field extraction | Single-call JSON mode covers both jobs; fastest free-tier option for sub-5s WhatsApp reply latency |

**Embedding Strategy:** N/A — no document corpus or semantic search in this system; all context is structured state + conversation history.

**RAG Pipeline:** N/A — qualification logic is rule/state-driven, not retrieval-driven.

### Prompt Design

**System prompt structure:**
- Role framing: "You are a lead-qualification assistant for [Hosh]'s freelance AI/ML engineering services. You are not a general chatbot — you only operate within the current conversation state."
- Output format constraint: strict JSON schema, no markdown, no preamble
- Explicit instruction: "Never invent information the user hasn't provided. If a required field is still missing, ask for it — do not guess."
- Forbidden: quoting prices/timelines as commitments, making promises about deliverables

**User prompt template:**
```
CURRENT_STATE: {state_name}
FIELDS_COLLECTED: {collected_fields_json}
FIELDS_MISSING: {missing_fields_list}
CONVERSATION_HISTORY: {last_6_messages}
LATEST_USER_MESSAGE: {user_text}

Generate the next reply and extract any new fields from the latest message.
```

**JSON mode:** Yes — required for reliable field extraction at scale on free-tier budget (no room for parse-retry loops on every call).

Schema (validated into a typed `ConversationTurnResult` model, never handled as a raw dict downstream):
```python
from pydantic import BaseModel
from typing import Literal

class ConversationTurnResult(BaseModel):
    reply_text: str
    extracted_fields: dict[str, str]
    next_state: str          # proposed — validated against the deterministic transition table before trusting it
    confidence_flag: Literal["high", "low"]
```

**Few-shot examples:** Yes — one example per state embedded in that state's prompt module (see `states/*.py`), e.g. for `budget`:
```
Input: "probably around 1-2 lakhs, not totally fixed"
Output: {"reply_text": "Got it — flexible budget in the ₹1-2L range, noted...", "extracted_fields": {"budget_range": "1-2L INR", "budget_flexibility": "flexible"}, "next_state": "timeline", "confidence_flag": "high"}
```

### AI Output Verification — two steps, not one

Schema validation confirms the JSON has the right *shape*. It does not confirm the proposed state transition or extracted fields make *business sense*. Both steps run on every Gemini call, in order:

**Step 1 — Schema validation:** Pydantic validates the raw JSON against `ConversationTurnResult`. Malformed JSON triggers one retry with a stricter prompt, then a filler message on second failure (Section 9a, dependency failure).

**Step 2 — Business-rule validation** (`validation/ai_output_rules.py`):
```python
def validate_turn_result(result: ConversationTurnResult, current_state: str) -> ConversationTurnResult:
    """Catches schema-valid but nonsensical proposed transitions."""
    allowed_next = TRANSITION_TABLE[current_state]  # deterministic table, states/*.py
    if result.next_state not in allowed_next:
        result.next_state = current_state  # reject the jump, stay put, ask again
        result.confidence_flag = "low"

    if result.next_state == "qualification_decision":
        required = {"budget_range", "timeline_expectation", "contact_name"}
        collected = set(result.extracted_fields.keys())
        if not required.issubset(collected):
            result.next_state = current_state  # can't qualify on missing critical fields

    return result
```

A Gemini response proposing to jump straight to `qualification_decision` without a budget on record is schema-valid JSON — Step 2 is what stops it from actually advancing state. This is distinct from and in addition to Step 1, not a rename of it.

### Agentic Design

- **Tools:** None for MVP — no function-calling/tool-use loop. The "agent" behavior is entirely state-transition logic, kept deliberately simple and auditable.
- **Memory:** Short-term only — last 6 messages + structured `collected_fields` passed every call. No long-term vector memory (no need; each lead is a bounded conversation).
- **Loop logic:** Conversation advances exactly one state per Gemini call, capped at 15 total messages per conversation — if not qualified by then, forced handoff with partial data flagged `incomplete`.
- **Guardrails:** Hard message cap (15) prevents infinite loop; `confidence_flag: low` from Gemini (or set by business-rule validation rejecting a transition) triggers a clarifying question instead of state advance, max 2 clarifications per state before forced progression.

### Classical ML Model

N/A — lead scoring is rule-based (see Deterministic vs. Probabilistic Processing above), not a trained model, for explainability.

### Known Failure Modes

| Failure | Where it occurs | Mitigation |
|---------|----------------|------------|
| LLM returns malformed JSON | Step 1, before Pydantic validation | Retry once with stricter prompt; on second failure, send generic "let me get back to you" + flag for manual review |
| **Gemini proposes an invalid state jump or advances without required fields** | Step 2, business-rule validation | Transition rejected, state held, `confidence_flag` forced to `low` — see the validation function above |
| Free-tier rate limit hit (429) | Gemini API call during burst traffic | Exponential backoff (1s→2s→4s, max 2 retries — WhatsApp UX can't tolerate long delays); on exhaustion, queue reply and send "give me a moment" filler message |
| Meta webhook duplicate delivery | Webhook receiver | Dedupe on `wa_message_id` unique constraint in `messages` table before processing |
| 24h session window expired mid-conversation | Outbound send attempt | Check `last_inbound_at` before every send; if >24h, use approved template message instead of free-text, or queue for manual follow-up |
| User sends unsupported content (image, voice note, doc) | Webhook receiver | Detect message type; reply with text-only redirect: "I can only read text messages right now — could you type that out?" |
| Gemini extracts conflicting info across turns (budget mentioned twice, differs) | Field extraction | Latest value always overwrites; log both in `messages` audit trail for human review at handoff |

---

## 11. WHATSAPP MESSAGING LAYER (replaces Stage 3 — Frontend)

*This project has no traditional frontend. WhatsApp is the UI. This section replaces the skill's standard Stage 3, and is built incrementally across Stages 2–4, not as one lump — see Section 7.*

### Component Architecture

| Module | File Path | Responsibility | Ships in |
|--------|-----------|----------------|----------|
| Webhook Receiver | `webhook.py` | Verify signature, dedupe, ack fast, enqueue processing | Stage 1 |
| Send Wrapper | `whatsapp_client.py` | Build + send Graph API requests, handle template vs. free-text | Stage 1 |
| Window Checker | `whatsapp_client.py::is_within_session_window()` | Returns bool based on `last_inbound_at` | Stage 1 |
| Conversation Engine | `conversation_engine.py` | Orchestrates state → prompt → Gemini → validate → persist → reply | Stage 2 (early funnel), extended in Stages 3–4 |

### Conversation State Machine

The deterministic transition table referenced by Step 2 of AI Output Verification (Section 10):

| State | Entry Condition | Exit Condition | Transitions To | Ships in |
|-------|-----------------|-----------------|-----------------|----------|
| Greeting | First inbound message on new `lead` | Service interest acknowledged | Service Identification | Stage 2 |
| Service Identification | Greeting complete | `service_type` field populated | Requirement Gathering | Stage 2 |
| Requirement Gathering | Service known | Core requirement description captured | Business Context | Stage 2 |
| Business Context | Requirements captured | Company/individual, industry known | Budget | Stage 2 |
| Budget | Business context known | `budget_range` populated (or explicitly "not disclosed") | Timeline | Stage 3 |
| Timeline | Budget known | `timeline_expectation` populated | Contact Verification | Stage 3 |
| Contact Verification | Timeline known | Name + preferred contact method confirmed | Qualification Decision | Stage 3 |
| Qualification Decision | All required fields present, or message cap hit | Score computed | Meeting Offer or Handoff (if disqualified) | Stage 3 |
| Meeting Offer | Lead scored ≥ qualified threshold | Calendly link sent, accepted/declined noted | Human Handoff | Stage 4 |
| Human Handoff | Meeting offered (or disqualified path) | Handoff message sent, `human_takeover=true` set | Follow-up | Stage 4 |
| Follow-up | Handoff complete, lead silent >24h | Template re-engagement sent or marked `stale` | terminal | Stage 5 (hardening) |

### whatsapp_client.py — send wrapper

```python
import httpx
from datetime import datetime, timedelta
import config

async def is_within_session_window(last_inbound_at: datetime) -> bool:
    return datetime.utcnow() - last_inbound_at < timedelta(hours=config.WHATSAPP_SESSION_WINDOW_HOURS)

async def send_message(to: str, text: str, last_inbound_at: datetime, template_name: str | None = None):
    url = f"https://graph.facebook.com/v19.0/{config.PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}

    if not await is_within_session_window(last_inbound_at):
        if not template_name:
            raise ValueError("Outside 24h window — must use an approved template, not free text")
        payload = {
            "messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": template_name, "language": {"code": "en"}}
        }
    else:
        payload = {
            "messaging_product": "whatsapp", "to": to, "type": "text",
            "text": {"body": text}
        }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
```

### Edge Cases / States Test Matrix

| State | Test With | What to Verify |
|-------|-----------|-----------------|
| Webhook dedupe | Same payload sent twice | Only one `messages` row created |
| 24h window | `last_inbound_at` set to 25h ago | `send_message` raises without `template_name`, succeeds with one |
| Message cap | Seed conversation with 15 prior messages | Forced transition to Qualification Decision regardless of missing fields |
| Unsupported content | Image message payload | Redirect text sent, no Gemini call made (saves quota) |
| 429 from Gemini | Mocked 429 response | Backoff triggers, filler message sent if exhausted |
| **Invalid proposed transition** | Mock Gemini returning `next_state: "qualification_decision"` from `greeting` | Business-rule validation rejects it, state stays at `greeting`, `confidence_flag` forced low |

---

## 12. DEPLOYMENT NOTES

### Backend → Render

- Service type: Web Service
- Start command: `uvicorn main:app --host 0.0.0.0 --port 10000`
- Env vars: all from `.env`, set in Render dashboard — never commit real values
- **HTTPS is mandatory** — Meta will not register a webhook over plain HTTP. Render provides this automatically.

### Meta Webhook Re-registration at Deploy

1. After Render deploy, get the public URL (e.g. `https://leadpilot.onrender.com`)
2. In Meta App dashboard → WhatsApp → Configuration → update Callback URL to `https://leadpilot.onrender.com/webhook/whatsapp`
3. Re-verify using the same `VERIFY_TOKEN`
4. Switch from test number to your registered business number — requires business verification with Meta (can take days; start this early, not at the end)

### n8n Deployment (notify-only)

- Self-hosted free tier on Render (separate small service) or n8n cloud free trial
- Single workflow: webhook trigger from FastAPI on handoff → Slack/email notification to you
- Do not route core conversation logic through it — see Section 4 rationale

### Deployment Gotchas

- **Render cold starts (free tier):** 20-30s wake-up. A WhatsApp webhook that doesn't get a fast `200` ack gets retried by Meta, multiplying duplicate-processing risk. Mitigation: respond `200` immediately in the webhook handler before doing any processing (background task pattern), not after.
- **Gemini daily quota resets at midnight Pacific** — track usage; if you're demoing live for a portfolio review during a high-traffic day, you can run dry.
- **Meta business verification lag** — start this in Stage 0, not Stage 6, or deployment stalls for days waiting on Meta.

---

## 13. DEMO SCRIPT

Setup: have a test WhatsApp number ready, portfolio site live with the CTA button, screen recorder running.

| Step | Input | Expected output | Talking point |
|------|-------|------------------|----------------|
| 1 | Click WhatsApp CTA on portfolio | WhatsApp opens with predefined service-interest text | Shows real entry point, not a staged demo |
| 2 | Send the predefined message | Bot greets, asks first qualifying question within 5s | State machine kicks off |
| 3 | Answer 5–6 qualifying questions naturally | Bot tracks state, never re-asks answered fields | Demonstrates structured memory, not generic chat |
| 4 | Reach Qualification Decision | Bot sends Calendly link + handoff message | Show the lead score logic briefly on screen (DB query) |
| 5 | Check email | Structured summary email arrived | Closes the loop — this is what actually saves time |
| 6 | Pull up Postgres `leads` table | Full structured record, score, transcript | Shows the engineering, not just the chat UX |
| 7 | Show the business-rule validation test (`test_validation.py`) passing | Test output | "Schema-valid isn't the same as sensible — this is what actually stops a bad state jump" |
| 8 | Show GitHub commit history | — | "Built in vertical slices — each commit is a working conversation segment, not one dump at the end" |

---

## 14. POLISH & PORTFOLIO

### README Structure

| Section | Content |
|---------|---------|
| Title + tagline | LeadPilot — AI WhatsApp Lead Qualifier |
| Demo | Screen recording GIF of the full WhatsApp thread (no live URL — this isn't a public web app) |
| Description | What it does, why state-driven over chatbot |
| Stack badges | FastAPI, PostgreSQL, Gemini, WhatsApp Cloud API |
| Architecture | The ASCII diagram from Section 4 |
| Local dev setup | Stage 0 instructions, condensed |
| Why it's non-trivial | 24h window handling, dedupe, explainable scoring, two-step AI output verification |
| V2 ideas | From radar below |

### Edge Cases to Handle Before Going Live

| Edge Case | Where It Fails | Fix |
|-----------|----------------|-----|
| Duplicate webhook delivery | Message dedupe | Unique constraint on `wa_message_id` |
| 24h window expiry mid-conversation | Outbound send | Template fallback, see Section 11 |
| Gemini malformed JSON | Field extraction | Retry once, then generic filler + flag (Section 9a, dependency failure) |
| Gemini proposes invalid state jump | State advancement | Business-rule validation rejects it, state held (Section 10) |
| User sends only emoji/image | Field extraction | Type check before Gemini call, redirect text |
| Conversation exceeds 15 messages | State machine | Forced handoff with `incomplete` flag |

### GitHub Repo Checklist

- [ ] About description under 120 chars, mentions WhatsApp Cloud API + Gemini + FastAPI
- [ ] No `.env` in git history
- [ ] Demo GIF in README (not a wall of text)
- [ ] Topics: `agentic-ai`, `whatsapp-api`, `fastapi`, `gemini`, `lead-qualification`, `vertical-slice`
- [ ] Commit history shows vertical-slice progression (Section 7), not a single dump — `git log --oneline` reviewed before making the repo public

### Portfolio Write-Up (ready to paste)

**Title:** LeadPilot — AI WhatsApp Lead Qualification System

**2-sentence description:** An agentic system that qualifies inbound WhatsApp leads through a structured, state-driven conversation before handing off to a human — built to replace manual triage on a freelance portfolio site. The core engineering challenge was managing WhatsApp's 24-hour session window and Meta's webhook delivery guarantees inside a deterministic state machine, with every AI-proposed state transition validated against a hardcoded transition table before being trusted.

**Tech stack:** FastAPI, PostgreSQL, Gemini API, WhatsApp Cloud API, Pydantic, n8n

**GitHub repo description:** "Agentic AI lead qualifier over WhatsApp — state-driven conversation, two-step AI output validation, FastAPI, Gemini, PostgreSQL CRM."

### Final Review — Technical, Product, Portfolio

**Technical**
- [ ] Does the full happy path work end-to-end, all four vertical slices?
- [ ] Is dependency direction respected — no `states/*.py` issuing raw SQL, no `gemini_client.py` importing from `webhook.py`?
- [ ] Are errors classified by failure type (Section 9a), not generic 500s?
- [ ] Is every Gemini output both schema-validated *and* business-rule-validated (Section 10)?
- [ ] Is the Postgres row the only source of truth — no state trusted from memory across requests?
- [ ] Are secrets protected — no `.env`, tokens, or `APP_SECRET` in git history?
- [ ] Is deployment reproducible — webhook re-registration steps documented and followed?

**Product**
- [ ] Does it solve the original problem — no more manually triaging tire-kicker inquiries?
- [ ] Is the qualification bar sensible — would a real lead be correctly qualified or filtered?
- [ ] Does the handoff feel clean, not jarring, to a real lead?
- [ ] Would you actually trust this running unattended on your own site?

**Portfolio**
- [ ] Can you explain the state machine and transition table without re-reading the code?
- [ ] Can you explain why scoring is rule-based and reply generation is LLM-based (the deterministic-first ladder)?
- [ ] Can you explain what business-rule validation catches that schema validation can't?
- [ ] Can you demonstrate the full flow, live, in under 2 minutes?
- [ ] Can someone inspect the GitHub repo and see incremental, reviewable commits — one per vertical slice?
- [ ] Can you explain what V2 would add (dashboard, multi-tenant, eval harness) and why it's deliberately not in MVP?

### V2 Radar

| Feature | Complexity | Portfolio Signal |
|---------|-----------|--------------------|
| Admin dashboard (Next.js) for lead review | Medium | High — turns it into a full-stack product |
| Calendly webhook → auto-confirm meeting in CRM | Low-Medium | Medium |
| Multi-tenant (other businesses use it) | High | Very High — shows productization thinking |
| RAGAS-style eval harness on a golden conversation set | Medium-High | Very High — rare, signals production rigor |
| Voice note transcription (Whisper) | Medium | Medium |
| Upgrade structured logging to full Langfuse tracing | Low | High — MVP already has basic structured logs; this is the depth upgrade |

---

## A. RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Gemini free-tier 429 during traffic burst | Medium | High — bot goes silent mid-conversation | Backoff + filler message; monitor daily usage |
| Meta business verification delay blocks production number | High (common 3-7 day lag) | High — can't deploy live | Start verification in Stage 0, not Stage 6 |
| 24h window expiry silently drops leads | Medium | High — lost leads with no error visible | Explicit window check before every send, template fallback |
| Render cold start causes Meta webhook retry storm | Medium | Medium — duplicate processing | Fast `200` ack before processing (background task), dedupe constraint |
| Duplicate webhook delivery corrupts conversation state | Medium | High | Unique constraint on `wa_message_id`, idempotent processing |
| WhatsApp conversation-based billing exceeds free 1,000/month | Low at MVP scale | Medium — unexpected cost | Monitor Meta billing dashboard; alert at 80% |
| Business-rule validation never actually catches anything in the demo | Low | Low — a weak demo moment, not a functional risk | Deliberately seed the invalid-transition fixture (Section 11 test matrix) rather than leaving it to chance |

---

## B. FREE-TIER BUDGET & LIMITS

| Component | Provider | Free Tier Limit | Est. Usage at 50 leads/day (≈8 msgs/lead) | Headroom |
|-----------|----------|------------------|----------------------------------------------|----------|
| LLM inference | Gemini 3.6 Flash | 1,500 req/day, 15 RPM | ~400 req/day | Comfortable at this volume; tight if leads spike |
| WhatsApp messaging | Meta Cloud API | 1,000 free service conversations/month | ~1,500/month at 50/day | **Will breach** — budget for Meta billing past ~33 leads/day sustained |
| Backend hosting | Render free | 750 hrs/month | ~720 hrs (always-on) | ~30 hr buffer — tight |
| Email | Resend free | 100/day | ~10-15/day (qualified leads only) | High headroom |
| DB | Render Postgres free / Supabase free | 1GB | Negligible at this scale | High headroom |

**Free-tier breach trigger:** WhatsApp conversation billing is the first wall you'll hit, not Gemini. Flag this explicitly in your README and decide your breach threshold (~33 qualified-enough leads/day) before launch — don't discover it from a Meta invoice.
