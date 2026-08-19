"""Terminal state for the conversational funnel — no further Gemini-driven questions.
Scoring is fully rule-based (scoring.py), not LLM-judged, per the blueprint's
deterministic-first ladder (explainability — "why did this lead score 72?" must be answerable).
"""

NAME = "qualification_decision"

INSTRUCTIONS = """You are in the Qualification Decision state. All required information has
already been collected. Do not ask anything further. Simply close warmly and let them know
next steps: Hoshang will follow up, and offer they can also grab a slot on his calendar if
they'd like. Do not extract new fields here."""

FEW_SHOT = """
Input: "(final message already handled by prior state)"
Output: {"reply_text": "Thanks so much, this sounds like exactly the kind of thing Hoshang builds. I've passed everything along to him, and he'll follow up with you directly.", "extracted_fields": {}, "next_state": "qualification_decision", "confidence_flag": "high"}
"""

REQUIRED_FIELDS: list[str] = []