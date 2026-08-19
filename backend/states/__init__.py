"""One module per conversation state. Each module declares the state's NAME, prompt
INSTRUCTIONS and FEW_SHOT example, and REQUIRED_FIELDS — the deterministic contract
validation/ai_output_rules.py checks Gemini's output against. Transition order is the fixed
STATE_ORDER in validation/ai_output_rules.py, not a per-module allow-list."""
