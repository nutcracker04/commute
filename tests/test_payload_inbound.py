"""Inbound payload + webhook body parsing + MSG91 response checks (no Workers runtime)."""

from __future__ import annotations

import json

import pytest

from payload import (
    format_coupon_whatsapp_message,
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


def test_parse_webhook_nested_data_wrapper():
    inner = {"customerNumber": "919876543210", "text": "hi", "direction": "0"}
    wrapped = {"event": "inbound", "data": inner}
    d = parse_webhook_post_dict(
        "application/json", json.dumps(wrapped).encode()
    )
    assert d["customerNumber"] == "919876543210"
    assert d["text"] == "hi"


def test_inbound_messages_as_native_list():
    jobs = iter_inbound_text_messages(
        {
            "direction": "0",
            "customerNumber": "9198111222333",
            "messages": [
                {
                    "type": "text",
                    "id": "mid-1",
                    "text": {"body": "Hello #RefID:7"},
                }
            ],
        }
    )
    assert len(jobs) == 1
    assert jobs[0]["wa_message_id"] == "mid-1"
    assert "RefID:7" in jobs[0]["text"]


def test_phone_digits_only_from_customer_number():
    jobs = iter_inbound_text_messages(
        {
            "direction": "0",
            "customerNumber": "+91 98765 43210",
            "text": "ping",
        }
    )
    assert jobs[0]["from_phone"] == "919876543210"


def test_messages_missing_type_but_has_text_body():
    jobs = iter_inbound_text_messages(
        {
            "direction": "0",
            "customerNumber": "15550001111",
            "messages": json.dumps(
                [{"id": "x1", "text": {"body": "Hi #RefID:3"}}]
            ),
        }
    )
    assert len(jobs) == 1
    assert jobs[0]["text"] == "Hi #RefID:3"


def test_format_coupon_template_with_extra_braces():
    tpl = "Code: {code} (save {percent}%)"  # would break str.format
    out = format_coupon_whatsapp_message(tpl, "ABC", "A B C")
    assert out == "Code: ABC (save {percent}%)"


def test_msg91_numeric_error_status_in_body_raises():
    body = json.dumps({"status": 400, "message": "bad request"})
    with pytest.raises(RuntimeError):
        raise_if_msg91_session_send_failed(True, 200, body)
