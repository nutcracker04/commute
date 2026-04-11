"""MSG91 HTTP response interpretation."""

from __future__ import annotations

import json

import pytest

from msg91_response import raise_if_msg91_session_send_failed


def test_http_not_ok_raises():
    with pytest.raises(RuntimeError, match="HTTP 401"):
        raise_if_msg91_session_send_failed(False, 401, "nope")


def test_http_ok_empty_body_ok():
    raise_if_msg91_session_send_failed(True, 200, "")


def test_meta_style_error_type_in_body_raises():
    body = json.dumps({"type": "error", "error": {"message": "bad"}})
    with pytest.raises(RuntimeError, match="MSG91 session message failed"):
        raise_if_msg91_session_send_failed(True, 200, body)


def test_success_false_raises():
    body = json.dumps({"success": False, "message": "x"})
    with pytest.raises(RuntimeError):
        raise_if_msg91_session_send_failed(True, 200, body)
