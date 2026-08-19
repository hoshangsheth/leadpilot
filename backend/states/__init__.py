"""One module per conversation state. Each module declares the state's NAME, prompt
INSTRUCTIONS and FEW_SHOT example, REQUIRED_FIELDS, and ALLOWED_NEXT transitions — the
deterministic contract validation/ai_output_rules.py checks Gemini's output against."""
