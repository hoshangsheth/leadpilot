# Uses the `google-genai` SDK (google-generativeai is deprecated/EOL as of this build).
import config
from schemas import ConversationTurnResult


async def call_gemini(prompt: str, schema: dict) -> ConversationTurnResult:
    if config.MOCK_LLM:
        return ConversationTurnResult(
            reply_text="mock reply",
            extracted_fields={},
            next_state="greeting",
            confidence_flag="high",
        )
    # real call added in Stage 2, via google.genai.Client(api_key=config.GEMINI_API_KEY)
    raise NotImplementedError("Real Gemini call not yet wired — Stage 2")
