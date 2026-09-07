"""Tests for process_payload's per-message isolation and failure alerting.

2026-09-07: a real DB connection blip (stale pooled connection, see db.py's pool_pre_ping fix)
raised inside handle_message and was swallowed by a single try/except around the whole
payload — the lead got no reply, Hoshang got no alert, and any other message in the same
payload would have been silently dropped too. These tests pin the fix: each message is
isolated, and a failure always triggers an alert carrying the real wa_number.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import message_handler  # noqa: E402


def _payload_with_messages(*messages):
    return {"entry": [{"changes": [{"value": {"messages": list(messages)}}]}]}


class TestProcessPayloadIsolation:
    def test_one_failing_message_does_not_block_the_next(self):
        payload = _payload_with_messages(
            {"id": "wamid.1", "from": "919000000001", "type": "text", "text": {"body": "hi"}},
            {"id": "wamid.2", "from": "919000000002", "type": "text", "text": {"body": "hi"}},
        )
        calls = []

        def fake_handle_message(msg):
            calls.append(msg["from"])
            if msg["from"] == "919000000001":
                raise RuntimeError("simulated DB timeout")

        with patch.object(message_handler, "handle_message", side_effect=fake_handle_message), \
             patch.object(message_handler, "send_processing_failure_email") as mock_alert:
            message_handler.process_payload(payload)

        assert calls == ["919000000001", "919000000002"], "second message must still be attempted"
        mock_alert.assert_called_once()

    def test_failure_alert_carries_the_real_wa_number(self):
        payload = _payload_with_messages(
            {"id": "wamid.1", "from": "919004001598", "type": "text", "text": {"body": "hi"}},
        )

        with patch.object(message_handler, "handle_message", side_effect=RuntimeError("could not send data to server")), \
             patch.object(message_handler, "send_processing_failure_email") as mock_alert:
            message_handler.process_payload(payload)

        mock_alert.assert_called_once()
        args, _ = mock_alert.call_args
        assert args[0] == "919004001598"
        assert "could not send data to server" in args[1]

    def test_no_alert_when_nothing_fails(self):
        payload = _payload_with_messages(
            {"id": "wamid.1", "from": "919000000003", "type": "text", "text": {"body": "hi"}},
        )

        with patch.object(message_handler, "handle_message") as mock_handle, \
             patch.object(message_handler, "send_processing_failure_email") as mock_alert:
            message_handler.process_payload(payload)

        mock_handle.assert_called_once()
        mock_alert.assert_not_called()
