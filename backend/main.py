from fastapi import FastAPI
from db import init_db
from webhook import router as webhook_router

app = FastAPI(title="LeadPilot")
app.include_router(webhook_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
