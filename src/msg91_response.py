"""
Interpret MSG91 WhatsApp session send HTTP responses.

Some APIs return HTTP 200 with an error object in JSON; treat those as failure
so queue consumers retry instead of acking without a coupon.
"""

from __future__ import annotations

import json
from typing import Any


def raise_if_msg91_session_send_failed(
    http_ok: bool, status: int, body: str
) -> None:
    """Raise RuntimeError when the send did not succeed."""
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

    err_type = str(parsed.get("type") or "").lower()
    if err_type == "error":
        raise RuntimeError(f"MSG91 session message failed: {snippet}")

    if parsed.get("success") is False:
        raise RuntimeError(f"MSG91 session message failed: {snippet}")

    st = parsed.get("status")
    if isinstance(st, str) and st.lower() in ("failed", "error", "fail"):
        raise RuntimeError(f"MSG91 session message failed: {snippet}")

    err = parsed.get("error")
    if err not in (None, False, "", {}):
        raise RuntimeError(f"MSG91 session message failed: {snippet}")
