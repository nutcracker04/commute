"""Operator-facing metadata: inventory URL contract and D1 registry description (testable without Workers)."""

from __future__ import annotations


def build_inventory_contract(public_base: str, example_ref_id: str = "1") -> dict[str, str]:
    base = public_base.rstrip("/")
    return {
        "url_template": f"{base}/r/{{ref_id}}",
        "example_ref_id": example_ref_id,
        "example_full_url": f"{base}/r/{example_ref_id}",
        "instructions": (
            "ref_id is the integer row id in the qrs table (generated QR). "
            "Encode example_full_url as the QR payload. Provision with POST /api/qrs. "
            "Assign drivers.qr_ref_id = qrs.id (same ref id as leads); multipart POST /api/drivers with qr_ref_id, UPI + identity files."
        ),
    }


def integration_document(*, public_base: str) -> dict[str, object]:
    return {
        "ok": True,
        "flow": "qr-whatsapp-leads",
        "registry": {
            "backend": "D1",
            "inventory_table": "qrs",
            "ephemeral_match_state": "Workers KV (SCAN_KV) + commute-session-index queue; ss:data:* keys TTL from SCAN_TTL_SECONDS; wi:nm:* keys for fallback-reply dedupe (no lead row).",
            "drivers_table": "drivers (qr_ref_id → qrs.id, same ref id as leads; upi_qr_asset_url, identity_asset_urls JSON; optional legacy qr_asset_url via PUT qr-image)",
            "commission_tables": ["weeks", "driver_lead_counts"],
            "leads": "ref_id = qrs.id; coupon_code_sent after match (prefix + random); live DLC increment + weekly cron reconcile",
            "ttl_note": "Each GET /r/{ref_id} writes a KV session and enqueues index update; LCS match consumes that session in KV.",
        },
        "inventory_qr_payload": build_inventory_contract(public_base),
        "webhook": {
            "callback_paths": ["/webhook/whatsapp"],
            "preferred_path": "/webhook/whatsapp",
            "method": "POST",
            "content_type": "provider-dependent (JSON for most; form-encoded for twilio/gupshup)",
            "notes": (
                "Inbound WhatsApp webhooks: POST is not authenticated. "
                "GET returns 'ok' or echoes hub.challenge when WHATSAPP_PROVIDER uses Meta-style GET handling."
            ),
        },
        "provider": {
            "selector_var": "WHATSAPP_PROVIDER",
            "selector_values": ["generic (default)", "meta", "360dialog", "twilio", "gupshup", "wati", "custom"],
            "architecture": (
                "Env-driven universal adapter. A single UniversalProvider class reads WA_INBOUND_*, "
                "WA_OUTBOUND_*, WA_VERIFY_* vars to handle any BSP. Named presets (meta, twilio, etc.) "
                "supply default mappings. Set WHATSAPP_PROVIDER=custom and configure WA_* vars manually "
                "for any BSP not in the preset list — zero Python code required."
            ),
            "inbound_vars": {
                "WA_INBOUND_UNWRAP": "Envelope strategy: 'none' (default), 'meta' (entry→changes→value→messages), 'form' (application/x-www-form-urlencoded)",
                "WA_INBOUND_FROM_PATH": "Dot-path to sender phone (e.g. 'from', 'waId', 'payload.source', 'From')",
                "WA_INBOUND_TEXT_PATH": "Dot-path to message text (e.g. 'text.body', 'text', 'Body', 'payload.payload.text')",
                "WA_INBOUND_ID_PATH": "Dot-path to message ID (e.g. 'id', 'whatsappMessageId', 'MessageSid')",
                "WA_INBOUND_NAME_PATH": "Dot-path to sender name, or '$contacts' for Meta contacts array lookup",
                "WA_INBOUND_TS_PATH": "Dot-path to timestamp",
                "WA_INBOUND_TS_UNIT": "'s' (seconds, default) or 'ms' (milliseconds — Gupshup)",
                "WA_INBOUND_FROM_STRIP": "Prefix to strip from phone (e.g. 'whatsapp:+' for Twilio)",
                "WA_INBOUND_SKIP_WHEN": "Skip rule: 'path=value' (skip when equal) or 'path!=value' (skip when NOT equal)",
                "WA_INBOUND_TYPE_PATH": "Dot-path to message type field (for filtering non-text)",
                "WA_INBOUND_TYPE_VALUE": "Expected type value (default 'text')",
            },
            "outbound_vars": {
                "WA_OUTBOUND_BODY_TEMPLATE": "Body template with {to}, {from}, {text_escaped}, {text_urlencoded}, {text_json_urlencoded}, {app_name} placeholders",
                "WA_OUTBOUND_URL_TEMPLATE": "URL template with {base_url}, {to}, {text_urlencoded} placeholders (overrides WHATSAPP_OUTBOUND_URL when set)",
                "WA_OUTBOUND_CONTENT_TYPE": "'application/json' (default) or 'application/x-www-form-urlencoded'",
            },
            "verify_vars": {
                "WA_VERIFY_MODE": "'none' (default), 'header' (shared secret), 'hmac-sha256' (Meta), 'hmac-sha1-twilio' (Twilio)",
                "WA_VERIFY_HEADER": "Header name containing signature/secret",
                "WA_VERIFY_SECRET_VAR": "Env var holding the HMAC key (default depends on mode)",
            },
            "challenge_vars": {
                "WA_GET_CHALLENGE": "'none' (default) or 'meta' (echo hub.challenge)",
            },
            "common_outbound_vars": {
                "WHATSAPP_OUTBOUND_URL": "BSP API endpoint URL",
                "WHATSAPP_OUTBOUND_AUTH_HEADER": "Header name for authentication",
                "WHATSAPP_OUTBOUND_AUTH_SECRET": "Auth value (secret — never in wrangler.toml)",
                "WHATSAPP_BUSINESS_PHONE": "Your sender number (E.164, no leading +)",
            },
            "presets": {
                "meta": "Meta Cloud API — HMAC-SHA256 verify, meta envelope unwrap, nested JSON outbound",
                "360dialog": "360dialog — same as meta but no HMAC verify",
                "twilio": "Twilio — HMAC-SHA1 verify, form-encoded inbound/outbound",
                "gupshup": "Gupshup — no verify, double-nested JSON inbound, form-encoded outbound",
                "wati": "WATI — no verify, flat JSON inbound, URL-path outbound",
            },
            "custom_bsp_example": {
                "description": "For any BSP (MSG91, Interakt, Kaleyra, AiSensy, etc.): read their webhook docs, set WA_INBOUND_* paths. Read their send API docs, set WA_OUTBOUND_BODY_TEMPLATE.",
                "steps": [
                    "1. Set WHATSAPP_PROVIDER=custom",
                    "2. Set WA_INBOUND_FROM_PATH, WA_INBOUND_TEXT_PATH (required minimum)",
                    "3. Set WA_INBOUND_ID_PATH, WA_INBOUND_NAME_PATH, WA_INBOUND_TS_PATH (optional)",
                    "4. Set WA_OUTBOUND_BODY_TEMPLATE with {to} and {text_escaped} placeholders",
                    "5. Set WHATSAPP_OUTBOUND_URL, WHATSAPP_OUTBOUND_AUTH_HEADER, WHATSAPP_OUTBOUND_AUTH_SECRET",
                    "6. Deploy — zero Python code needed",
                ],
            },
            "backward_compat": (
                "When WHATSAPP_PROVIDER is unset or 'generic' and no WA_INBOUND_* vars exist, "
                "the legacy payload.py heuristic + whatsapp_outbound.py builder is used. "
                "No migration needed for existing deployments."
            ),
        },
        "secrets": {
            "common": "WHATSAPP_OUTBOUND_AUTH_SECRET (outbound sends to BSP / Graph API)",
            "coupon_vars": "COUPON_CODE_PREFIX, COUPON_RANDOM_LENGTH, COUPON_WHATSAPP_TEMPLATE ({code}, {code_spaced}); legacy PROMO_CODE_PREFIX / BRAND_COUPON_PREFIX for prefix only",
            "admin_inventory_api": "Admin JSON APIs require no authentication.",
            "r2_driver_assets": "DRIVER_ASSETS R2 binding; set R2_PUBLIC_BASE when using a public bucket hostname.",
            "public_base": "PUBLIC_BASE_URL in wrangler [vars] for correct /integration links",
        },
        "admin_api": {
            "qrs_create": {"method": "POST", "path": "/api/qrs"},
            "qrs_list": {"method": "GET", "path": "/api/qrs"},
            "qrs_available_refs": {
                "method": "GET",
                "path": "/api/qrs/available-refs",
                "query": "limit, offset",
                "response": "ref_ids, has_more",
            },
            "drivers_create": {
                "method": "POST",
                "path": "/api/drivers",
                "content_type": "multipart/form-data",
                "fields": [
                    "name",
                    "phone",
                    "qr_ref_id",
                    "upi_qr (file)",
                    "identity (file)",
                ],
            },
            "drivers_list": {"method": "GET", "path": "/api/drivers"},
            "drivers_patch": {"method": "PATCH", "path": "/api/drivers/{id}"},
            "driver_qr_image": {"method": "PUT", "path": "/api/drivers/{id}/qr-image"},
            "driver_upi_qr_image": {"method": "PUT", "path": "/api/drivers/{id}/upi-qr-image"},
            "driver_identity_image": {"method": "PUT", "path": "/api/drivers/{id}/identity-image"},
            "leads_list": {
                "method": "GET",
                "path": "/api/leads",
                "query": "ref_id (legacy: qr_id)",
                "response_fields": ["coupon_code_sent"],
            },
            "weeks_list": {"method": "GET", "path": "/api/weeks"},
            "dlc_list": {"method": "GET", "path": "/api/dlc"},
            "run_dlc_cron": {"method": "POST", "path": "/api/admin/run-dlc"},
            "auth_header": "None (admin APIs are open).",
        },
        "setup_doc": "docs/flow-alignment.md",
    }
