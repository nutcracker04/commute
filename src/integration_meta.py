"""Operator-facing metadata: inventory URL contract and D1 registry description (testable without Workers)."""

from __future__ import annotations


def build_inventory_contract(public_base: str, example_ref_id: str = "deadbeef01234567") -> dict[str, str]:
    base = public_base.rstrip("/")
    return {
        "url_template": f"{base}/r/{{ref_id}}",
        "optional_slug_template": f"{base}/r/{{slug}}",
        "slug_note": "If physical_qrs.slug is set, the QR may encode /r/{slug} instead of ref_id.",
        "example_ref_id": example_ref_id,
        "example_full_url": f"{base}/r/{example_ref_id}",
        "instructions": "Encode example_full_url (or slug URL) as the QR payload. Create rows with POST /api/physical-qrs; ref and text live in physical_qrs.",
    }


def integration_document(*, public_base: str) -> dict[str, object]:
    return {
        "ok": True,
        "flow": "qr-whatsapp-leads",
        "registry": {
            "backend": "D1",
            "inventory_table": "physical_qrs",
            "ttl_note": "expires_at starts at first GET /r/...; SCAN_TTL_SECONDS (default 3h).",
        },
        "inventory_qr_payload": build_inventory_contract(public_base),
        "polarr_qr_payload": build_inventory_contract(public_base),
        "webhook": {
            "callback_paths": ["/webhook/whatsapp", "/webhook/msg91"],
            "preferred_path": "/webhook/whatsapp",
            "method": "POST",
            "content_type": "application/json",
            "notes": "Inbound WhatsApp webhooks (New). GET on same paths returns ok for URL probes.",
        },
        "secrets": {
            "fallback_whatsapp_replies": ["MSG91_AUTH_KEY", "MSG91_INTEGRATED_NUMBER"],
            "optional_inbound_auth": ["MSG91_WEBHOOK_SECRET"],
            "optional_vars": ["MSG91_SESSION_SEND_URL", "MSG91_WEBHOOK_SECRET_HEADER"],
            "admin_inventory_api": "ADMIN_API_SECRET (required for /api/physical-qrs; 503 if unset). Local dev: .dev.vars",
            "public_base": "PUBLIC_BASE_URL in wrangler [vars] for correct /integration links",
        },
        "admin_api": {
            "create": {"method": "POST", "path": "/api/physical-qrs"},
            "list": {"method": "GET", "path": "/api/physical-qrs"},
            "auth_header": "ADMIN_API_SECRET_HEADER (default X-Admin-Key) or Authorization: Bearer …",
        },
        "setup_doc": "docs/flow-alignment.md",
    }
