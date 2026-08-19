"""FastAPI application entrypoint. Wires up logging, the DB schema, the WhatsApp webhook
router, and a bare health-check endpoint for the hosting platform.
"""

import logging

from fastapi import FastAPI
from db.db import init_db
from webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="LeadPilot")
app.include_router(webhook_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    # Some uptime probes / platform health checks hit "/" rather than "/health" -- without
    # this it 404s, which some monitors treat as "service down" even though the app is fine.
    return {"status": "ok"}
