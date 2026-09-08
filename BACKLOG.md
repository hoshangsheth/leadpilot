# LeadPilot — Backlog

Deliberately deferred work. Each entry records what the gap is, what currently covers it,
and what would justify doing it — so a future decision isn't made from scratch.

---

## Durable message queue (replaces the startup recovery sweep)

**Status:** deferred, 2026-09-08. Not needed yet.

**The gap.** `webhook.py` acks Meta with a 200 immediately and processes the message in a
FastAPI background task in the same process. If the process dies in the few seconds that
takes — a Render deploy, a restart, an OOM kill — the work is lost permanently. Meta will
not resend a message it has already been told was received, and no exception is raised, so
none of the existing error handling can catch it.

**What covers it today.** `recovery.py` runs a sweep at startup, finds conversations whose
last message was the lead's with no reply after it (excluding `human_takeover` ones), and
emails Hoshang so he can reply manually. The lead is recovered by a human rather than
automatically — which closes the "someone vanishes silently" hole, just not the delivery
gap itself.

**The middle option (do this first if it's ever needed).** Persist the raw inbound payload
to Postgres *before* acking Meta, and have the startup sweep reprocess those rows instead
of only alerting. Reuses infrastructure that already exists, no new service, roughly an
hour of work, and gets most of the benefit.

**The full version.** Durable job store (job table, Redis, or SQS) written before the ack; a
worker that marks a job done only after the reply is actually delivered; retry and
idempotency logic; dead-letter handling; queue-depth monitoring. Realistically a second
Render service.

**What would justify building it:**
- A startup alert actually firing in real use — that's the signal it happens often enough
  to be worth automating.
- Running on a Render tier that spins down or restarts frequently, which would turn a rare
  failure into a routine one (and would also mean cold-start delays on inbound webhooks —
  worth checking independently of this).
- Enough inbound volume that manually re-replying to stranded leads stops being realistic.
