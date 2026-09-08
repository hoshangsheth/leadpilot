"""HTTP transport layer for Meta's WhatsApp Cloud API webhook. Handles the GET verification
handshake and the POST delivery endpoint (signature check + fast ack), then hands the payload
off to message_handler for all persistence and conversation-orchestration logic.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Request, Response, BackgroundTasks

import config
from message_handler import process_payload

router = APIRouter()
logger = logging.getLogger("leadpilot.webhook")


@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    # compare_digest, not ==, for the same reason the POST handler's signature check uses it:
    # a plain string comparison short-circuits on the first differing byte and leaks the
    # token's prefix through response timing. Cheap to do correctly.
    if mode == "subscribe" and token and hmac.compare_digest(token, config.VERIFY_TOKEN):
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()

    if not _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256", "")):
        return Response(status_code=403)

    payload = await request.json()
    background_tasks.add_task(process_payload, payload)
    return {}


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(config.APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)
