"""
Parse WhatsApp inbound webhook JSON (text messages).

Supports common BSP / aggregator shapes: flat customer fields, optional stringified
`messages` arrays (including Cloud-API-like entries with from, id, text.body).

Also supports flat event envelopes:
  event_type, field, contacts (wa_id + profile.name), messages[], statuses, metadata, api_key.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


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


def _messages_list(messages_val: Any) -> list[Any]:
    """Normalize messages field to a list (already parsed JSON or stringified JSON array)."""
    if isinstance(messages_val, list):
        return messages_val
    parsed = _parse_json_if_string(messages_val)
    return parsed if isinstance(parsed, list) else []


def _text_message_dict(m: dict[str, Any]) -> dict[str, Any] | None:
    """One inbound text message → {from_phone, wa_message_id, text, timestamp} or None."""
    if str(m.get("type") or "").lower() != "text":
        return None
    tb = m.get("text")
    body: str | None = None
    if isinstance(tb, dict):
        b = tb.get("body")
        if isinstance(b, str):
            body = b.strip() or None
    if not body:
        return None
    wf = m.get("from")
    if not wf:
        return None
    from_phone = str(wf).strip().lstrip("+")
    mid = m.get("id")
    mid_s = str(mid) if mid else ""
    ts_raw = m.get("timestamp")
    ts = 0
    if ts_raw is not None:
        try:
            ts = int(str(ts_raw))
        except ValueError:
            ts = 0
    return {
        "from_phone": from_phone,
        "wa_message_id": mid_s,
        "text": body,
        "timestamp": ts,
    }


def _expand_text_messages_from_array(messages_val: Any) -> list[dict[str, Any]]:
    """All type=text entries in messages[] (new flat webhook + Cloud-API-like arrays)."""
    out: list[dict[str, Any]] = []
    for m in _messages_list(messages_val):
        if not isinstance(m, dict):
            continue
        item = _text_message_dict(m)
        if item:
            out.append(item)
    return out


def _from_messages_array(messages_val: Any) -> tuple[str | None, str | None, int]:
    """Returns (message_id, text_body, timestamp) from the first text message only."""
    expanded = _expand_text_messages_from_array(messages_val)
    if not expanded:
        return None, None, 0
    m0 = expanded[0]
    mid = m0.get("wa_message_id") or None
    return mid, m0.get("text"), int(m0.get("timestamp") or 0)


def _name_from_contacts_for_phone(
    payload: dict[str, Any], from_phone: str
) -> str | None:
    """Match top-level contacts[].wa_id to profile.name (flat BSP webhook shape)."""
    raw = payload.get("contacts")
    if not isinstance(raw, list):
        return None
    for c in raw:
        if not isinstance(c, dict):
            continue
        wid = str(c.get("wa_id") or "").strip().lstrip("+")
        if wid != from_phone:
            continue
        profile = c.get("profile")
        if isinstance(profile, dict):
            n = profile.get("name")
            if isinstance(n, str) and n.strip():
                return n.strip()
    return None


def _name_from_payload(
    payload: dict[str, Any], *, from_phone: str | None = None
) -> str | None:
    """Extract sender display name from common webhook shapes.

    Checks top-level name fields first, top-level contacts (by wa_id when from_phone
    is set), then contacts.profile nested inside the first messages entry (legacy).
    """
    for key in ("customerName", "name", "senderName", "sender_name"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    if from_phone:
        hit = _name_from_contacts_for_phone(payload, from_phone)
        if hit:
            return hit

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


def _skip_non_message_event(payload: dict[str, Any]) -> bool:
    et = payload.get("event_type")
    if et is None or et == "":
        return False
    return str(et).strip().lower() != "message"


def _is_status_delivery_only(payload: dict[str, Any]) -> bool:
    """True when there are delivery/status updates but no inbound messages."""
    if not _messages_list(payload.get("messages")):
        st = payload.get("statuses")
        if st is None:
            return False
        if isinstance(st, list):
            return len(st) > 0
        if isinstance(st, dict):
            return bool(st)
        return True
    return False


def _finalize_wa_message_id(
    payload: dict[str, Any],
    *,
    from_phone: str,
    text_body: str,
    msg_id: str,
) -> str:
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
    return wa_message_id


def iter_inbound_text_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Each item: { wa_message_id, from_phone, text, timestamp, name }.
    Skips outbound delivery webhooks (direction 1), non-text inbound, status-only
    payloads, and envelopes whose event_type is not the string message when present.
    """
    out: list[dict[str, Any]] = []

    direction = payload.get("direction")
    if direction is not None and str(direction) == "1":
        return out

    if _skip_non_message_event(payload):
        return out

    if _is_status_delivery_only(payload):
        return out

    expanded = _expand_text_messages_from_array(payload.get("messages"))
    if expanded:
        for item in expanded:
            fp = str(item["from_phone"])
            tb = str(item["text"])
            ts = int(item.get("timestamp") or 0)
            wa_message_id = _finalize_wa_message_id(
                payload,
                from_phone=fp,
                text_body=tb,
                msg_id=str(item.get("wa_message_id") or ""),
            )
            sender_name = _name_from_payload(payload, from_phone=fp)
            out.append(
                {
                    "wa_message_id": wa_message_id,
                    "from_phone": fp,
                    "text": tb,
                    "timestamp": ts,
                    "name": sender_name,
                }
            )
        return out

    from_phone = str(payload.get("customerNumber") or "").strip().lstrip("+")

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
        parsed_m = _messages_list(payload.get("messages"))
        if parsed_m and isinstance(parsed_m[0], dict):
            wf = parsed_m[0].get("from")
            if wf:
                from_phone = str(wf).strip().lstrip("+")

    if not from_phone:
        return out

    if not text_body:
        return out

    if content_type and content_type != "text":
        if not payload.get("text"):
            return out

    wa_message_id = _finalize_wa_message_id(
        payload,
        from_phone=from_phone,
        text_body=text_body,
        msg_id=msg_id or "",
    )

    sender_name = _name_from_payload(payload, from_phone=from_phone)

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


def iter_webhook_inbound_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize inbound webhook POST JSON into queue jobs (single entrypoint for the Worker)."""
    return list(iter_inbound_text_messages(payload))
