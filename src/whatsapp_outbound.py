"""Env-driven WhatsApp outbound HTTP request (single flat JSON body shape)."""

from __future__ import annotations

from typing import Any


def _str_env(env: Any, name: str, default: str = "") -> str:
    raw = getattr(env, name, None)
    return default if raw is None else str(raw)


def build_whatsapp_outbound_request(
    env: Any, *, to_phone: str, text: str
) -> tuple[str, dict[str, str], dict[str, Any]] | None:
    """
    If WHATSAPP_OUTBOUND_URL is unset, returns None (send is skipped).

    If the URL is set, requires WHATSAPP_BUSINESS_PHONE, WHATSAPP_OUTBOUND_AUTH_HEADER,
    WHATSAPP_OUTBOUND_AUTH_SECRET, and WHATSAPP_OUTBOUND_BODY_{FROM,TO,TEXT}_FIELD.
    Raises RuntimeError when any required piece is missing.
    """
    url = _str_env(env, "WHATSAPP_OUTBOUND_URL", "").strip()
    if not url:
        return None

    business = _str_env(env, "WHATSAPP_BUSINESS_PHONE", "").strip().lstrip("+")
    auth_header = _str_env(env, "WHATSAPP_OUTBOUND_AUTH_HEADER", "").strip()
    auth_secret = _str_env(env, "WHATSAPP_OUTBOUND_AUTH_SECRET", "").strip()
    from_field = _str_env(env, "WHATSAPP_OUTBOUND_BODY_FROM_FIELD", "").strip()
    to_field = _str_env(env, "WHATSAPP_OUTBOUND_BODY_TO_FIELD", "").strip()
    text_field = _str_env(env, "WHATSAPP_OUTBOUND_BODY_TEXT_FIELD", "").strip()

    missing: list[str] = []
    if not business:
        missing.append("WHATSAPP_BUSINESS_PHONE")
    if not auth_header:
        missing.append("WHATSAPP_OUTBOUND_AUTH_HEADER")
    if not auth_secret:
        missing.append("WHATSAPP_OUTBOUND_AUTH_SECRET")
    if not from_field:
        missing.append("WHATSAPP_OUTBOUND_BODY_FROM_FIELD")
    if not to_field:
        missing.append("WHATSAPP_OUTBOUND_BODY_TO_FIELD")
    if not text_field:
        missing.append("WHATSAPP_OUTBOUND_BODY_TEXT_FIELD")
    if missing:
        raise RuntimeError(
            "WhatsApp outbound misconfigured: WHATSAPP_OUTBOUND_URL is set but required "
            f"bindings are missing or empty: {', '.join(missing)}"
        )

    recipient = to_phone.strip().lstrip("+")
    body: dict[str, Any] = {
        from_field: business,
        to_field: recipient,
        text_field: text,
    }
    ct_field = _str_env(env, "WHATSAPP_OUTBOUND_BODY_CONTENT_TYPE_FIELD", "").strip()
    if ct_field:
        body[ct_field] = "text"

    headers = {
        auth_header: auth_secret,
        "Content-Type": "application/json",
    }
    return url, headers, body
