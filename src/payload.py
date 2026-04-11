"""
Parse WhatsApp inbound webhook JSON (text messages).

Typical payloads include customerNumber, contentType, text, content (stringified JSON),
messages (stringified JSON array).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import parse_qs


def _strip_utf8_bom(raw: bytes) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:]
    return raw


def _coalesce_provider_payload(d: dict[str, Any]) -> dict[str, Any]:
    """Use inner object when the provider wraps the MSG91 body (data/payload/body)."""
    for key in ("data", "payload", "body"):
        inner = d.get(key)
        if isinstance(inner, dict) and (
            inner.get("customerNumber") is not None
            or inner.get("messages") is not None
            or inner.get("text") is not None
            or inner.get("content") is not None
            or inner.get("direction") is not None
        ):
            return inner
        if isinstance(inner, str) and inner.strip():
            try:
                parsed = json.loads(inner.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return _coalesce_provider_payload(parsed)
    return d


def parse_webhook_post_dict(content_type: str, raw: bytes) -> dict[str, Any]:
    """JSON object from webhook POST: raw JSON or form-encoded ``payload``/``body``/etc."""
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
                        return _coalesce_provider_payload(parsed)
        raise ValueError("form body has no JSON object field (payload/body/data/json)")

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
    return _coalesce_provider_payload(parsed)


def _parse_json_if_string(val: Any) -> Any:
    if val is None or val == "":
        return None
    if not isinstance(val, str):
        return val
    s = val.strip()
    if not s or (s[0] not in "[{"):
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _text_from_content_field(content_val: Any) -> str | None:
    parsed = _parse_json_if_string(content_val)
    if not isinstance(parsed, dict):
        return None
    if "text" in parsed:
        t = parsed["text"]
        if isinstance(t, str):
            return t.strip() or None
        if isinstance(t, dict):
            b = t.get("body")
            if isinstance(b, str) and b.strip():
                return b.strip()
    return None


def _normalize_wa_phone(raw: str) -> str:
    """Digits only, no + or spaces (MSG91 / wa.me expect country code + national)."""
    return "".join(ch for ch in raw if ch.isdigit())


def _from_messages_array(messages_val: Any) -> tuple[str | None, str | None, int]:
    """Returns (message_id, text_body, timestamp)."""
    parsed: Any = messages_val
    if not isinstance(parsed, list):
        parsed = _parse_json_if_string(messages_val)
    if not isinstance(parsed, list) or not parsed:
        return None, None, 0
    m0 = parsed[0]
    if not isinstance(m0, dict):
        return None, None, 0
    tb = m0.get("text")
    body: str | None = None
    if isinstance(tb, dict):
        b = tb.get("body")
        if isinstance(b, str):
            body = b.strip() or None
    elif isinstance(tb, str) and tb.strip():
        body = tb.strip()
    msg_type = str(m0.get("type") or "").lower()
    if msg_type and msg_type != "text" and not body:
        return None, None, 0
    mid = m0.get("id")
    ts_raw = m0.get("timestamp")
    ts = 0
    if ts_raw is not None:
        try:
            ts = int(str(ts_raw))
        except ValueError:
            ts = 0
    mid_s = str(mid) if mid else None
    return mid_s, body, ts


def _name_from_payload(payload: dict[str, Any]) -> str | None:
    """Extract sender display name from MSG91 webhook payload.

    Checks top-level name/senderName fields first, then falls back to
    the contacts profile inside the messages array (Meta Cloud API format).
    """
    for key in ("customerName", "name", "senderName", "sender_name"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    parsed_m = payload.get("messages")
    if not isinstance(parsed_m, list):
        parsed_m = _parse_json_if_string(payload.get("messages"))
    if isinstance(parsed_m, list) and parsed_m and isinstance(parsed_m[0], dict):
        contacts = parsed_m[0].get("contacts")
        if isinstance(contacts, list) and contacts and isinstance(contacts[0], dict):
            profile = contacts[0].get("profile")
            if isinstance(profile, dict):
                n = profile.get("name")
                if isinstance(n, str) and n.strip():
                    return n.strip()

    return None


def iter_inbound_text_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Each item: { wa_message_id, from_phone, text, timestamp, name }.
    Skips outbound delivery webhooks (direction 1) and non-text inbound.
    """
    out: list[dict[str, Any]] = []

    direction = payload.get("direction")
    if direction is not None and str(direction) == "1":
        return out

    from_phone = _normalize_wa_phone(
        str(payload.get("customerNumber") or "").strip().lstrip("+")
    )

    content_type = str(payload.get("contentType") or "").strip().lower()
    text_plain = payload.get("text")
    text_body: str | None = None
    if isinstance(text_plain, str) and text_plain.strip():
        text_body = text_plain.strip()

    if not text_body:
        text_body = _text_from_content_field(payload.get("content"))

    msg_id, msg_text, ts = _from_messages_array(payload.get("messages"))
    if msg_text:
        text_body = text_body or msg_text

    if not from_phone:
        parsed_m = payload.get("messages")
        if not isinstance(parsed_m, list):
            parsed_m = _parse_json_if_string(payload.get("messages"))
        if isinstance(parsed_m, list) and parsed_m and isinstance(parsed_m[0], dict):
            wf = parsed_m[0].get("from")
            if wf:
                from_phone = _normalize_wa_phone(str(wf).strip().lstrip("+"))

    if not from_phone:
        return out

    if not text_body:
        return out

    # Do not drop inbound when contentType is e.g. "session" but text came from
    # the stringified ``messages`` array (common for Meta-style payloads).
    if content_type and content_type != "text":
        has_top_text = isinstance(payload.get("text"), str) and str(
            payload.get("text") or ""
        ).strip()
        if not has_top_text and not msg_text:
            return out

    wa_message_id = msg_id or ""
    if not wa_message_id:
        uuid_val = str(payload.get("uuid") or "").strip()
        if uuid_val:
            wa_message_id = uuid_val.split("_", 1)[0] if "_" in uuid_val else uuid_val
    if not wa_message_id:
        rid = str(payload.get("requestId") or "").strip()
        if rid:
            wa_message_id = rid
    if not wa_message_id:
        raw = f"{from_phone}|{payload.get('ts', '')}|{text_body}"
        wa_message_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

    sender_name = _name_from_payload(payload)

    out.append(
        {
            "wa_message_id": wa_message_id,
            "from_phone": from_phone,
            "text": text_body,
            "timestamp": ts,
            "name": sender_name,
        }
    )
    return out


def format_coupon_whatsapp_message(tpl: str, code: str, spaced: str) -> str:
    """Fill template without str.format (extra `{` in user templates must not crash)."""
    return (tpl or "").replace("{code_spaced}", spaced).replace("{code}", code)


def iter_webhook_inbound_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize inbound webhook POST JSON into queue jobs (single entrypoint for the Worker)."""
    return list(iter_inbound_text_messages(payload))


def raise_if_msg91_session_send_failed(
    http_ok: bool, status: int, body: str
) -> None:
    """Raise when MSG91 session send failed (HTTP or JSON error in 200 body)."""
    detail = (body or "").strip()
    snippet = detail[:500] if detail else ""

    if not http_ok:
        raise RuntimeError(
            f"MSG91 session message failed: HTTP {int(status)} {snippet}"
        )

    if not detail:
        return

    try:
        parsed: Any = json.loads(detail)
    except json.JSONDecodeError:
        return

    if not isinstance(parsed, dict):
        return

    if str(parsed.get("type") or "").lower() == "error":
        raise RuntimeError(f"MSG91 session message failed: {snippet}")

    if parsed.get("success") is False:
        raise RuntimeError(f"MSG91 session message failed: {snippet}")

    st = parsed.get("status")
    if isinstance(st, str) and st.lower() in ("failed", "error", "fail"):
        raise RuntimeError(f"MSG91 session message failed: {snippet}")
    if isinstance(st, (int, float)) and int(st) >= 400:
        raise RuntimeError(f"MSG91 session message failed: {snippet}")

    code = parsed.get("code")
    if isinstance(code, (int, float)) and int(code) != 0 and int(code) != 200:
        raise RuntimeError(f"MSG91 session message failed: {snippet}")

    err = parsed.get("error")
    if err not in (None, False, "", {}):
        raise RuntimeError(f"MSG91 session message failed: {snippet}")
