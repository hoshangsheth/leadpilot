import logging

logger = logging.getLogger("leadpilot.transitions")


def log_transition(lead_id: int, from_state: str, to_state: str, gemini_call_ms: int | None, outcome: str):
    """One structured line per state transition — lead_id, from_state, to_state,
    gemini_call_ms, outcome. Grep-able by design, no external tracing tool needed for MVP."""
    logger.info(
        "lead_id=%s from_state=%s to_state=%s gemini_ms=%s outcome=%s",
        lead_id, from_state, to_state, gemini_call_ms, outcome,
    )
