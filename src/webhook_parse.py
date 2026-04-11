"""
Parse WhatsApp webhook POST bodies: raw JSON, or form-encoded wrappers (payload=…).
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs


def _strip_utf8_bom(raw: bytes) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:]
    return raw


def parse_webhook_post_dict(content_type: str, raw: bytes) -> dict[str, Any]:
    """Return a JSON object from the webhook body.

    Supports application/json (default) and application/x-www-form-urlencoded
    when providers nest JSON in a field (e.g. ``payload``, ``body``, ``data``).
    """
    ct = (content_type or "").split(";")[0].strip().lower()
    blob = _strip_utf8_bom(raw)

    if ct == "application/x-www-form-urlencoded":
        text = blob.decode("utf-8", errors="replace")
        qs = parse_qs(text, keep_blank_values=True)
        for key in ("payload", "body", "data", "json", "message"):
            vals = qs.get(key)
            if vals and vals[0]:
                inner = vals[0].strip()
                if inner:
                    try:
                        parsed = json.loads(inner)
                    except json.JSONDecodeError as e:
                        raise ValueError(f"invalid JSON in form field {key!r}") from e
                    if isinstance(parsed, dict):
                        return parsed
        raise ValueError("form body has no JSON object field (payload/body/data/json)")

    # application/json, empty, or unknown — try UTF-8 JSON
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("body is not valid UTF-8") from e
    text = text.strip()
    if not text:
        raise ValueError("empty body")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError("body is not valid JSON") from e
    if not isinstance(parsed, dict):
        raise ValueError("JSON root must be an object")
    return parsed
