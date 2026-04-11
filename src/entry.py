"""
Cloudflare Python Worker: QR redirect, WhatsApp inbound webhook → queue, consumer matching.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from pyodide.ffi import to_js

from dlc_cron import run_weekly_dlc_for_previous_week
from dlc_increment import increment_dlc_for_lead
from coupon import (
    fetch_coupon_prefix,
    format_coupon_spaced,
    generate_coupon_code,
)
from integration_meta import integration_document
from matching import (
    candidate_from_row,
    extract_ref_id,
    pick_best_match,
)
from prefill import build_prefilled_text
from payload import iter_webhook_inbound_jobs
from scan_sessions_kv import (
    inbound_fallback_claim,
    inbound_fallback_release,
    ss_claim_session,
    ss_load_lcs_candidates,
    ss_merge_index_batch,
    ss_put_session,
)

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


def _extract_multipart_boundary(content_type: str) -> str | None:
    if not content_type:
        return None
    lower = content_type.lower()
    key = "boundary="
    idx = lower.find(key)
    if idx < 0:
        return None
    val = content_type[idx + len(key) :].strip()
    if val.startswith('"'):
        end = val.find('"', 1)
        if end < 0:
            return None
        return val[1:end]
    m = re.match(r"([^;\s]+)", val)
    return m.group(1).strip() if m else None


def _strip_mime_part_trailer(blob: bytes) -> bytes:
    if blob.endswith(b"\r\n"):
        return blob[:-2]
    if blob.endswith(b"\n"):
        return blob[:-1]
    return blob


def _parse_multipart_form_data(body: bytes, boundary: str) -> dict[str, tuple[Any, ...]]:
    """Parse multipart/form-data without request.formData() (Python Workers often break on multipart).

    Each value is ``("text", str)`` or ``("file", bytes, content_type)``.
    """
    if not boundary:
        raise ValueError("missing boundary")
    delim = b"--" + boundary.encode("latin-1", errors="strict")
    segments = body.split(delim)
    out: dict[str, tuple[Any, ...]] = {}
    for seg in segments:
        # Only trim leading CRLF before the first boundary line; do not strip the
        # tail of the part (binary bodies may end with CR/LF bytes).
        seg = seg.lstrip(b"\r\n")
        if not seg or seg == b"--":
            continue
        header_end = seg.find(b"\r\n\r\n")
        sep_len = 4
        if header_end < 0:
            header_end = seg.find(b"\n\n")
            sep_len = 2
        if header_end < 0:
            continue
        header_blob = seg[:header_end].decode("utf-8", errors="replace")
        body_blob = seg[header_end + sep_len :]
        cd_line = ""
        ct_line = "text/plain"
        for line in re.split(r"\r\n|\n", header_blob):
            if not line.strip():
                continue
            low = line.lower()
            if low.startswith("content-disposition:"):
                cd_line = line
            elif low.startswith("content-type:"):
                ct_line = line.split(":", 1)[1].strip()
        if not cd_line:
            continue
        name_m = re.search(r'name\s*=\s*"([^"]*)"', cd_line, re.I)
        if not name_m:
            name_m = re.search(r"name\s*=\s*'([^']*)'", cd_line, re.I)
        if not name_m:
            name_m = re.search(r"name\s*=\s*([^;\s]+)", cd_line, re.I)
        if not name_m:
            continue
        field_name = name_m.group(1).strip().strip('"').strip("'")
        has_file = "filename=" in cd_line.lower()
        if has_file:
            body_blob = _strip_mime_part_trailer(body_blob)
            out[field_name] = (
                "file",
                body_blob,
                ct_line or "application/octet-stream",
            )
        else:
            body_blob = _strip_mime_part_trailer(body_blob)
            out[field_name] = ("text", body_blob.decode("utf-8", errors="replace"))
    return out


def _multipart_text_field(parts: dict[str, tuple[Any, ...]], key: str) -> str:
    v = parts.get(key)
    if v and v[0] == "text":
        return str(v[1]).strip()
    return ""


def _multipart_file_field(
    parts: dict[str, tuple[Any, ...]], key: str
) -> tuple[bytes | None, str]:
    v = parts.get(key)
    if v and v[0] == "file" and len(v) >= 3:
        raw = v[1]
        if not isinstance(raw, (bytes, bytearray)):
            return None, ""
        b = bytes(raw)
        if not b:
            return None, ""
        return b, str(v[2] or "application/octet-stream").strip()
    return None, ""


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
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, OPTIONS",
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


_DEFAULT_COUPON_WA_TEMPLATE = """Here's your coupon — use it at checkout:

*{code}*"""


async def _allocate_unique_coupon_code(
    db: Any,
    prefix: str,
    random_length: int,
    *,
    max_attempts: int = 5,
) -> str:
    for _ in range(max_attempts):
        code = generate_coupon_code(prefix, random_length=random_length)
        row = await _d1_first(
            db,
            "SELECT 1 AS ok FROM leads WHERE coupon_code_sent = ? LIMIT 1",
            code,
        )
        if not row:
            return code
    return generate_coupon_code(prefix, random_length=random_length)


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
        if path == "/api/qrs/available-refs":
            if method == "GET":
                return await self._handle_api_qrs_available_refs(request, url)
            return Response("Method not allowed", status=405)
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

        if path == "/api/drivers":
            if method == "GET":
                return await self._handle_api_drivers_list(request, url)
            if method == "POST":
                return await self._handle_api_drivers_create(request)
            return Response("Method not allowed", status=405)

        if path == "/api/weeks":
            if method == "GET":
                return await self._handle_api_weeks_list(request, url)
            return Response("Method not allowed", status=405)

        if path == "/api/dlc":
            if method == "GET":
                return await self._handle_api_dlc_list(request, url)
            return Response("Method not allowed", status=405)

        if path == "/api/admin/run-dlc":
            if method == "POST":
                return await self._handle_api_admin_run_dlc(request)
            return Response("Method not allowed", status=405)

        if path.startswith("/api/drivers/"):
            return await self._handle_api_drivers_subpath(request, method, path)

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
        ttl = _int_env(self.env, "SCAN_TTL_SECONDS", 21600)
        expires_at = now + ttl
        session_id = uuid.uuid4().hex

        await ss_put_session(
            self.env.SCAN_KV,
            session_id=session_id,
            qr_id=qr_id,
            full_text=full_text,
            scanned_at=now,
            expires_at=expires_at,
            ttl_seconds=ttl,
        )
        try:
            await self.env.SESSION_INDEX_QUEUE.send(
                to_js(
                    {
                        "_kind": "session_index",
                        "op": "add",
                        "id": session_id,
                        "scanned_at": now,
                        "expires_at": expires_at,
                    }
                )
            )
        except Exception:
            return Response("Session index queue unavailable", status=503)

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
                    "ref_id": new_id,
                    "full_prefilled_text": full_text,
                    "redirect_url": f"{base}/r/{new_id}",
                    "provisioned_at": now,
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
            SELECT q.id, q.full_prefilled_text, q.provisioned_at
            FROM qrs q
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
                    "ref_id": qid,
                    "full_prefilled_text": str(r["full_prefilled_text"]),
                    "redirect_url": f"{base}/r/{qid}",
                    "provisioned_at": int(r["provisioned_at"])
                    if r.get("provisioned_at") is not None
                    else None,
                }
            )

        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset},
            status=200,
        )

    async def _handle_api_qrs_available_refs(self, request, url: str) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        parsed = urlparse(url)
        q = parse_qs(parsed.query or "")

        def _first(key: str) -> str | None:
            vals = q.get(key, [])
            return str(vals[0]).strip() if vals and str(vals[0]).strip() else None

        max_limit = _int_env(self.env, "ADMIN_AVAILABLE_REFS_MAX_LIMIT", 5000)
        try:
            limit = int(_first("limit") or str(max_limit))
        except ValueError:
            return _json_response({"error": "invalid limit"}, status=400)
        try:
            offset = int(_first("offset") or "0")
        except ValueError:
            return _json_response({"error": "invalid offset"}, status=400)

        if limit < 1 or limit > max_limit:
            return _json_response(
                {"error": f"limit must be between 1 and {max_limit}"},
                status=400,
            )
        if offset < 0:
            return _json_response({"error": "offset must be >= 0"}, status=400)

        fetch_n = limit + 1
        rows = await _d1_all(
            self.env.DB,
            """
            SELECT q.id
            FROM qrs q
            LEFT JOIN drivers d ON d.qr_ref_id = q.id
            WHERE d.id IS NULL
            ORDER BY q.id ASC
            LIMIT ? OFFSET ?
            """,
            fetch_n,
            offset,
        )
        has_more = len(rows) > limit
        ref_ids = [int(r["id"]) for r in rows[:limit]]
        return _json_response(
            {
                "ref_ids": ref_ids,
                "has_more": has_more,
                "limit": limit,
                "offset": offset,
            }
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

        filter_ref = _first("ref_id") or _first("qr_id")
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

        if filter_ref:
            try:
                where_parts.append("l.ref_id = ?")
                bind_vals.append(int(filter_ref))
            except ValueError:
                return _json_response({"error": "invalid ref_id"}, status=400)
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
            SELECT l.id, l.from_phone, l.wa_display_name, l.ref_id,
                   l.match_method, l.raw_text, l.created_at,
                   l.coupon_code_sent
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
                "ref_id": r.get("ref_id"),
                "match_method": r["match_method"],
                "created_at": r["created_at"],
                "coupon_code_sent": r.get("coupon_code_sent"),
            }
            for r in rows
        ]

        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset}
        )

    def _r2_object_public_url(self, key: str) -> str:
        base = _str_env(self.env, "R2_PUBLIC_BASE", "").rstrip("/")
        if base:
            return f"{base}/{key}"
        return key

    async def _request_body_bytes(self, request: Any) -> bytes:
        """Read raw POST body. Prefer workers.Request.bytes(); avoid arrayBuffer() (not on Python Request)."""
        b_get = getattr(request, "bytes", None)
        if callable(b_get):
            raw = await b_get()
            if isinstance(raw, (bytes, bytearray)):
                return bytes(raw)
        buf_get = getattr(request, "buffer", None)
        if callable(buf_get):
            ab = await buf_get()
            if hasattr(ab, "to_bytes"):
                return ab.to_bytes()
            return bytes(ab)
        ab = await request.arrayBuffer()
        if hasattr(ab, "to_bytes"):
            return ab.to_bytes()
        return bytes(ab)

    async def _r2_put_bytes(
        self, bucket: Any, key: str, body: bytes, content_type: str
    ) -> None:
        """R2 ``put`` expects Blob/ArrayBufferView in Workers; plain Python bytes often fail."""
        try:
            from workers import Blob
        except ImportError:
            ct = (content_type or "").strip() or "application/octet-stream"
            await bucket.put(
                key,
                bytes(body),
                {"httpMetadata": {"contentType": ct}},
            )
            return
        ct = (content_type or "").strip() or "application/octet-stream"
        blob = Blob([bytes(body)], content_type=ct)
        await bucket.put(
            key,
            blob.js_object,
            {"httpMetadata": {"contentType": ct}},
        )

    @staticmethod
    def _parse_identity_urls_json(raw: Any) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw if x]
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except json.JSONDecodeError:
            pass
        return []

    @staticmethod
    def _driver_assets_satisfied(upi_url: Any, identity_raw: Any) -> bool:
        if not upi_url or not str(upi_url).strip():
            return False
        urls = Default._parse_identity_urls_json(identity_raw)
        return len(urls) > 0

    @staticmethod
    def _image_ext_from_content_type(ct: str) -> str:
        c = (ct or "").lower()
        if "png" in c:
            return "png"
        if "jpeg" in c or "jpg" in c:
            return "jpg"
        if "webp" in c:
            return "webp"
        if "pdf" in c:
            return "pdf"
        return "bin"

    async def _form_upload_bytes(self, part: Any) -> tuple[bytes | None, str]:
        if part is None:
            return None, ""
        if isinstance(part, str):
            return None, ""
        try:
            ab = await part.arrayBuffer()
        except Exception:
            return None, ""
        if hasattr(ab, "to_bytes"):
            raw = ab.to_bytes()
        else:
            raw = bytes(ab)
        if not raw:
            return None, ""
        ct = ""
        try:
            ct = str(getattr(part, "type", None) or "").strip()
        except Exception:
            pass
        return raw, ct or "application/octet-stream"

    @staticmethod
    def _canonical_driver_code(driver_id: int, stored: Any) -> str:
        s = str(stored).strip() if stored is not None else ""
        return s if s else f"D{int(driver_id)}"

    async def _handle_api_drivers_list(self, request, url: str) -> Response:
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

        count_row = await _d1_first(self.env.DB, "SELECT COUNT(*) AS n FROM drivers")
        total = int(count_row["n"]) if count_row else 0

        rows = await _d1_all(
            self.env.DB,
            """
            SELECT id, driver_code, name, phone, qr_ref_id,
                   qr_asset_url, upi_qr_asset_url, identity_asset_urls, created_at
            FROM drivers
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            limit,
            offset,
        )

        items = []
        for r in rows:
            did = int(r["id"])
            code = self._canonical_driver_code(did, r.get("driver_code"))
            items.append(
                {
                    "id": did,
                    "driver_code": code,
                    "driver_id": code,
                    "name": r["name"],
                    "phone": r["phone"],
                    "qr_ref_id": int(r["qr_ref_id"])
                    if r.get("qr_ref_id") is not None
                    else None,
                    "qr_asset_url": r.get("qr_asset_url"),
                    "upi_qr_asset_url": r.get("upi_qr_asset_url"),
                    "identity_asset_urls": self._parse_identity_urls_json(
                        r.get("identity_asset_urls")
                    ),
                    "created_at": int(r["created_at"])
                    if r.get("created_at") is not None
                    else None,
                }
            )

        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset}
        )

    async def _handle_api_drivers_create(self, request) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        ct_hdr = (_header_get(request.headers, "Content-Type") or "").lower()
        if "multipart/form-data" not in ct_hdr:
            return _json_response(
                {
                    "error": (
                        "use multipart/form-data with fields: name, phone, qr_ref_id, "
                        "and file fields upi_qr, identity"
                    )
                },
                status=415,
            )

        full_ct = _header_get(request.headers, "Content-Type") or ""
        boundary = _extract_multipart_boundary(full_ct)
        if not boundary:
            return _json_response({"error": "multipart boundary missing"}, status=400)

        try:
            raw_body = await self._request_body_bytes(request)
            parts = _parse_multipart_form_data(raw_body, boundary)
        except Exception:
            return _json_response({"error": "invalid multipart body"}, status=400)

        name = _multipart_text_field(parts, "name")
        phone = _multipart_text_field(parts, "phone")
        if not name or not phone:
            return _json_response({"error": "name and phone are required"}, status=400)

        qr_ref_raw = _multipart_text_field(parts, "qr_ref_id")
        if not qr_ref_raw:
            return _json_response({"error": "qr_ref_id is required"}, status=400)
        try:
            qr_ref_id = int(qr_ref_raw)
        except ValueError:
            return _json_response({"error": "invalid qr_ref_id"}, status=400)
        qrow = await _d1_first(
            self.env.DB, "SELECT id FROM qrs WHERE id = ?", qr_ref_id
        )
        if not qrow:
            return _json_response({"error": "qr_ref_id not found in qrs"}, status=400)
        taken = await _d1_first(
            self.env.DB, "SELECT id FROM drivers WHERE qr_ref_id = ?", qr_ref_id
        )
        if taken:
            return _json_response(
                {"error": "qr_ref_id already assigned to another driver"},
                status=409,
            )

        bucket = getattr(self.env, "DRIVER_ASSETS", None)
        if bucket is None:
            return _json_response({"error": "R2 not configured"}, status=503)

        upi_body, upi_ct = _multipart_file_field(parts, "upi_qr")
        id_body, id_ct = _multipart_file_field(parts, "identity")
        if not upi_body:
            return _json_response({"error": "upi_qr file is required"}, status=400)
        if not id_body:
            return _json_response(
                {"error": "identity proof file is required"}, status=400
            )

        now = int(time.time())
        did = await _d1_last_insert_rowid(
            self.env.DB,
            """
            INSERT INTO drivers (name, phone, created_at)
            VALUES (?, ?, ?)
            """,
            name,
            phone,
            now,
        )
        if did is None:
            return _json_response({"error": "failed to create driver"}, status=500)

        try:
            upi_ext = self._image_ext_from_content_type(upi_ct)
            id_ext = self._image_ext_from_content_type(id_ct)
            upi_key = f"drivers/{did}/upi-qr.{upi_ext}"
            id_uid = uuid.uuid4().hex[:12]
            id_key = f"drivers/{did}/id-{id_uid}.{id_ext}"
            await self._r2_put_bytes(bucket, upi_key, upi_body, upi_ct)
            await self._r2_put_bytes(bucket, id_key, id_body, id_ct)
            upi_url = self._r2_object_public_url(upi_key)
            id_url = self._r2_object_public_url(id_key)
            ident_json = json.dumps([id_url])
            auto_code = f"D{did}"
            await _d1_run(
                self.env.DB,
                """
                UPDATE drivers
                SET upi_qr_asset_url = ?, identity_asset_urls = ?,
                    driver_code = ?, qr_ref_id = ?
                WHERE id = ?
                """,
                upi_url,
                ident_json,
                auto_code,
                qr_ref_id,
                did,
            )
        except Exception:
            await _d1_run(self.env.DB, "DELETE FROM drivers WHERE id = ?", did)
            return _json_response({"error": "failed to store driver assets"}, status=500)

        return _json_response(
            {
                "id": did,
                "driver_code": auto_code,
                "name": name,
                "phone": phone,
                "qr_ref_id": qr_ref_id,
                "upi_qr_asset_url": upi_url,
                "identity_asset_urls": [id_url],
                "created_at": now,
            },
            status=201,
        )

    async def _handle_api_drivers_patch(self, request, driver_id: int) -> Response:
        body_text = await request.text()
        try:
            payload = json.loads(body_text) if body_text.strip() else {}
        except json.JSONDecodeError:
            return _json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(payload, dict):
            return _json_response({"error": "body must be a JSON object"}, status=400)

        cur = await _d1_first(
            self.env.DB,
            """
            SELECT id, qr_ref_id, qr_asset_url, upi_qr_asset_url, identity_asset_urls
            FROM drivers WHERE id = ?
            """,
            driver_id,
        )
        if not cur:
            return _json_response({"error": "not found"}, status=404)

        merged_upi = cur.get("upi_qr_asset_url")
        merged_ident = cur.get("identity_asset_urls")
        if "upi_qr_asset_url" in payload:
            v = payload.get("upi_qr_asset_url")
            merged_upi = None if v is None else str(v).strip() or None
        if "identity_asset_urls" in payload:
            v = payload.get("identity_asset_urls")
            if v is None:
                merged_ident = None
            elif isinstance(v, list):
                merged_ident = json.dumps([str(x) for x in v if x])
            else:
                return _json_response({"error": "identity_asset_urls must be a list"}, status=400)
        if not self._driver_assets_satisfied(merged_upi, merged_ident):
            return _json_response(
                {
                    "error": (
                        "driver must keep upi qr and at least one identity proof URL"
                    )
                },
                status=400,
            )

        sets: list[str] = []
        vals: list[Any] = []
        if "name" in payload:
            sets.append("name = ?")
            vals.append(str(payload.get("name") or "").strip())
        if "phone" in payload:
            sets.append("phone = ?")
            vals.append(str(payload.get("phone") or "").strip())
        if "qr_ref_id" in payload:
            v = payload.get("qr_ref_id")
            if v is None:
                sets.append("qr_ref_id = ?")
                vals.append(None)
            else:
                try:
                    qrid = int(v)
                except (TypeError, ValueError):
                    return _json_response({"error": "invalid qr_ref_id"}, status=400)
                qrow = await _d1_first(
                    self.env.DB, "SELECT id FROM qrs WHERE id = ?", qrid
                )
                if not qrow:
                    return _json_response({"error": "qr_ref_id not found in qrs"}, status=400)
                taken = await _d1_first(
                    self.env.DB,
                    "SELECT id FROM drivers WHERE qr_ref_id = ? AND id != ?",
                    qrid,
                    driver_id,
                )
                if taken:
                    return _json_response(
                        {
                            "error": "qr_ref_id already assigned to another driver",
                        },
                        status=409,
                    )
                sets.append("qr_ref_id = ?")
                vals.append(qrid)
        if "qr_asset_url" in payload:
            sets.append("qr_asset_url = ?")
            v = payload.get("qr_asset_url")
            vals.append(None if v is None else str(v).strip() or None)
        if "identity_asset_urls" in payload:
            v = payload.get("identity_asset_urls")
            if v is None:
                sets.append("identity_asset_urls = ?")
                vals.append(None)
            elif isinstance(v, list):
                sets.append("identity_asset_urls = ?")
                vals.append(json.dumps([str(x) for x in v if x]))
            else:
                return _json_response({"error": "identity_asset_urls must be a list"}, status=400)
        if "upi_qr_asset_url" in payload:
            v = payload.get("upi_qr_asset_url")
            sets.append("upi_qr_asset_url = ?")
            vals.append(None if v is None else str(v).strip() or None)

        if not sets:
            return _json_response({"error": "no fields to update"}, status=400)

        sql = "UPDATE drivers SET " + ", ".join(sets) + " WHERE id = ?"
        vals.append(driver_id)
        await _d1_run(self.env.DB, sql, *vals)
        return _json_response({"ok": True, "id": driver_id})

    async def _handle_driver_qr_image_put(self, request, driver_id: int) -> Response:
        bucket = getattr(self.env, "DRIVER_ASSETS", None)
        if bucket is None:
            return _json_response({"error": "R2 not configured"}, status=503)

        row = await _d1_first(
            self.env.DB, "SELECT id FROM drivers WHERE id = ?", driver_id
        )
        if not row:
            return _json_response({"error": "not found"}, status=404)

        ct = _header_get(request.headers, "Content-Type") or "application/octet-stream"
        body = await self._request_body_bytes(request)
        if not body:
            return _json_response({"error": "empty body"}, status=400)

        ext = "bin"
        if "png" in ct.lower():
            ext = "png"
        elif "jpeg" in ct.lower() or "jpg" in ct.lower():
            ext = "jpg"
        elif "webp" in ct.lower():
            ext = "webp"
        key = f"drivers/{driver_id}/qr.{ext}"
        await self._r2_put_bytes(bucket, key, body, ct)
        url = self._r2_object_public_url(key)
        await _d1_run(
            self.env.DB,
            "UPDATE drivers SET qr_asset_url = ? WHERE id = ?",
            url,
            driver_id,
        )
        return _json_response({"ok": True, "qr_asset_url": url, "key": key})

    async def _handle_driver_upi_qr_image_put(self, request, driver_id: int) -> Response:
        bucket = getattr(self.env, "DRIVER_ASSETS", None)
        if bucket is None:
            return _json_response({"error": "R2 not configured"}, status=503)

        row = await _d1_first(
            self.env.DB, "SELECT id FROM drivers WHERE id = ?", driver_id
        )
        if not row:
            return _json_response({"error": "not found"}, status=404)

        ct = _header_get(request.headers, "Content-Type") or "application/octet-stream"
        body = await self._request_body_bytes(request)
        if not body:
            return _json_response({"error": "empty body"}, status=400)

        ext = "bin"
        if "png" in ct.lower():
            ext = "png"
        elif "jpeg" in ct.lower() or "jpg" in ct.lower():
            ext = "jpg"
        elif "webp" in ct.lower():
            ext = "webp"
        key = f"drivers/{driver_id}/upi-qr.{ext}"
        await self._r2_put_bytes(bucket, key, body, ct)
        url = self._r2_object_public_url(key)
        await _d1_run(
            self.env.DB,
            "UPDATE drivers SET upi_qr_asset_url = ? WHERE id = ?",
            url,
            driver_id,
        )
        return _json_response({"ok": True, "upi_qr_asset_url": url, "key": key})

    async def _handle_driver_identity_image_put(self, request, driver_id: int) -> Response:
        bucket = getattr(self.env, "DRIVER_ASSETS", None)
        if bucket is None:
            return _json_response({"error": "R2 not configured"}, status=503)

        row = await _d1_first(
            self.env.DB,
            "SELECT identity_asset_urls FROM drivers WHERE id = ?",
            driver_id,
        )
        if not row:
            return _json_response({"error": "not found"}, status=404)

        ct = _header_get(request.headers, "Content-Type") or "application/octet-stream"
        body = await self._request_body_bytes(request)
        if not body:
            return _json_response({"error": "empty body"}, status=400)

        ext = "bin"
        if "png" in ct.lower():
            ext = "png"
        elif "jpeg" in ct.lower() or "jpg" in ct.lower():
            ext = "jpg"
        elif "pdf" in ct.lower():
            ext = "pdf"

        uid = uuid.uuid4().hex[:12]
        key = f"drivers/{driver_id}/id-{uid}.{ext}"
        await self._r2_put_bytes(bucket, key, body, ct)
        url = self._r2_object_public_url(key)
        urls = self._parse_identity_urls_json(row.get("identity_asset_urls"))
        urls.append(url)
        await _d1_run(
            self.env.DB,
            "UPDATE drivers SET identity_asset_urls = ? WHERE id = ?",
            json.dumps(urls),
            driver_id,
        )
        return _json_response(
            {"ok": True, "identity_asset_urls": urls, "added": url, "key": key}
        )

    async def _handle_api_drivers_subpath(
        self, request, method: str, path: str
    ) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        rest = path.removeprefix("/api/drivers/").strip("/")
        if not rest:
            return Response("Not found", status=404)
        parts = rest.split("/")
        try:
            did = int(parts[0])
        except ValueError:
            return _json_response({"error": "invalid driver id"}, status=400)

        if len(parts) == 1:
            if method == "PATCH":
                return await self._handle_api_drivers_patch(request, did)
            return Response("Method not allowed", status=405)

        if len(parts) == 2 and parts[1] == "qr-image":
            if method == "PUT":
                return await self._handle_driver_qr_image_put(request, did)
            return Response("Method not allowed", status=405)

        if len(parts) == 2 and parts[1] == "upi-qr-image":
            if method == "PUT":
                return await self._handle_driver_upi_qr_image_put(request, did)
            return Response("Method not allowed", status=405)

        if len(parts) == 2 and parts[1] == "identity-image":
            if method == "PUT":
                return await self._handle_driver_identity_image_put(request, did)
            return Response("Method not allowed", status=405)

        return Response("Not found", status=404)

    async def _handle_api_weeks_list(self, request, url: str) -> Response:
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

        count_row = await _d1_first(self.env.DB, "SELECT COUNT(*) AS n FROM weeks")
        total = int(count_row["n"]) if count_row else 0

        rows = await _d1_all(
            self.env.DB,
            """
            SELECT id, start_at, end_at FROM weeks
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            limit,
            offset,
        )

        items = [
            {
                "id": int(r["id"]),
                "start_at": int(r["start_at"]),
                "end_at": int(r["end_at"]),
            }
            for r in rows
        ]
        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset}
        )

    async def _handle_api_dlc_list(self, request, url: str) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        parsed = urlparse(url)
        q = parse_qs(parsed.query or "")

        def _first(key: str) -> str | None:
            vals = q.get(key, [])
            return str(vals[0]).strip() if vals and str(vals[0]).strip() else None

        week_id_raw = _first("week_id")
        try:
            limit = int(_first("limit") or "200")
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

        where_sql = ""
        bind: list[Any] = []
        if week_id_raw:
            try:
                where_sql = "WHERE d.week_id = ?"
                bind.append(int(week_id_raw))
            except ValueError:
                return _json_response({"error": "invalid week_id"}, status=400)

        count_row = await _d1_first(
            self.env.DB,
            f"SELECT COUNT(*) AS n FROM driver_lead_counts d {where_sql}",
            *bind,
        )
        total = int(count_row["n"]) if count_row else 0

        rows = await _d1_all(
            self.env.DB,
            f"""
            SELECT d.id, d.ref_id, d.week_id, d.lead_count, d.computed_at,
                   w.start_at, w.end_at
            FROM driver_lead_counts d
            JOIN weeks w ON w.id = d.week_id
            {where_sql}
            ORDER BY d.week_id DESC, d.ref_id ASC
            LIMIT ? OFFSET ?
            """,
            *bind,
            limit,
            offset,
        )

        items = [
            {
                "id": int(r["id"]),
                "ref_id": int(r["ref_id"]),
                "week_id": int(r["week_id"]),
                "lead_count": int(r["lead_count"]),
                "computed_at": int(r["computed_at"]),
                "week_start_at": int(r["start_at"]),
                "week_end_at": int(r["end_at"]),
            }
            for r in rows
        ]
        return _json_response(
            {"items": items, "total": total, "limit": limit, "offset": offset}
        )

    async def _handle_api_admin_run_dlc(self, request) -> Response:
        bad = _admin_api_check(request, self.env)
        if bad is not None:
            return bad

        now_ts = int(time.time())
        result = await run_weekly_dlc_for_previous_week(
            self.env.DB,
            self.env,
            now_ts=now_ts,
            d1_first=_d1_first,
            d1_all=_d1_all,
            d1_run=_d1_run,
        )
        return _json_response(result, status=200 if result.get("ok") else 500)

    async def scheduled(self, *args, **kwargs):  # type: ignore[override]
        now_ts = int(time.time())
        await run_weekly_dlc_for_previous_week(
            self.env.DB,
            self.env,
            now_ts=now_ts,
            d1_first=_d1_first,
            d1_all=_d1_all,
            d1_run=_d1_run,
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

        # Session index queue: merge all adds in one KV write.
        if batch.messages:
            first = batch.messages[0].body
            if hasattr(first, "to_py"):
                py0 = first.to_py()
                first = py0 if isinstance(py0, dict) else {}
            if isinstance(first, dict) and first.get("_kind") == "session_index":
                adds: list[dict[str, Any]] = []
                for message in batch.messages:
                    body = message.body
                    if hasattr(body, "to_py"):
                        py = body.to_py()
                        body = py if isinstance(py, dict) else {}
                    if isinstance(body, dict):
                        adds.append(body)
                await ss_merge_index_batch(self.env.SCAN_KV, adds)
                for message in batch.messages:
                    message.ack()
                return

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

            try:
                ref = extract_ref_id(text)
                matched_qr_id: int | None = None
                matched_session_id: str | None = None
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
                    raw_rows = await ss_load_lcs_candidates(
                        self.env.SCAN_KV,
                        now_ts=now_ts,
                        max_candidates=max_cand,
                    )
                    candidates = [candidate_from_row(r) for r in raw_rows]
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
                    coupon_prefix = fetch_coupon_prefix(self.env)
                    rand_len = _int_env(self.env, "COUPON_RANDOM_LENGTH", 6)
                    changes = await _d1_run_changes(
                        self.env.DB,
                        """
                        INSERT OR IGNORE INTO leads (
                          whatsapp_message_id, from_phone, wa_display_name, ref_id,
                          match_method, raw_text, created_at
                        )
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
                    row = await _d1_first(
                        self.env.DB,
                        """
                        SELECT id, coupon_code_sent FROM leads
                        WHERE whatsapp_message_id = ?
                        """,
                        wa_message_id,
                    )
                    if not row:
                        message.ack()
                        continue
                    lead_id = int(row["id"])
                    if changes > 0:
                        await increment_dlc_for_lead(
                            self.env.DB,
                            self.env,
                            ref_id=matched_qr_id,
                            created_at=now_ts,
                            d1_first=_d1_first,
                            d1_run=_d1_run,
                        )
                    coupon_sent = row.get("coupon_code_sent")
                    if not coupon_sent:
                        code = (
                            await _allocate_unique_coupon_code(
                                self.env.DB, coupon_prefix, rand_len
                            )
                            if lead_id
                            else ""
                        )
                        if code:
                            tpl = (
                                _str_env(self.env, "COUPON_WHATSAPP_TEMPLATE", "").strip()
                                or _str_env(
                                    self.env,
                                    "PROMO_WHATSAPP_TEMPLATE",
                                    "",
                                ).strip()
                                or _DEFAULT_COUPON_WA_TEMPLATE
                            )
                            spaced = format_coupon_spaced(code)
                            sent = await self._send_whatsapp_session_text(
                                from_phone,
                                tpl.format(code=code, code_spaced=spaced),
                            )
                            if sent:
                                await _d1_run(
                                    self.env.DB,
                                    """
                                    UPDATE leads SET coupon_code_sent = ?
                                    WHERE id = ? AND (coupon_code_sent IS NULL OR coupon_code_sent = '')
                                    """,
                                    code,
                                    lead_id,
                                )
                    if method == "lcs" and matched_session_id is not None:
                        await ss_claim_session(
                            self.env.SCAN_KV, matched_session_id, now_ts
                        )
                else:
                    if not await inbound_fallback_claim(
                        self.env.SCAN_KV, wa_message_id
                    ):
                        message.ack()
                        continue
                    try:
                        sent = await self._send_whatsapp_session_text(
                            from_phone, fallback_text
                        )
                        if not sent:
                            await inbound_fallback_release(
                                self.env.SCAN_KV, wa_message_id
                            )
                    except Exception:
                        await inbound_fallback_release(
                            self.env.SCAN_KV, wa_message_id
                        )
                        raise

            except Exception:
                raise

            message.ack()

    async def _send_whatsapp_session_text(self, to_phone: str, body: str) -> bool:
        """Send WhatsApp session text via MSG91.

        Returns True if the HTTP request succeeded. Returns False when MSG91
        credentials are missing (nothing was sent). Raises on network/HTTP
        failure so the queue consumer can retry.
        """
        authkey = _str_env(self.env, "MSG91_AUTH_KEY", "")
        integrated = _str_env(self.env, "MSG91_INTEGRATED_NUMBER", "")
        if not authkey or not integrated:
            return False
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
        resp = await fetch(
            send_url,
            to_js(
                {
                    "method": "POST",
                    "headers": headers,
                    "body": json.dumps(payload),
                }
            ),
        )
        ok = bool(getattr(resp, "ok", False))
        if not ok:
            status = int(getattr(resp, "status", 0) or 0)
            detail = ""
            text_fn = getattr(resp, "text", None)
            if callable(text_fn):
                try:
                    t = await text_fn()
                    if t is not None:
                        detail = str(t)[:500]
                except Exception:
                    detail = ""
            raise RuntimeError(f"MSG91 session message failed: HTTP {status} {detail}")
        return True
