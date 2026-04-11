"""Inbound payload normalization (MSG91 / Meta-style)."""

from __future__ import annotations

import json

from payload import iter_inbound_text_messages


def test_non_text_content_type_with_messages_array_still_inbound():
    """Regression: do not drop inbound when contentType != text but text is in messages."""
    messages = [
        {
            "type": "text",
            "from": "15550001111",
            "id": "wamid.abc",
            "text": {"body": "Hey #RefID:42"},
        }
    ]
    payload = {
        "direction": "0",
        "contentType": "session",
        "customerNumber": "",
        "messages": json.dumps(messages),
    }
    jobs = iter_inbound_text_messages(payload)
    assert len(jobs) == 1
    assert jobs[0]["from_phone"] == "15550001111"
    assert "RefID:42" in jobs[0]["text"]
    assert jobs[0]["wa_message_id"] == "wamid.abc"
