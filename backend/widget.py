"""Website chat widget: a separate, FAQ-only channel from the WhatsApp funnel.

Answers questions about the practice using the same company_knowledge reference facts the
WhatsApp assistant uses, but runs no qualification state machine and extracts no lead fields.
Its only decision is `handoff`: once a visitor is ready to talk about their own project, the
frontend surfaces a "Continue on WhatsApp" action, where the existing, unmodified WhatsApp
qualification flow takes over as it always has.

Deliberately isolated from the WhatsApp code paths: own router, own DB tables (WidgetSession /
WidgetMessage, see db/models.py), own Gemini call (call_gemini_widget), no imports from
webhook.py, message_handler.py, conversation_engine.py, or states/. A bug here cannot reach
the live WhatsApp number.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import company_knowledge
from company_knowledge import PRICING_CATALOGUE_URL
from db.db import get_db
from db.models import WidgetSession, WidgetMessage
from integrations.gemini_client import call_gemini_widget

router = APIRouter()
logger = logging.getLogger("leadpilot.widget")

# Bounds on what a browser can send: this endpoint has no auth (it's a public FAQ widget), so
# these exist to cap prompt size and Gemini cost per request, not because a real visitor would
# ever hit them.
_MAX_MESSAGE_CHARS = 1500
_MAX_HISTORY_TURNS = 12

_FALLBACK_REPLY = (
    "Sorry, I'm having trouble responding right now. You can reach Hoshang directly on "
    "WhatsApp instead, he'll pick it up from here."
)

_SYSTEM_INSTRUCTION_TEMPLATE = """You are the FAQ assistant on Hoshang Sheth's website, answering questions from a visitor
browsing the site. You are NOT the lead-qualification assistant, that is a separate system on
WhatsApp; your only job here is to answer honestly using the reference info below, in a short,
warm, conversational way (a few sentences, not an essay), and to recognise the moment a visitor
is ready to move from browsing to discussing their own project.

{knowledge}

YOUR ROLE HERE, SPECIFICALLY:
- Answer questions about services, pricing, process, timelines, past work, and scope using only
  the reference info above. Never invent a number, capability, or claim that is not in it.
- You do not collect their name, budget, timeline, or contact details here, that only happens
  on WhatsApp if they choose to continue there. Do not ask qualifying questions.
- Set handoff to true once the visitor is ready to talk about their own project specifically:
  they ask to get started, ask for a quote or timeline for their own business, ask how to move
  forward, ask to talk to Hoshang directly, or ask something that genuinely needs their specific
  business context to answer. Otherwise keep handoff false and keep answering.
- When handoff is true, reply_text should say warmly that you'll connect them with the WhatsApp
  assistant to get their specific details sorted, do not ask further generic questions in that
  same reply.
- If asked something unrelated to this business entirely, gently steer back to what you can
  help with here.
- If asked for a PDF, brochure, catalogue, package info, services catalogue, or a downloadable
  pricing sheet: yes, this exists. Say so plainly and say it's linked right below your reply,
  never that there is no PDF or download available. Set wants_catalogue to true on this turn
  so the actual link gets attached (the link itself is added by the site, not by you, so never
  write a URL yourself). This does not count as a handoff on its own; keep answering normally
  unless something else in the conversation warrants it.

Reply with JSON: {{"reply_text": "...", "handoff": true|false, "wants_catalogue": true|false}}"""


class WidgetChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=_MAX_MESSAGE_CHARS)
    history: list[dict] = Field(default_factory=list)


class WidgetChatResponse(BaseModel):
    reply: str
    handoff: bool
    catalogue_url: str | None = None


def _build_prompt(message: str, history: list[dict]) -> str:
    capped = history[-_MAX_HISTORY_TURNS:]
    lines = []
    for turn in capped:
        role = "Visitor" if turn.get("role") == "user" else "Assistant"
        text = str(turn.get("text", ""))[:_MAX_MESSAGE_CHARS]
        if text:
            lines.append(f"{role}: {text}")
    lines.append(f"Visitor: {message}")
    return "\n".join(lines)


def _persist(db: Session, session_id: str, user_message: str, reply: str, handoff: bool) -> None:
    """Best-effort only. A DB hiccup here must never take down a reply that has already been
    computed and is about to be sent to the visitor."""
    try:
        session = db.query(WidgetSession).filter_by(session_id=session_id).first()
        if session is None:
            session = WidgetSession(session_id=session_id)
            db.add(session)
            db.flush()
        db.add(WidgetMessage(session_id=session.id, direction="in", text=user_message))
        db.add(WidgetMessage(session_id=session.id, direction="out", text=reply, handoff=handoff))
        db.commit()
    except Exception:
        logger.exception("Failed to persist widget conversation for session %s", session_id)
        db.rollback()


@router.post("/widget/chat", response_model=WidgetChatResponse)
async def widget_chat(payload: WidgetChatRequest, db: Session = Depends(get_db)) -> WidgetChatResponse:
    system_instruction = _SYSTEM_INSTRUCTION_TEMPLATE.format(knowledge=company_knowledge.as_prompt_block())
    prompt = _build_prompt(payload.message, payload.history)

    result = await call_gemini_widget(prompt, system_instruction)

    if result is None:
        logger.warning("Widget Gemini call failed after retries for session %s", payload.session_id)
        reply, handoff, wants_catalogue = _FALLBACK_REPLY, True, False
    else:
        reply, handoff, wants_catalogue = result.reply_text, result.handoff, result.wants_catalogue

    catalogue_url = PRICING_CATALOGUE_URL if wants_catalogue else None

    _persist(db, payload.session_id, payload.message, reply, handoff)

    return WidgetChatResponse(reply=reply, handoff=handoff, catalogue_url=catalogue_url)
