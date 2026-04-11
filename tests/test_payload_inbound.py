"""Inbound payload + webhook body parsing + MSG91 response checks (no Workers runtime)."""

from __future__ import annotations

import json

import pytest

from payload import (
    iter_inbound_text_messages,
    parse_webhook_post_dict,
    raise_if_msg91_session_send_failed,
)


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


def test_parse_webhook_json_body():
    raw = b'{"customerNumber":"9198","text":"hi","direction":"0"}'
    d = parse_webhook_post_dict("application/json", raw)
    assert d["customerNumber"] == "9198"
    assert d["text"] == "hi"


def test_parse_webhook_json_with_utf8_bom():
    raw = b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode()
    d = parse_webhook_post_dict("application/json; charset=utf-8", raw)
    assert d == {"a": 1}


def test_parse_webhook_form_urlencoded_payload_field():
    inner = {"customerNumber": "91x", "text": "hello", "direction": "0"}
    form = "payload=" + json.dumps(inner)
    d = parse_webhook_post_dict("application/x-www-form-urlencoded", form.encode())
    assert d == inner


def test_parse_webhook_form_invalid_json_raises():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_webhook_post_dict(
            "application/x-www-form-urlencoded",
            b"payload=not-json",
        )


def test_msg91_http_not_ok_raises():
    with pytest.raises(RuntimeError, match="HTTP 401"):
        raise_if_msg91_session_send_failed(False, 401, "nope")


def test_msg91_http_ok_empty_body_ok():
    raise_if_msg91_session_send_failed(True, 200, "")


def test_msg91_meta_style_error_type_in_body_raises():
    body = json.dumps({"type": "error", "error": {"message": "bad"}})
    with pytest.raises(RuntimeError, match="MSG91 session message failed"):
        raise_if_msg91_session_send_failed(True, 200, body)


def test_msg91_success_false_raises():
    body = json.dumps({"success": False, "message": "x"})
    with pytest.raises(RuntimeError):
        raise_if_msg91_session_send_failed(True, 200, body)
