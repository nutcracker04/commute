"""
Ephemeral QR scan sessions in Workers KV + ordered index (updated via queue consumer).
"""

from __future__ import annotations

import json
import time
from typing import Any

SS_INDEX_KEY = "ss:index"
SS_DATA_PREFIX = "ss:data:"
INDEX_CAP = 600


def _kv_put_options(expiration_ttl: int | None) -> Any:
    if expiration_ttl is None:
        return None
    return {"expirationTtl": int(expiration_ttl)}


async def ss_put_session(
    kv: Any,
    *,
    session_id: str,
    qr_id: int,
    full_text: str,
    scanned_at: int,
    expires_at: int,
    ttl_seconds: int,
) -> None:
    payload = {
        "qr_id": qr_id,
        "full_text": full_text,
        "scanned_at": scanned_at,
        "expires_at": expires_at,
        "claimed_at": None,
    }
    opts = _kv_put_options(max(60, ttl_seconds))
    key = SS_DATA_PREFIX + session_id
    val = json.dumps(payload)
    if opts is not None:
        await kv.put(key, val, opts)
    else:
        await kv.put(key, val)


async def ss_merge_index_batch(kv: Any, adds: list[dict[str, Any]]) -> None:
    """Merge session index entries (serialized consumer). `adds` items: id, scanned_at, expires_at."""
    now = int(time.time())
    raw = await kv.get(SS_INDEX_KEY)
    by_id: dict[str, dict[str, int]] = {}
    if raw:
        try:
            prev = json.loads(str(raw))
            if isinstance(prev, list):
                for e in prev:
                    if isinstance(e, dict) and e.get("id"):
                        iid = str(e["id"])
                        by_id[iid] = {
                            "id": iid,
                            "scanned_at": int(e["scanned_at"]),
                            "expires_at": int(e["expires_at"]),
                        }
        except (json.JSONDecodeError, TypeError, ValueError):
            by_id = {}

    for b in adds:
        if b.get("op") != "add":
            continue
        iid = str(b.get("id") or "")
        if not iid:
            continue
        by_id[iid] = {
            "id": iid,
            "scanned_at": int(b["scanned_at"]),
            "expires_at": int(b["expires_at"]),
        }

    merged = [e for e in by_id.values() if e["expires_at"] > now]
    merged.sort(key=lambda x: -x["scanned_at"])
    merged = merged[:INDEX_CAP]
    await kv.put(SS_INDEX_KEY, json.dumps(merged))


async def ss_load_lcs_candidates(
    kv: Any,
    *,
    now_ts: int,
    max_candidates: int,
) -> list[dict[str, Any]]:
    raw = await kv.get(SS_INDEX_KEY)
    if not raw:
        return []
    try:
        entries = json.loads(str(raw))
    except json.JSONDecodeError:
        return []
    if not isinstance(entries, list):
        return []

    out: list[dict[str, Any]] = []
    for e in entries:
        if len(out) >= max_candidates:
            break
        if not isinstance(e, dict):
            continue
        sid = str(e.get("id") or "")
        if not sid:
            continue
        dr = await kv.get(SS_DATA_PREFIX + sid)
        if not dr:
            continue
        try:
            data = json.loads(str(dr))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("claimed_at") is not None:
            continue
        try:
            exp = int(data["expires_at"])
            if exp <= now_ts:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        try:
            out.append(
                {
                    "session_id": sid,
                    "qr_id": int(data["qr_id"]),
                    "full_prefilled_text": str(data["full_text"]),
                    "scanned_at": int(data["scanned_at"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def ss_claim_session(kv: Any, session_id: str, now_ts: int) -> None:
    key = SS_DATA_PREFIX + session_id
    raw = await kv.get(key)
    if not raw:
        return
    try:
        data = json.loads(str(raw))
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return
    data["claimed_at"] = now_ts
    try:
        exp = int(data["expires_at"])
    except (KeyError, TypeError, ValueError):
        return
    ttl = max(60, exp - now_ts)
    opts = _kv_put_options(ttl)
    val = json.dumps(data)
    if opts is not None:
        await kv.put(key, val, opts)
    else:
        await kv.put(key, val)


# Fallback-only inbound dedupe (no lead row). Matched path uses UNIQUE(leads.whatsapp_message_id).
WI_NOMATCH_PREFIX = "wi:nm:"


async def inbound_fallback_claim(
    kv: Any,
    wa_message_id: str,
    *,
    ttl_seconds: int = 30 * 24 * 3600,
) -> bool:
    """Return True if this worker should send the fallback reply; False if already handled."""
    key = WI_NOMATCH_PREFIX + wa_message_id
    existing = await kv.get(key)
    if existing is not None:
        return False
    opts = _kv_put_options(max(60, ttl_seconds))
    if opts is not None:
        await kv.put(key, "1", opts)
    else:
        await kv.put(key, "1")
    return True


async def inbound_fallback_release(kv: Any, wa_message_id: str) -> None:
    """Clear claim so a failed send can be retried by the queue."""
    await kv.delete(WI_NOMATCH_PREFIX + wa_message_id)
