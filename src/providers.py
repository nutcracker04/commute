"""Universal env-driven WhatsApp BSP adapter.

Instead of one Python class per BSP, this module uses a single UniversalProvider
class that reads dot-path field mappings and body templates from env vars. Any BSP
— Meta, Twilio, Gupshup, WATI, MSG91, Interakt, Kaleyra, AiSensy, or any future
provider — works by setting WA_INBOUND_* / WA_OUTBOUND_* / WA_VERIFY_* vars.

Named presets (WHATSAPP_PROVIDER = meta|twilio|gupshup|wati|360dialog) supply
sensible defaults so operators don't have to look up field paths themselves.
Set WHATSAPP_PROVIDER = custom to configure every field manually.
Unset WHATSAPP_PROVIDER (or "generic") uses the legacy payload.py heuristic for
backward compatibility.

Interface (unchanged from previous iteration, no entry.py changes needed):
  handle_get(request, env) -> (body_str, status) | None
  parse_inbound(body_text, content_type) -> list[job_dict]
  build_outbound(env, *, to_phone, text) -> (url, headers, body) | None
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlparse

from payload import iter_webhook_inbound_jobs
from whatsapp_outbound import build_whatsapp_outbound_request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _str_env(env: Any, name: str, default: str = "") -> str:
    raw = getattr(env, name, None)
    return default if raw is None else str(raw)


def _header_get(headers: Any, name: str) -> str | None:
    try:
        if hasattr(headers, "get"):
            v = headers.get(name)
            return None if v is None else str(v)
    except Exception:
        pass
    try:
        return str(headers[name])
    except Exception:
        return None


def _resolve_dot_path(data: Any, path: str) -> Any:
    """Walk a dot-separated path through nested dicts/lists.

    "payload.sender.name"  → data["payload"]["sender"]["name"]
    "messages.0.text.body" → data["messages"][0]["text"]["body"]
    Returns None if any step fails.
    """
    if not path or data is None:
        return None
    current = data
    for segment in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _coerce_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _env_with_preset(env: Any, name: str, preset: dict[str, str], default: str = "") -> str:
    """Read from env first, fall back to preset defaults."""
    val = _str_env(env, name, "").strip()
    if val:
        return val
    return preset.get(name, default)


# ---------------------------------------------------------------------------
# Base class (interface)
# ---------------------------------------------------------------------------

class WhatsAppProvider:
    name: str = "base"

    def handle_get(self, request: Any, env: Any) -> tuple[str, int] | None:
        return None

    def parse_inbound(self, body_text: str, content_type: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def build_outbound(
        self, env: Any, *, to_phone: str, text: str
    ) -> tuple[str, dict[str, str], dict[str, Any] | str] | None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# GenericFlatProvider — backward-compatible default (payload.py heuristic)
# ---------------------------------------------------------------------------

class GenericFlatProvider(WhatsAppProvider):
    """Legacy fallback: delegates to payload.py heuristics and whatsapp_outbound.py.

    Active when WHATSAPP_PROVIDER is unset or "generic" and no WA_INBOUND_* vars
    are configured.
    """

    name = "generic"

    def parse_inbound(self, body_text: str, content_type: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(payload, dict):
            return []
        return iter_webhook_inbound_jobs(payload)

    def build_outbound(
        self, env: Any, *, to_phone: str, text: str
    ) -> tuple[str, dict[str, str], dict[str, Any]] | None:
        return build_whatsapp_outbound_request(env, to_phone=to_phone, text=text)


# ---------------------------------------------------------------------------
# Presets — default WA_* values for named providers
# ---------------------------------------------------------------------------

_PRESET_META: dict[str, str] = {
    "WA_VERIFY_MODE": "hmac-sha256",
    "WA_VERIFY_HEADER": "X-Hub-Signature-256",
    "WA_VERIFY_SECRET_VAR": "WHATSAPP_APP_SECRET",
    "WA_GET_CHALLENGE": "meta",
    "WA_INBOUND_UNWRAP": "meta",
    "WA_INBOUND_FROM_PATH": "from",
    "WA_INBOUND_TEXT_PATH": "text.body",
    "WA_INBOUND_ID_PATH": "id",
    "WA_INBOUND_TS_PATH": "timestamp",
    "WA_INBOUND_TS_UNIT": "s",
    "WA_INBOUND_NAME_PATH": "$contacts",
    "WA_INBOUND_TYPE_PATH": "type",
    "WA_INBOUND_TYPE_VALUE": "text",
    "WA_OUTBOUND_CONTENT_TYPE": "application/json",
    "WA_OUTBOUND_BODY_TEMPLATE": '{"messaging_product":"whatsapp","recipient_type":"individual","to":"{to}","type":"text","text":{"body":"{text_escaped}"}}',
}

_PRESET_360DIALOG: dict[str, str] = {
    **_PRESET_META,
    "WA_VERIFY_MODE": "none",
    "WA_GET_CHALLENGE": "meta",
}

_PRESET_TWILIO: dict[str, str] = {
    "WA_VERIFY_MODE": "hmac-sha1-twilio",
    "WA_VERIFY_HEADER": "X-Twilio-Signature",
    "WA_VERIFY_SECRET_VAR": "WHATSAPP_AUTH_TOKEN",
    "WA_GET_CHALLENGE": "none",
    "WA_INBOUND_UNWRAP": "form",
    "WA_INBOUND_FROM_PATH": "From",
    "WA_INBOUND_TEXT_PATH": "Body",
    "WA_INBOUND_ID_PATH": "MessageSid",
    "WA_INBOUND_NAME_PATH": "ProfileName",
    "WA_INBOUND_TS_UNIT": "s",
    "WA_INBOUND_FROM_STRIP": "whatsapp:+",
    "WA_OUTBOUND_CONTENT_TYPE": "application/x-www-form-urlencoded",
    "WA_OUTBOUND_BODY_TEMPLATE": "From=whatsapp%3A%2B{from}&To=whatsapp%3A%2B{to}&Body={text_urlencoded}",
}

_PRESET_GUPSHUP: dict[str, str] = {
    "WA_VERIFY_MODE": "none",
    "WA_GET_CHALLENGE": "none",
    "WA_INBOUND_UNWRAP": "none",
    "WA_INBOUND_FROM_PATH": "payload.source",
    "WA_INBOUND_TEXT_PATH": "payload.payload.text",
    "WA_INBOUND_ID_PATH": "payload.id",
    "WA_INBOUND_NAME_PATH": "payload.sender.name",
    "WA_INBOUND_TS_PATH": "timestamp",
    "WA_INBOUND_TS_UNIT": "ms",
    "WA_INBOUND_SKIP_WHEN": "type!=message",
    "WA_INBOUND_TYPE_PATH": "payload.type",
    "WA_INBOUND_TYPE_VALUE": "text",
    "WA_OUTBOUND_CONTENT_TYPE": "application/x-www-form-urlencoded",
    "WA_OUTBOUND_BODY_TEMPLATE": "channel=whatsapp&source={from}&destination={to}&src.name={app_name}&message={text_json_urlencoded}",
}

_PRESET_WATI: dict[str, str] = {
    "WA_VERIFY_MODE": "none",
    "WA_GET_CHALLENGE": "none",
    "WA_INBOUND_UNWRAP": "none",
    "WA_INBOUND_FROM_PATH": "waId",
    "WA_INBOUND_TEXT_PATH": "text",
    "WA_INBOUND_ID_PATH": "whatsappMessageId",
    "WA_INBOUND_NAME_PATH": "senderName",
    "WA_INBOUND_TS_PATH": "timestamp",
    "WA_INBOUND_TS_UNIT": "s",
    "WA_INBOUND_SKIP_WHEN": "owner=true",
    "WA_INBOUND_TYPE_PATH": "type",
    "WA_INBOUND_TYPE_VALUE": "text",
    "WA_OUTBOUND_CONTENT_TYPE": "application/json",
    "WA_OUTBOUND_URL_TEMPLATE": "{base_url}/api/v1/sendSessionMessage/{to}?messageText={text_urlencoded}",
    "WA_OUTBOUND_BODY_TEMPLATE": "",
}

_PRESETS: dict[str, dict[str, str]] = {
    "meta": _PRESET_META,
    "360dialog": _PRESET_360DIALOG,
    "twilio": _PRESET_TWILIO,
    "gupshup": _PRESET_GUPSHUP,
    "wati": _PRESET_WATI,
    "custom": {},
}


# ---------------------------------------------------------------------------
# UniversalProvider — the single env-driven adapter
# ---------------------------------------------------------------------------

class UniversalProvider(WhatsAppProvider):
    """Env-driven universal BSP adapter.

    Reads WA_INBOUND_* and WA_OUTBOUND_* vars (with preset defaults)
    to handle any WhatsApp BSP without writing Python code.
    """

    name = "universal"

    def __init__(self, preset: dict[str, str]) -> None:
        self._preset = preset

    def _cfg(self, env: Any, name: str, default: str = "") -> str:
        return _env_with_preset(env, name, self._preset, default)

    # --- GET challenge engine (Meta hub.challenge echo; no verify_token check) ---

    def handle_get(self, request: Any, env: Any) -> tuple[str, int] | None:
        mode = self._cfg(env, "WA_GET_CHALLENGE", "none").lower()
        if mode != "meta":
            return None
        try:
            qs = parse_qs(urlparse(str(request.url)).query)
        except Exception:
            return None
        if (qs.get("hub.mode") or [""])[0] != "subscribe":
            return None
        challenge = (qs.get("hub.challenge") or [""])[0]
        if not challenge:
            return None
        return (challenge, 200)

    # --- Inbound parse engine ---

    def _unwrap_meta_envelope(self, payload: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, str]]]:
        """Unwrap Meta Cloud API entry→changes→value→messages, returning (msg_dict, name_map) pairs."""
        if payload.get("object") != "whatsapp_business_account":
            return []
        results: list[tuple[dict[str, Any], dict[str, str]]] = []
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                messages = value.get("messages")
                if not isinstance(messages, list):
                    continue
                name_by_wa_id: dict[str, str] = {}
                for c in value.get("contacts") or []:
                    if isinstance(c, dict):
                        wa_id = _coerce_str(c.get("wa_id"))
                        profile = c.get("profile")
                        if isinstance(profile, dict):
                            n = _coerce_str(profile.get("name"))
                            if wa_id and n:
                                name_by_wa_id[wa_id] = n
                for msg in messages:
                    if isinstance(msg, dict):
                        results.append((msg, name_by_wa_id))
        return results

    def _check_skip(self, data: dict[str, Any], env: Any) -> bool:
        """Return True if this message should be skipped based on WA_INBOUND_SKIP_WHEN."""
        skip_rule = self._cfg(env, "WA_INBOUND_SKIP_WHEN", "")
        if not skip_rule:
            return False
        if "!=" in skip_rule:
            path, expected = skip_rule.split("!=", 1)
            val = _coerce_str(_resolve_dot_path(data, path.strip()))
            return val.lower() != expected.strip().lower()
        if "=" in skip_rule:
            path, expected = skip_rule.split("=", 1)
            val = _coerce_str(_resolve_dot_path(data, path.strip()))
            return val.lower() == expected.strip().lower()
        return False

    def _extract_job(self, data: dict[str, Any], env: Any, name_map: dict[str, str] | None = None) -> dict[str, Any] | None:
        """Extract the 5 normalized fields from a single message dict using WA_INBOUND_*_PATH."""
        if self._check_skip(data, env):
            return None

        type_path = self._cfg(env, "WA_INBOUND_TYPE_PATH", "")
        if type_path:
            type_val = _coerce_str(_resolve_dot_path(data, type_path)).lower()
            expected = self._cfg(env, "WA_INBOUND_TYPE_VALUE", "text").lower()
            if type_val and type_val != expected:
                return None

        from_path = self._cfg(env, "WA_INBOUND_FROM_PATH", "")
        text_path = self._cfg(env, "WA_INBOUND_TEXT_PATH", "")
        if not from_path or not text_path:
            return None

        from_phone = _coerce_str(_resolve_dot_path(data, from_path))
        strip_prefix = self._cfg(env, "WA_INBOUND_FROM_STRIP", "")
        if strip_prefix and from_phone.startswith(strip_prefix):
            from_phone = from_phone[len(strip_prefix):]
        from_phone = from_phone.lstrip("+").strip()
        if not from_phone:
            return None

        text_body = _coerce_str(_resolve_dot_path(data, text_path))
        if not text_body:
            return None

        id_path = self._cfg(env, "WA_INBOUND_ID_PATH", "")
        mid = _coerce_str(_resolve_dot_path(data, id_path)) if id_path else ""
        if not mid:
            raw = f"{from_phone}|{text_body}"
            mid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

        ts = 0
        ts_path = self._cfg(env, "WA_INBOUND_TS_PATH", "")
        if ts_path:
            ts_raw = _resolve_dot_path(data, ts_path)
            if ts_raw is not None:
                try:
                    ts_int = int(str(ts_raw))
                    ts_unit = self._cfg(env, "WA_INBOUND_TS_UNIT", "s").lower()
                    ts = ts_int // 1000 if ts_unit == "ms" else ts_int
                except (ValueError, TypeError):
                    ts = 0

        name: str | None = None
        name_path = self._cfg(env, "WA_INBOUND_NAME_PATH", "")
        if name_path == "$contacts" and name_map:
            name = name_map.get(from_phone)
        elif name_path:
            n = _coerce_str(_resolve_dot_path(data, name_path))
            name = n if n else None

        return {
            "wa_message_id": mid,
            "from_phone": from_phone,
            "text": text_body,
            "timestamp": ts,
            "name": name,
        }

    def parse_inbound(self, body_text: str, content_type: str) -> list[dict[str, Any]]:
        unwrap = self._cfg(self._current_env, "WA_INBOUND_UNWRAP", "none").lower()

        if unwrap == "form":
            data = dict(parse_qsl(body_text, keep_blank_values=True))
            job = self._extract_job(data, self._current_env)
            return [job] if job else []

        if unwrap == "meta":
            try:
                payload = json.loads(body_text)
            except (json.JSONDecodeError, ValueError):
                return []
            if not isinstance(payload, dict):
                return []
            pairs = self._unwrap_meta_envelope(payload)
            if not pairs:
                return []
            out: list[dict[str, Any]] = []
            for msg, name_map in pairs:
                job = self._extract_job(msg, self._current_env, name_map)
                if job:
                    out.append(job)
            return out

        # unwrap == "none" or default: parse as JSON
        try:
            data = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(data, dict):
            return []
        job = self._extract_job(data, self._current_env)
        return [job] if job else []

    # --- Outbound template engine ---

    def build_outbound(
        self, env: Any, *, to_phone: str, text: str
    ) -> tuple[str, dict[str, str], dict[str, Any] | str] | None:
        auth_header = _str_env(env, "WHATSAPP_OUTBOUND_AUTH_HEADER", "").strip()
        auth_secret = _str_env(env, "WHATSAPP_OUTBOUND_AUTH_SECRET", "").strip()
        base_url = _str_env(env, "WHATSAPP_OUTBOUND_URL", "").strip().rstrip("/")
        if not base_url:
            return None

        recipient = to_phone.strip().lstrip("+")
        business = _str_env(env, "WHATSAPP_BUSINESS_PHONE", "").strip().lstrip("+")
        app_name = _str_env(env, "WHATSAPP_GUPSHUP_APP_NAME", "").strip()

        # Prepare replacement values
        replacements = {
            "to": recipient,
            "from": business,
            "text": text,
            "text_escaped": text.replace("\\", "\\\\").replace('"', '\\"'),
            "text_urlencoded": quote(text, safe=""),
            "text_json_urlencoded": quote(json.dumps({"type": "text", "text": text}), safe=""),
            "base_url": base_url,
            "app_name": app_name,
        }

        def _substitute(template: str) -> str:
            result = template
            for key, val in replacements.items():
                result = result.replace("{" + key + "}", val)
            return result

        # URL template: if set, build the final URL from template; otherwise use base_url
        url_template = self._cfg(env, "WA_OUTBOUND_URL_TEMPLATE", "")
        if url_template:
            final_url = _substitute(url_template)
        else:
            final_url = base_url

        # Body template
        body_template = self._cfg(env, "WA_OUTBOUND_BODY_TEMPLATE", "")
        body_str = _substitute(body_template) if body_template else ""

        content_type = self._cfg(env, "WA_OUTBOUND_CONTENT_TYPE", "application/json")
        headers: dict[str, str] = {"Content-Type": content_type}
        if auth_header and auth_secret:
            headers[auth_header] = auth_secret

        return final_url, headers, body_str

    # Stash env ref for use in parse_inbound (avoids changing the interface)
    _current_env: Any = None

    def _with_env(self, env: Any) -> "UniversalProvider":
        """Bind env for a single request cycle. Thread-safe in Workers (single-threaded)."""
        self._current_env = env
        return self


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_generic = GenericFlatProvider()


def get_provider(env: Any) -> WhatsAppProvider:
    """Return the configured WhatsApp provider adapter.

    WHATSAPP_PROVIDER values:
      (unset) / "generic"  — legacy payload.py heuristic (backward compat)
      "meta"               — Meta Cloud API preset
      "360dialog"          — 360dialog preset (same envelope as Meta)
      "twilio"             — Twilio preset (form-encoded)
      "gupshup"            — Gupshup preset (double-nested JSON)
      "wati"               — WATI preset (flat JSON, URL-based outbound)
      "custom"             — no preset; operator sets all WA_* vars manually
    """
    name = _str_env(env, "WHATSAPP_PROVIDER", "generic").strip().lower()

    if name == "generic" or name == "":
        has_universal_config = any(
            _str_env(env, var, "").strip()
            for var in ("WA_INBOUND_FROM_PATH", "WA_INBOUND_TEXT_PATH", "WA_OUTBOUND_BODY_TEMPLATE")
        )
        if has_universal_config:
            return UniversalProvider({})._with_env(env)
        return _generic

    preset = _PRESETS.get(name)
    if preset is None:
        known = ", ".join(["generic"] + sorted(_PRESETS))
        raise RuntimeError(f"Unknown WHATSAPP_PROVIDER={name!r}. Known providers: {known}")

    return UniversalProvider(preset)._with_env(env)
