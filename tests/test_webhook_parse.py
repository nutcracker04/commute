"""Tests for webhook body parsing (no Workers runtime)."""

from __future__ import annotations

import json

import pytest

from webhook_parse import parse_webhook_post_dict


def test_json_body():
    raw = b'{"customerNumber":"9198","text":"hi","direction":"0"}'
    d = parse_webhook_post_dict("application/json", raw)
    assert d["customerNumber"] == "9198"
    assert d["text"] == "hi"


def test_json_with_utf8_bom():
    raw = b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode()
    d = parse_webhook_post_dict("application/json; charset=utf-8", raw)
    assert d == {"a": 1}


def test_form_urlencoded_payload_field():
    inner = {"customerNumber": "91x", "text": "hello", "direction": "0"}
    form = "payload=" + json.dumps(inner)
    d = parse_webhook_post_dict("application/x-www-form-urlencoded", form.encode())
    assert d == inner


def test_form_invalid_json_raises():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_webhook_post_dict(
            "application/x-www-form-urlencoded",
            b"payload=not-json",
        )
