"""Tests for the website FAQ widget's catalogue-download wiring.

2026-09-15: the WhatsApp funnel already handles "can I get a PDF of your pricing?" by having
the model set a one-shot signal and having code attach the real file. The website widget had
no such thing at all, since it was built before the pricing PDF existed. This pins the same
pattern here: the model only signals intent (wants_catalogue), the actual URL always comes
from company_knowledge.PRICING_CATALOGUE_URL, never from the model's own text.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from company_knowledge import PRICING_CATALOGUE_URL  # noqa: E402
from schemas import WidgetTurnResult  # noqa: E402
from widget import widget_chat, WidgetChatRequest  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class TestCatalogueDownload:
    def test_wants_catalogue_attaches_the_real_url(self):
        payload = WidgetChatRequest(session_id="s1", message="do you have a pricing PDF?", history=[])
        mock_result = WidgetTurnResult(
            reply_text="Yes, it's linked right below.",
            handoff=False,
            wants_catalogue=True,
        )
        with patch("widget.call_gemini_widget", return_value=mock_result):
            response = _run(widget_chat(payload, db=MagicMock()))

        assert response.catalogue_url == PRICING_CATALOGUE_URL

    def test_normal_reply_has_no_catalogue_url(self):
        payload = WidgetChatRequest(session_id="s2", message="what's your process like?", history=[])
        mock_result = WidgetTurnResult(
            reply_text="Discovery call, proposal, then a 5-12 week build.",
            handoff=False,
            wants_catalogue=False,
        )
        with patch("widget.call_gemini_widget", return_value=mock_result):
            response = _run(widget_chat(payload, db=MagicMock()))

        assert response.catalogue_url is None

    def test_failed_gemini_call_never_sends_a_catalogue(self):
        payload = WidgetChatRequest(session_id="s3", message="hi", history=[])
        with patch("widget.call_gemini_widget", return_value=None):
            response = _run(widget_chat(payload, db=MagicMock()))

        assert response.catalogue_url is None
