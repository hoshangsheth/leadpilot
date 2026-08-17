from pydantic import BaseModel
from typing import Literal


class ConversationTurnResult(BaseModel):
    reply_text: str
    extracted_fields: dict[str, str]
    next_state: str  # proposed — validated against the deterministic transition table before trusting it
    confidence_flag: Literal["high", "low"]
