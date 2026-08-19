"""FastAPI application entrypoint. Wires up logging, the DB schema, the WhatsApp webhook
router, and a bare health-check endpoint for the hosting platform.
"""

import logging

from fastapi import FastAPI
from db import init_db
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
