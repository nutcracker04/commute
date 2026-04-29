"""Env-driven WhatsApp outbound HTTP request (flat or templated JSON body)."""

from __future__ import annotations

import json
from typing import Any


def _str_env(env: Any, name: str, default: str = "") -> str:
    raw = getattr(env, name, None)
    return default if raw is None else str(raw)


def _truthy_env(env: Any, name: str) -> bool:
    v = _str_env(env, name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def outbound_authorization_value(env: Any, secret: str, *, header_name: str = "") -> str:
    """Build auth header value. Bearer prefix only for ``Authorization`` (not X-Api-Key, etc.)."""
    s = secret.strip()
    if not s:
        return s
    h = (header_name or "").strip().lower()
    use_bearer = _truthy_env(env, "WHATSAPP_OUTBOUND_BEARER_PREFIX")
    if use_bearer and h == "authorization" and not s.lower().startswith("bearer "):
        return f"Bearer {s}"
    return s


def outbound_response_api_error(body_text: str) -> str | None:
    """If a JSON response body indicates API-level failure, return a short message; else None."""
    if not body_text or not body_text.strip():
        return None
    try:
        data = json.loads(body_text.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("success") is False:
        parts: list[str] = []
        for k in ("message", "error", "detail", "description"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
            elif isinstance(v, dict) and v:
                parts.append(json.dumps(v, ensure_ascii=False)[:240])
        return "; ".join(parts) if parts else json.dumps(data, ensure_ascii=False)[:300]
    err = data.get("error")
    if isinstance(err, str) and err.strip():
        return err.strip()[:300]
    if isinstance(err, dict) and err:
        return json.dumps(err, ensure_ascii=False)[:300]
    errs = data.get("errors")
    if isinstance(errs, list) and errs:
        first = errs[0]
        if isinstance(first, dict):
            m = first.get("message")
            if isinstance(m, str) and m.strip():
                return m.strip()[:300]
    return None


def json_string_embed(s: str) -> str:
    """Encode *s* for inserting between JSON string quotes (contents only, no outer quotes)."""
    return json.dumps(s, ensure_ascii=False)[1:-1]


def _resolve_outbound_url(env: Any) -> str:
    """Full URL, or WHATSAPP_OUTBOUND_API_BASE + WHATSAPP_OUTBOUND_PATH (default send path)."""
    full = _str_env(env, "WHATSAPP_OUTBOUND_URL", "").strip()
    if full:
        return full
    base = _str_env(env, "WHATSAPP_OUTBOUND_API_BASE", "").strip().rstrip("/")
    if not base:
        return ""
    path = _str_env(
        env,
        "WHATSAPP_OUTBOUND_PATH",
        "/message/v1/client/message/send",
    ).strip()
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def resolve_whatsapp_outbound_url(env: Any) -> str:
    """Public alias for URL resolution (used by UniversalProvider)."""
    return _resolve_outbound_url(env)


def build_whatsapp_outbound_request(
    env: Any, *, to_phone: str, text: str
) -> tuple[str, dict[str, str], dict[str, Any] | str] | None:
    """
    If neither WHATSAPP_OUTBOUND_URL nor WHATSAPP_OUTBOUND_API_BASE is set, returns None
    (send is skipped).

    URL resolution: WHATSAPP_OUTBOUND_URL (full URL) wins; otherwise
    WHATSAPP_OUTBOUND_API_BASE + WHATSAPP_OUTBOUND_PATH (default path
    /message/v1/client/message/send).

    If WHATSAPP_OUTBOUND_BODY_TEMPLATE is set, the body is built from that string after
    substituting {to}, {from}, {text}, {text_escaped} (BSP shapes like nested text.body).
    ``{text_escaped}`` is JSON-safe (newlines, quotes, etc.) for embedding inside JSON strings.

    Otherwise (legacy): requires WHATSAPP_BUSINESS_PHONE, WHATSAPP_OUTBOUND_AUTH_HEADER,
    WHATSAPP_OUTBOUND_AUTH_SECRET, and WHATSAPP_OUTBOUND_BODY_{FROM,TO,TEXT}_FIELD.

    Raises RuntimeError when any required piece is missing.
    """
    url = _resolve_outbound_url(env)
    if not url:
        return None

    auth_header = _str_env(env, "WHATSAPP_OUTBOUND_AUTH_HEADER", "").strip()
    auth_secret = _str_env(env, "WHATSAPP_OUTBOUND_AUTH_SECRET", "").strip()
    body_template = _str_env(env, "WHATSAPP_OUTBOUND_BODY_TEMPLATE", "").strip()

    if body_template:
        missing_t: list[str] = []
        if not auth_header:
            missing_t.append("WHATSAPP_OUTBOUND_AUTH_HEADER")
        if not auth_secret:
            missing_t.append("WHATSAPP_OUTBOUND_AUTH_SECRET")
        if missing_t:
            raise RuntimeError(
                "WhatsApp outbound misconfigured: WHATSAPP_OUTBOUND_BODY_TEMPLATE is set but "
                f"required bindings are missing or empty: {', '.join(missing_t)}"
            )
        recipient = to_phone.strip().lstrip("+")
        business = _str_env(env, "WHATSAPP_BUSINESS_PHONE", "").strip().lstrip("+")
        text_inner = json_string_embed(text)
        raw = (
            body_template.replace("{to}", recipient)
            .replace("{from}", business)
            .replace("{text_escaped}", text_inner)
            .replace("{text}", text)
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"WhatsApp outbound: WHATSAPP_OUTBOUND_BODY_TEMPLATE is not valid JSON after "
                f"substitution: {e}"
            ) from e
        body_str = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        headers = {
            auth_header: outbound_authorization_value(env, auth_secret, header_name=auth_header),
            "Content-Type": "application/json",
        }
        return url, headers, body_str

    business = _str_env(env, "WHATSAPP_BUSINESS_PHONE", "").strip().lstrip("+")
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
            "WhatsApp outbound misconfigured: outbound URL is set but required "
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
        auth_header: outbound_authorization_value(env, auth_secret, header_name=auth_header),
        "Content-Type": "application/json",
    }
    return url, headers, body
