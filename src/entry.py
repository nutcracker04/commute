"""
Cloudflare Python Worker: QR redirect, WhatsApp inbound webhook → queue, consumer matching.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from pyodide.ffi import to_js

from integration_meta import integration_document
from matching import (
    candidate_from_row,
    extract_ref_id,
    pick_best_match,
)
from prefill import build_prefilled_text
from payload import iter_webhook_inbound_jobs

try:
    from workers import Response, WorkerEntrypoint
except ImportError:
    WorkerEntrypoint = object  # type: ignore[misc,assignment]

    class Response:  # type: ignore[no-redef]
        def __init__(self, body: str = "", status: int = 200, headers: dict | None = None):
            self.body = body
            self.status = status
            self.headers = headers or {}


def _int_env(env: Any, name: str, default: int) -> int:
    raw = getattr(env, name, None)
    if raw is None:
        return default
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return default


def _float_env(env: Any, name: str, default: float) -> float:
    raw = getattr(env, name, None)
    if raw is None:
        return default
    try:
        return float(str(raw))
    except (TypeError, ValueError):
        return default


def _str_env(env: Any, name: str, default: str = "") -> str:
    raw = getattr(env, name, None)
    return default if raw is None else str(raw)


def _public_base_from_request(request: Any, env: Any) -> str:
    override = _str_env(env, "PUBLIC_BASE_URL", "").strip()
    if override:
        return override.rstrip("/")
    u = urlparse(str(request.url))
    scheme = u.scheme or "https"
    netloc = u.netloc
    if not netloc:
        return "https://example.invalid"
    return f"{scheme}://{netloc}"


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


def _admin_request_token(request: Any, env: Any) -> str | None:
    hdr_name = _str_env(env, "ADMIN_API_SECRET_HEADER", "X-Admin-Key").strip() or "X-Admin-Key"
    raw = _header_get(request.headers, hdr_name)
    if raw is None:
        return None
    s = str(raw).strip()
    if hdr_name.lower() == "authorization" and s.lower().startswith("bearer "):
        s = s[7:].strip()
    return s or None


def _admin_api_check(request: Any, env: Any) -> Response | None:
    """
    Returns a Response to send if the request is not allowed; None if OK.
    Rejects when ADMIN_API_SECRET is unset (no accidental open admin API).
    """
    secret = _str_env(env, "ADMIN_API_SECRET", "")
    if not secret:
        return Response(
            json.dumps({"error": "admin API not configured (set ADMIN_API_SECRET)"}),
            status=503,
            headers={"content-type": "application/json"},
        )
    got = _admin_request_token(request, env)
    if got != secret:
        return Response(
            json.dumps({"error": "unauthorized"}),
            status=401,
            headers={"content-type": "application/json"},
        )
    return None


def _json_response(data: object, status: int = 200) -> Response:
    return Response(
        json.dumps(data),
        status=status,
        headers={"content-type": "application/json; charset=utf-8"},
    )


def _js_to_py(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "to_py"):
        return obj.to_py()
    return obj


async def _d1_first(db: Any, sql: str, *bind_args: Any) -> dict[str, Any] | None:
    stmt = db.prepare(sql)
    bound = stmt.bind(*bind_args) if bind_args else stmt
    row = _js_to_py(await bound.first())
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return None


async def _d1_all(db: Any, sql: str, *bind_args: Any) -> list[dict[str, Any]]:
    stmt = db.prepare(sql)
    bound = stmt.bind(*bind_args) if bind_args else stmt
    result = _js_to_py(await bound.all())
    if not isinstance(result, dict):
        return []
    rows = result.get("results")
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
    return out


async def _d1_run(db: Any, sql: str, *bind_args: Any) -> None:
    stmt = db.prepare(sql)
    bound = stmt.bind(*bind_args) if bind_args else stmt
    await bound.run()


async def _d1_run_changes(db: Any, sql: str, *bind_args: Any) -> int:
    stmt = db.prepare(sql)
    bound = stmt.bind(*bind_args) if bind_args else stmt
    result = _js_to_py(await bound.run())
    if not isinstance(result, dict):
        return 0
    meta = result.get("meta") or {}
    if isinstance(meta, dict):
        return int(meta.get("changes", 0) or 0)
    return int(getattr(meta, "changes", 0) or 0)


class Default(WorkerEntrypoint):
    async def fetch(self, request):  # type: ignore[override]
        url = str(request.url)
        parsed = urlparse(url)
        path = parsed.path or "/"
        method = str(request.method).upper()

        if path.startswith("/r/"):
            return await self._handle_physical_redirect(request, path)
        if self._is_whatsapp_webhook_path(path):
            if method == "GET":
                return await self._handle_webhook_get()
            if method == "POST":
                return await self._handle_webhook_post(request)
        if path == "/integration":
            base = _public_base_from_request(request, self.env)
            doc = integration_document(public_base=base)
            return Response(
                json.dumps(doc),
                headers={"content-type": "application/json"},
            )
        if path in ("/", "/health"):
            base = _public_base_from_request(request, self.env)
            return Response(
                json.dumps(
                    {
                        "ok": True,
                        "integration": f"{base}/integration",
                    }
                ),
                headers={"content-type": "application/json"},
            )
        if path == "/api/physical-qrs":
            if method == "GET":
                return await self._handle_api_physical_qrs_list(request, url)
            if method == "POST":
                return await self._handle_api_physical_qrs_create(request, url)
            return Response("Method not allowed", status=405)

        return Response("Not found", status=404)

    @staticmethod
    def _is_whatsapp_webhook_path(path: str) -> bool:
        if path in ("/webhook/whatsapp", "/webhook/msg91"):
            return True
        return path.endswith("/webhook/whatsapp") or path.endswith("/webhook/msg91")

    async def _handle_physical_redirect(self, request, path: str) -> Response:
        token = path.removeprefix("/r/").strip("/").split("/")[0]
        if not token:
            return Response("Missing ref or slug", status=400)

        row = await _d1_first(
            self.env.DB,
            """
            SELECT p.ref_id, p.full_prefilled_text, p.first_scanned_at, p.expires_at,
                   e.wa_phone_e164
            FROM physical_qrs p
            JOIN events e ON e.id = p.event_id
            WHERE p.ref_id = ? OR p.slug = ?
            """,
            token,
            token,
        )
        if not row:
            return Response("Unknown QR", status=404)

        now = int(time.time())
        expires_at = row.get("expires_at")
        if expires_at is not None and int(expires_at) <= now:
            return Response(
                "This link has expired. Please use a current QR code.",
                status=410,
                headers={"content-type": "text/plain; charset=utf-8"},
            )

        ttl = _int_env(self.env, "SCAN_TTL_SECONDS", 10800)
        first_scanned = row.get("first_scanned_at")
        ref_id = str(row["ref_id"])
        if first_scanned is None:
            await _d1_run(
                self.env.DB,
                """
                UPDATE physical_qrs
                SET first_scanned_at = ?, expires_at = ?
                WHERE ref_id = ? AND first_scanned_at IS NULL
                """,
                now,
                now + ttl,
                ref_id,
            )

        full_text = str(row["full_prefilled_text"])
        phone = str(row["wa_phone_e164"]).lstrip("+")
        wa_url = f"https://wa.me/{phone}?text={quote(full_text, safe='')}"
        return Response("", status=302, headers={"Location": wa_url})

    async def _handle_api_physical_qrs_create(self, request, url: str) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        body_text = await request.text()
        try:
            payload = json.loads(body_text) if body_text.strip() else {}
        except json.JSONDecodeError:
            return _json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(payload, dict):
            return _json_response({"error": "body must be a JSON object"}, status=400)

        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            return _json_response({"error": "event_id is required"}, status=400)

        raw_count = payload.get("count", 1)
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            return _json_response({"error": "invalid count"}, status=400)
        max_count = _int_env(self.env, "ADMIN_PROVISION_MAX_COUNT", 500)
        if count < 1 or count > max_count:
            return _json_response(
                {"error": f"count must be between 1 and {max_count}"},
                status=400,
            )

        batch_id = payload.get("batch_id")
        batch_s = str(batch_id).strip() if batch_id is not None and str(batch_id).strip() else None
        label_raw = payload.get("label")
        label_s = str(label_raw).strip() if label_raw is not None and str(label_raw).strip() else None

        ev = await _d1_first(
            self.env.DB,
            "SELECT id, greeting, context_text, request_text FROM events WHERE id = ?",
            event_id,
        )
        if not ev:
            return _json_response({"error": "unknown event_id"}, status=404)

        greeting = str(ev.get("greeting", "Hey!"))
        context_text = str(ev["context_text"])
        request_text = str(ev.get("request_text", "I'd like more info"))

        base = _public_base_from_request(request, self.env)
        now = int(time.time())
        items: list[dict[str, Any]] = []

        for _ in range(count):
            ref_id = uuid.uuid4().hex[:16]
            full_text = build_prefilled_text(greeting, context_text, request_text, ref_id)
            await _d1_run(
                self.env.DB,
                """
                INSERT INTO physical_qrs (
                    ref_id, event_id, full_prefilled_text, batch_id, label,
                    external_sku, slug, provisioned_at, first_scanned_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL)
                """,
                ref_id,
                event_id,
                full_text,
                batch_s,
                label_s,
                now,
            )
            items.append(
                {
                    "ref_id": ref_id,
                    "event_id": event_id,
                    "full_prefilled_text": full_text,
                    "redirect_url": f"{base}/r/{ref_id}",
                    "batch_id": batch_s,
                    "label": label_s,
                    "provisioned_at": now,
                }
            )

        return _json_response({"created": len(items), "items": items}, status=201)

    async def _handle_api_physical_qrs_list(self, request, url: str) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        parsed = urlparse(url)
        q = parse_qs(parsed.query or "")
        def _first(key: str) -> str | None:
            vals = q.get(key, [])
            return str(vals[0]).strip() if vals and str(vals[0]).strip() else None

        filter_event = _first("event_id")
        filter_batch = _first("batch_id")

        try:
            limit = int(_first("limit") or "100")
        except ValueError:
            return _json_response({"error": "invalid limit"}, status=400)
        try:
            offset = int(_first("offset") or "0")
        except ValueError:
            return _json_response({"error": "invalid offset"}, status=400)

        max_limit = _int_env(self.env, "ADMIN_LIST_MAX_LIMIT", 500)
        if limit < 1 or limit > max_limit:
            return _json_response(
                {"error": f"limit must be between 1 and {max_limit}"},
                status=400,
            )
        if offset < 0:
            return _json_response({"error": "offset must be >= 0"}, status=400)

        where_parts: list[str] = []
        bind_count: list[Any] = []
        if filter_event:
            where_parts.append("event_id = ?")
            bind_count.append(filter_event)
        if filter_batch:
            where_parts.append("batch_id = ?")
            bind_count.append(filter_batch)
        where_sql = " AND ".join(where_parts) if where_parts else "1=1"

        count_row = await _d1_first(
            self.env.DB,
            f"SELECT COUNT(*) AS n FROM physical_qrs WHERE {where_sql}",
            *bind_count,
        )
        total = int(count_row["n"]) if count_row and count_row.get("n") is not None else 0

        rows = await _d1_all(
            self.env.DB,
            f"""
            SELECT ref_id, event_id, full_prefilled_text, batch_id, label, slug, external_sku,
                   provisioned_at, first_scanned_at, expires_at
            FROM physical_qrs
            WHERE {where_sql}
            ORDER BY provisioned_at DESC, ref_id DESC
            LIMIT ? OFFSET ?
            """,
            *bind_count,
            limit,
            offset,
        )

        base = _public_base_from_request(request, self.env)
        items: list[dict[str, Any]] = []
        for r in rows:
            rid = str(r["ref_id"])
            items.append(
                {
                    "ref_id": rid,
                    "event_id": str(r["event_id"]),
                    "full_prefilled_text": str(r["full_prefilled_text"]),
                    "redirect_url": f"{base}/r/{rid}",
                    "batch_id": r.get("batch_id"),
                    "label": r.get("label"),
                    "slug": r.get("slug"),
                    "external_sku": r.get("external_sku"),
                    "provisioned_at": int(r["provisioned_at"])
                    if r.get("provisioned_at") is not None
                    else None,
                    "first_scanned_at": int(r["first_scanned_at"])
                    if r.get("first_scanned_at") is not None
                    else None,
                    "expires_at": int(r["expires_at"]) if r.get("expires_at") is not None else None,
                }
            )

        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset},
            status=200,
        )

    async def _handle_webhook_get(self) -> Response:
        """Inbound provider may probe the callback URL; always return 200."""
        return Response("ok", headers={"content-type": "text/plain"})

    async def _handle_webhook_post(self, request) -> Response:
        body_text = await request.text()

        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            return Response("Bad JSON", status=400)

        if not isinstance(payload, dict):
            return Response("Bad JSON", status=400)

        wh_secret = _str_env(self.env, "MSG91_WEBHOOK_SECRET", "")
        if wh_secret:
            hdr_name = _str_env(self.env, "MSG91_WEBHOOK_SECRET_HEADER", "X-Webhook-Secret")
            got = _header_get(request.headers, hdr_name)
            if got != wh_secret:
                return Response("Invalid webhook secret", status=401)

        messages = iter_webhook_inbound_jobs(payload)
        received_at = int(time.time())

        for msg in messages:
            job = {
                "wa_message_id": msg["wa_message_id"],
                "from_phone": msg["from_phone"],
                "text": msg["text"],
                "received_at": received_at,
            }
            try:
                await self.env.LEAD_QUEUE.send(to_js(job))
            except Exception:
                return Response("Queue unavailable", status=503)

        return Response(json.dumps({"received": len(messages)}), headers={"content-type": "application/json"})

    async def queue(self, batch):  # type: ignore[override]
        now_ts = int(time.time())
        min_score = _float_env(self.env, "LCS_MIN_SCORE", 0.35)
        min_gap = _float_env(self.env, "LCS_MIN_GAP", 0.08)
        tau = _float_env(self.env, "LCS_RECENCY_TAU_MINUTES", 60.0)
        max_cand = _int_env(self.env, "LCS_MAX_CANDIDATES", 500)
        fallback_text = _str_env(
            self.env,
            "FALLBACK_REPLY_TEXT",
            "We could not link this message to a campaign. Please scan the QR code again.",
        )

        for message in batch.messages:
            body = message.body
            if hasattr(body, "to_py"):
                py = body.to_py()
                body = py if isinstance(py, dict) else {}
            if not isinstance(body, dict):
                continue

            wa_message_id = str(body.get("wa_message_id", ""))
            from_phone = str(body.get("from_phone", ""))
            text = str(body.get("text", ""))
            if not wa_message_id or not from_phone:
                message.ack()
                continue

            inserted = await _d1_run_changes(
                self.env.DB,
                """
                INSERT OR IGNORE INTO processed_inbound_messages (whatsapp_message_id, from_phone, processed_at)
                VALUES (?, ?, ?)
                """,
                wa_message_id,
                from_phone,
                now_ts,
            )
            if inserted == 0:
                message.ack()
                continue

            claimed = True
            try:
                ref = extract_ref_id(text)
                event_id: str | None = None
                matched_ref: str | None = None
                method: str | None = None

                if ref:
                    row = await _d1_first(
                        self.env.DB,
                        """
                        SELECT ref_id, event_id
                        FROM physical_qrs
                        WHERE ref_id = ?
                          AND first_scanned_at IS NOT NULL
                          AND expires_at > ?
                        """,
                        ref,
                        now_ts,
                    )
                    if row:
                        event_id = str(row["event_id"])
                        matched_ref = str(row["ref_id"])
                        method = "ref_id"

                if not event_id:
                    rows = await _d1_all(
                        self.env.DB,
                        """
                        SELECT ref_id, event_id, full_prefilled_text,
                               first_scanned_at AS match_anchor_at
                        FROM physical_qrs
                        WHERE first_scanned_at IS NOT NULL AND expires_at > ?
                        ORDER BY first_scanned_at DESC
                        LIMIT ?
                        """,
                        now_ts,
                        max_cand,
                    )
                    candidates = [candidate_from_row(r) for r in rows]
                    match = pick_best_match(
                        text,
                        candidates,
                        now_ts=now_ts,
                        min_score=min_score,
                        min_gap=min_gap,
                        tau_minutes=tau,
                    )
                    if match:
                        event_id = match.event_id
                        matched_ref = match.ref_id
                        method = match.method

                if event_id and method:
                    await _d1_run(
                        self.env.DB,
                        """
                        INSERT INTO leads (whatsapp_message_id, from_phone, event_id, ref_id, match_method, raw_text, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        wa_message_id,
                        from_phone,
                        event_id,
                        matched_ref or "",
                        method,
                        text,
                        now_ts,
                    )
                    await _d1_run(
                        self.env.DB,
                        """
                        UPDATE processed_inbound_messages
                        SET ref_id = ?, event_id = ?, match_method = ?
                        WHERE whatsapp_message_id = ?
                        """,
                        matched_ref or "",
                        event_id,
                        method,
                        wa_message_id,
                    )
                else:
                    await self._send_whatsapp_session_text(from_phone, fallback_text)
            except Exception:
                if claimed:
                    await _d1_run(
                        self.env.DB,
                        "DELETE FROM processed_inbound_messages WHERE whatsapp_message_id = ?",
                        wa_message_id,
                    )
                raise

            message.ack()

    async def _send_whatsapp_session_text(self, to_phone: str, body: str) -> None:
        authkey = _str_env(self.env, "MSG91_AUTH_KEY", "")
        integrated = _str_env(self.env, "MSG91_INTEGRATED_NUMBER", "")
        if not authkey or not integrated:
            return
        send_url = _str_env(
            self.env,
            "MSG91_SESSION_SEND_URL",
            "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/send-session-message/",
        )
        recipient = to_phone.lstrip("+")
        payload = {
            "integrated_number": integrated.lstrip("+"),
            "recipient_number": recipient,
            "content_type": "text",
            "text": body,
        }
        from js import fetch  # type: ignore[import-not-found]

        headers = to_js({"authkey": authkey, "Content-Type": "application/json"})
        await fetch(
            send_url,
            to_js(
                {
                    "method": "POST",
                    "headers": headers,
                    "body": json.dumps(payload),
                }
            ),
        )
