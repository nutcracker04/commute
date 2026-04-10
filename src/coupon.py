"""Coupon codes: brand prefix + cryptographically random body (no lead id in code)."""

from __future__ import annotations

import re
import secrets
from typing import Any

# Crockford-like: omit 0, O, 1, I, L for readability.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

_PREFIX_MAX_LEN = 6
_DEFAULT_PREFIX = "CMP"
_DEFAULT_RANDOM_LENGTH = 6


def fetch_coupon_prefix(env: Any) -> str:
    for key in ("COUPON_CODE_PREFIX", "PROMO_CODE_PREFIX", "BRAND_COUPON_PREFIX"):
        raw = getattr(env, key, None)
        if raw is not None and str(raw).strip():
            s = re.sub(r"[^A-Za-z0-9]", "", str(raw).strip()).upper()
            if s:
                return s[:_PREFIX_MAX_LEN]
    return _DEFAULT_PREFIX


def _random_body(length: int) -> str:
    n = max(4, min(12, length))
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def generate_coupon_code(prefix: str, *, random_length: int = _DEFAULT_RANDOM_LENGTH) -> str:
    pfx = re.sub(r"[^A-Za-z0-9]", "", (prefix or "").strip()).upper()[:_PREFIX_MAX_LEN] or _DEFAULT_PREFIX
    return pfx + _random_body(random_length)


def format_coupon_spaced(code: str, group: int = 3) -> str:
    c = (code or "").strip().upper()
    if not c or group < 1:
        return c
    parts: list[str] = []
    for i in range(0, len(c), group):
        parts.append(c[i : i + group])
    return " ".join(parts)
