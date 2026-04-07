"""
Cloudflare Python Worker: QR redirect, WhatsApp inbound webhook → queue, consumer matching.
"""

from __future__ import annotations

import json
import time
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


def _bool_env(env: Any, name: str, default: bool) -> bool:
    raw = getattr(env, name, None)
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return default


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


_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Admin-Key, Authorization",
    "Access-Control-Max-Age": "86400",
}


def _json_response(data: object, status: int = 200) -> Response:
    return Response(
        json.dumps(data),
        status=status,
        headers={"content-type": "application/json; charset=utf-8", **_CORS_HEADERS},
    )


def _js_to_py(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "to_py"):
        return obj.to_py()
    return obj


def _d1_clean_value(v: Any) -> Any:
    """Convert JS null/undefined proxy values to Python None after D1 row fetch."""
    if v is None:
        return None
    type_name = type(v).__name__
    if type_name in ("JsNull", "JsUndefined"):
        return None
    if hasattr(v, "to_py"):
        return v.to_py()
    return v


def _d1_clean_row(row: dict) -> dict:
    return {k: _d1_clean_value(v) for k, v in row.items()}


def _d1_nullsafe(sql: str, args: tuple[Any, ...]) -> tuple[str, tuple[Any, ...]]:
    """Replace ? placeholders with NULL literal for any None values.

    D1's Python binding cannot accept None/null bind parameters, so we inline
    NULL directly into the SQL and remove those positions from the bind list.
    """
    parts = sql.split("?")
    if len(parts) - 1 != len(args):
        return sql, args
    new_args: list[Any] = []
    out: list[str] = [parts[0]]
    for i, arg in enumerate(args):
        if arg is None:
            out.append("NULL")
        else:
            out.append("?")
            new_args.append(arg)
        out.append(parts[i + 1])
    return "".join(out), tuple(new_args)


async def _d1_first(db: Any, sql: str, *bind_args: Any) -> dict[str, Any] | None:
    safe_sql, safe_args = _d1_nullsafe(sql, bind_args)
    stmt = db.prepare(safe_sql)
    bound = stmt.bind(*safe_args) if safe_args else stmt
    row = _js_to_py(await bound.first())
    if row is None:
        return None
    if isinstance(row, dict):
        return _d1_clean_row(dict(row))
    return None


async def _d1_all(db: Any, sql: str, *bind_args: Any) -> list[dict[str, Any]]:
    safe_sql, safe_args = _d1_nullsafe(sql, bind_args)
    stmt = db.prepare(safe_sql)
    bound = stmt.bind(*safe_args) if safe_args else stmt
    result = _js_to_py(await bound.all())
    if not isinstance(result, dict):
        return []
    rows = result.get("results")
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(_d1_clean_row(dict(row)))
    return out


async def _d1_run(db: Any, sql: str, *bind_args: Any) -> None:
    safe_sql, safe_args = _d1_nullsafe(sql, bind_args)
    stmt = db.prepare(safe_sql)
    bound = stmt.bind(*safe_args) if safe_args else stmt
    await bound.run()


async def _d1_run_changes(db: Any, sql: str, *bind_args: Any) -> int:
    safe_sql, safe_args = _d1_nullsafe(sql, bind_args)
    stmt = db.prepare(safe_sql)
    bound = stmt.bind(*safe_args) if safe_args else stmt
    result = _js_to_py(await bound.run())
    if not isinstance(result, dict):
        return 0
    meta = result.get("meta") or {}
    if isinstance(meta, dict):
        return int(meta.get("changes", 0) or 0)
    return int(getattr(meta, "changes", 0) or 0)


async def _d1_last_insert_rowid(db: Any, sql: str, *bind_args: Any) -> int | None:
    """Run an INSERT and return the last_row_id from the D1 run result meta."""
    safe_sql, safe_args = _d1_nullsafe(sql, bind_args)
    stmt = db.prepare(safe_sql)
    bound = stmt.bind(*safe_args) if safe_args else stmt
    result = _js_to_py(await bound.run())
    if not isinstance(result, dict):
        return None
    meta = result.get("meta") or {}
    if isinstance(meta, dict):
        rowid = meta.get("last_row_id")
        if rowid is not None:
            return int(rowid)
    rowid = getattr(meta, "last_row_id", None)
    return int(rowid) if rowid is not None else None


class Default(WorkerEntrypoint):
    async def fetch(self, request):  # type: ignore[override]
        url = str(request.url)
        parsed = urlparse(url)
        path = parsed.path or "/"
        method = str(request.method).upper()

        if method == "OPTIONS":
            return Response("", status=204, headers=_CORS_HEADERS)

        if path.startswith("/r/"):
            return await self._handle_redirect(request, path)
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
        if path == "/api/qrs":
            if method == "GET":
                return await self._handle_api_qrs_list(request, url)
            if method == "POST":
                return await self._handle_api_qrs_create(request, url)
            return Response("Method not allowed", status=405)

        if path == "/api/leads":
            if method == "GET":
                return await self._handle_api_leads_list(request, url)
            return Response("Method not allowed", status=405)

        return Response("Not found", status=404)

    @staticmethod
    def _is_whatsapp_webhook_path(path: str) -> bool:
        if path in ("/webhook/whatsapp", "/webhook/msg91"):
            return True
        return path.endswith("/webhook/whatsapp") or path.endswith("/webhook/msg91")

    async def _handle_redirect(self, request, path: str) -> Response:
        token = path.removeprefix("/r/").strip("/").split("/")[0]
        if not token:
            return Response("Missing QR id", status=400)

        try:
            qr_id = int(token)
        except ValueError:
            return Response("Invalid QR id", status=400)

        row = await _d1_first(
            self.env.DB,
            "SELECT id, full_prefilled_text FROM qrs WHERE id = ?",
            qr_id,
        )
        if not row:
            return Response("Unknown QR", status=404)

        full_text = str(row["full_prefilled_text"])
        phone = _str_env(self.env, "MSG91_INTEGRATED_NUMBER", "").lstrip("+")
        if not phone:
            return Response("WhatsApp number not configured", status=503)

        now = int(time.time())
        ttl = _int_env(self.env, "SCAN_TTL_SECONDS", 10800)
        expires_at = now + ttl

        await _d1_run(
            self.env.DB,
            """
            INSERT INTO scan_sessions (qr_id, full_text, scanned_at, expires_at, claimed_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            qr_id,
            full_text,
            now,
            expires_at,
        )

        wa_url = f"https://wa.me/{phone}?text={quote(full_text, safe='')}"
        return Response("", status=302, headers={"Location": wa_url})

    async def _handle_api_qrs_create(self, request, url: str) -> Response:
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

        greeting = _str_env(self.env, "WA_GREETING", "Hey!")
        context_text = _str_env(self.env, "WA_CONTEXT_TEXT", "Regarding the offer")
        request_text = _str_env(self.env, "WA_REQUEST_TEXT", "I would like more information")

        base = _public_base_from_request(request, self.env)
        now = int(time.time())
        items: list[dict[str, Any]] = []

        for _ in range(count):
            placeholder_text = build_prefilled_text(greeting, context_text, request_text, "0")
            new_id = await _d1_last_insert_rowid(
                self.env.DB,
                "INSERT INTO qrs (full_prefilled_text, provisioned_at) VALUES (?, ?)",
                placeholder_text,
                now,
            )
            if new_id is None:
                return _json_response({"error": "failed to insert QR row"}, status=500)

            full_text = build_prefilled_text(greeting, context_text, request_text, str(new_id), qr_id=new_id)
            await _d1_run(
                self.env.DB,
                "UPDATE qrs SET full_prefilled_text = ? WHERE id = ?",
                full_text,
                new_id,
            )

            items.append(
                {
                    "id": new_id,
                    "full_prefilled_text": full_text,
                    "redirect_url": f"{base}/r/{new_id}",
                    "provisioned_at": now,
                    "last_scanned_at": None,
                    "expires_at": None,
                }
            )

        return _json_response({"created": len(items), "items": items}, status=201)

    async def _handle_api_qrs_list(self, request, url: str) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        parsed = urlparse(url)
        q = parse_qs(parsed.query or "")

        def _first(key: str) -> str | None:
            vals = q.get(key, [])
            return str(vals[0]).strip() if vals and str(vals[0]).strip() else None

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

        count_row = await _d1_first(self.env.DB, "SELECT COUNT(*) AS n FROM qrs")
        total = int(count_row["n"]) if count_row and count_row.get("n") is not None else 0

        rows = await _d1_all(
            self.env.DB,
            """
            SELECT q.id, q.full_prefilled_text, q.provisioned_at,
                   s.scanned_at AS last_scanned_at, s.expires_at
            FROM qrs q
            LEFT JOIN scan_sessions s ON s.qr_id = q.id
              AND s.id = (
                SELECT id FROM scan_sessions
                WHERE qr_id = q.id
                ORDER BY scanned_at DESC LIMIT 1
              )
            ORDER BY q.id DESC
            LIMIT ? OFFSET ?
            """,
            limit,
            offset,
        )

        base = _public_base_from_request(request, self.env)
        items: list[dict[str, Any]] = []
        for r in rows:
            qid = int(r["id"])
            items.append(
                {
                    "id": qid,
                    "full_prefilled_text": str(r["full_prefilled_text"]),
                    "redirect_url": f"{base}/r/{qid}",
                    "provisioned_at": int(r["provisioned_at"])
                    if r.get("provisioned_at") is not None
                    else None,
                    "last_scanned_at": int(r["last_scanned_at"])
                    if r.get("last_scanned_at") is not None
                    else None,
                    "expires_at": int(r["expires_at"])
                    if r.get("expires_at") is not None
                    else None,
                }
            )

        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset},
            status=200,
        )

    async def _handle_api_leads_list(self, request, url: str) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        parsed = urlparse(url)
        q = parse_qs(parsed.query or "")

        def _first(key: str) -> str | None:
            vals = q.get(key, [])
            return str(vals[0]).strip() if vals and str(vals[0]).strip() else None

        filter_qr = _first("qr_id")
        filter_phone = _first("from_phone")
        filter_start = _first("start_ts")
        filter_end = _first("end_ts")

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
        bind_vals: list[Any] = []

        if filter_qr:
            try:
                where_parts.append("l.qr_id = ?")
                bind_vals.append(int(filter_qr))
            except ValueError:
                return _json_response({"error": "invalid qr_id"}, status=400)
        if filter_phone:
            where_parts.append("l.from_phone = ?")
            bind_vals.append(filter_phone)
        if filter_start:
            try:
                where_parts.append("l.created_at >= ?")
                bind_vals.append(int(filter_start))
            except ValueError:
                return _json_response({"error": "invalid start_ts"}, status=400)
        if filter_end:
            try:
                where_parts.append("l.created_at <= ?")
                bind_vals.append(int(filter_end))
            except ValueError:
                return _json_response({"error": "invalid end_ts"}, status=400)

        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        count_row = await _d1_first(
            self.env.DB,
            f"SELECT COUNT(*) AS n FROM leads l {where_sql}",
            *bind_vals,
        )
        total = int(count_row["n"]) if count_row else 0

        rows = await _d1_all(
            self.env.DB,
            f"""
            SELECT l.id, l.from_phone, l.wa_display_name, l.qr_id,
                   l.match_method, l.raw_text, l.created_at
            FROM leads l
            {where_sql}
            ORDER BY l.created_at DESC
            LIMIT ? OFFSET ?
            """,
            *bind_vals,
            limit,
            offset,
        )

        items = [
            {
                "id": r["id"],
                "from_phone": r["from_phone"],
                "wa_display_name": r.get("wa_display_name"),
                "qr_id": r.get("qr_id"),
                "match_method": r["match_method"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset}
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
                "name": msg.get("name") or "",
            }
            try:
                await self.env.LEAD_QUEUE.send(to_js(job))
            except Exception:
                return Response("Queue unavailable", status=503)

        return Response(json.dumps({"received": len(messages)}), headers={"content-type": "application/json"})

    async def queue(self, batch, env=None, ctx=None):  # type: ignore[override]
        now_ts = int(time.time())
        min_score = _float_env(self.env, "LCS_MIN_SCORE", 0.35)
        min_gap = _float_env(self.env, "LCS_MIN_GAP", 0.08)
        tau = _float_env(self.env, "LCS_RECENCY_TAU_MINUTES", 60.0)
        max_cand = _int_env(self.env, "LCS_MAX_CANDIDATES", 500)
        require_confidence = _bool_env(self.env, "LCS_REQUIRE_CONFIDENCE", False)
        tie_break = _str_env(self.env, "LCS_TIE_BREAK", "recent").strip().lower()
        prefer_recent_scan_on_tie = tie_break not in ("first", "lru", "oldest")
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
            wa_display_name = str(body.get("name", "")) or None
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
                matched_qr_id: int | None = None
                matched_session_id: int | None = None
                method: str | None = None

                if ref:
                    try:
                        ref_int = int(ref)
                    except ValueError:
                        ref_int = None

                    if ref_int is not None:
                        row = await _d1_first(
                            self.env.DB,
                            "SELECT id FROM qrs WHERE id = ?",
                            ref_int,
                        )
                        if row:
                            matched_qr_id = int(row["id"])
                            method = "ref_id"

                if matched_qr_id is None:
                    rows = await _d1_all(
                        self.env.DB,
                        """
                        SELECT s.id AS session_id, s.qr_id,
                               s.full_text AS full_prefilled_text, s.scanned_at
                        FROM scan_sessions s
                        WHERE s.expires_at > ?
                          AND s.claimed_at IS NULL
                        ORDER BY s.scanned_at DESC
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
                        require_confidence=require_confidence,
                        prefer_recent_scan_on_tie=prefer_recent_scan_on_tie,
                    )
                    if match:
                        matched_qr_id = match.qr_id
                        method = match.method
                        matched_session_id = match.session_id

                if matched_qr_id is not None and method:
                    await _d1_run(
                        self.env.DB,
                        """
                        INSERT INTO leads (whatsapp_message_id, from_phone, wa_display_name, qr_id, match_method, raw_text, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        wa_message_id,
                        from_phone,
                        wa_display_name,
                        matched_qr_id,
                        method,
                        text,
                        now_ts,
                    )
                    await _d1_run(
                        self.env.DB,
                        """
                        UPDATE processed_inbound_messages
                        SET ref_id = ?, match_method = ?
                        WHERE whatsapp_message_id = ?
                        """,
                        str(matched_qr_id),
                        method,
                        wa_message_id,
                    )
                    # Claim the specific session row so it is excluded from future
                    # LCS matching. Each scan now has its own row (id PK), so claiming
                    # one person's session does not affect another person who scanned
                    # the same QR. ref_id matches need no claim.
                    if method == "lcs" and matched_session_id is not None:
                        await _d1_run(
                            self.env.DB,
                            "UPDATE scan_sessions SET claimed_at = ? WHERE id = ?",
                            now_ts,
                            matched_session_id,
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
