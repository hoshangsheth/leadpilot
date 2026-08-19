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
