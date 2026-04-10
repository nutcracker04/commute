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
            "coupon_vars": "COUPON_CODE_PREFIX, COUPON_RANDOM_LENGTH, COUPON_WHATSAPP_TEMPLATE ({code}, {code_spaced}); legacy PROMO_CODE_PREFIX / PROMO_WHATSAPP_TEMPLATE / BRAND_COUPON_PREFIX",
            "admin_inventory_api": "ADMIN_API_SECRET (required for admin JSON APIs; 503 if unset). Local dev: .dev.vars",
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
            "auth_header": "ADMIN_API_SECRET_HEADER (default X-Admin-Key) or Authorization: Bearer …",
        },
        "setup_doc": "docs/flow-alignment.md",
    }
