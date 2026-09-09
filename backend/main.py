"""FastAPI application entrypoint. Wires up logging, the DB schema, the WhatsApp webhook
router, and a bare health-check endpoint for the hosting platform.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.db import init_db
from recovery import sweep_stranded_messages
from webhook import router as webhook_router
from widget import router as widget_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="LeadPilot")

# Scoped to the actual site plus local dev, not "*": this is additive middleware for the new
# browser-facing widget endpoint only. The WhatsApp webhook is server-to-server (Meta calling
# in with its own signature header, no browser involved), so CORS has no effect on it either
# way — this cannot change WhatsApp behavior.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://hoshangsheth.com", "http://localhost:3000"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(widget_router)


@app.on_event("startup")
def on_startup():
    init_db()
    # A message being processed when the service restarted was acked to Meta and will never
    # be resent, so nothing else can recover it — see recovery.py. Runs after init_db so the
    # tables are guaranteed to exist on a first boot, and can never block startup itself.
    sweep_stranded_messages()


@app.get("/health")
@app.head("/health")
def health():
    return {"status": "ok"}


@app.get("/")
@app.head("/")
def root():
    # Some uptime probes / platform health checks hit "/" rather than "/health", and some use
    # HEAD instead of GET -- confirmed live in the Render logs (HEAD / -> 405) once GET / was
    # added but HEAD wasn't, since this FastAPI/Starlette version doesn't auto-add it. Explicit
    # @app.head on both routes so no health-check verb/path combination ever 404s or 405s.
    return {"status": "ok"}
