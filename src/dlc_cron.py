"""
Weekly driver lead count (DLC) reconciliation into D1 from leads in the window.
"""

from __future__ import annotations

from typing import Any

from dlc_weeks import previous_completed_ist_week_bounds


def _int_env(env: Any, name: str, default: int) -> int:
    raw = getattr(env, name, None)
    if raw is None:
        return default
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return default


async def run_weekly_dlc_for_previous_week(
    db: Any,
    env: Any,
    *,
    now_ts: int,
    d1_first: Any,
    d1_all: Any,
    d1_run: Any,
) -> dict[str, Any]:
    offset_min = _int_env(env, "DLC_WEEK_TZ_OFFSET_MINUTES", 330)
    start_at, end_at, label = previous_completed_ist_week_bounds(now_ts, offset_min)

    row = await d1_first(
        db,
        "SELECT id FROM weeks WHERE start_at = ? AND end_at = ?",
        start_at,
        end_at,
    )
    if row:
        week_id = int(row["id"])
    else:
        await d1_run(
            db,
            "INSERT INTO weeks (start_at, end_at) VALUES (?, ?)",
            start_at,
            end_at,
        )
        row = await d1_first(
            db,
            "SELECT id FROM weeks WHERE start_at = ? AND end_at = ?",
            start_at,
            end_at,
        )
        if not row:
            return {"ok": False, "error": "failed to create week row", "label": label}
        week_id = int(row["id"])

    counts = await d1_all(
        db,
        """
        SELECT ref_id, COUNT(*) AS n
        FROM leads
        WHERE ref_id IS NOT NULL
          AND created_at >= ?
          AND created_at < ?
        GROUP BY ref_id
        """,
        start_at,
        end_at,
    )

    n_rows = 0
    for r in counts:
        rid = r.get("ref_id")
        if rid is None:
            continue
        n = int(r.get("n") or 0)
        await d1_run(
            db,
            """
            INSERT INTO driver_lead_counts (ref_id, week_id, lead_count, computed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ref_id, week_id) DO UPDATE SET
              lead_count = excluded.lead_count,
              computed_at = excluded.computed_at
            """,
            int(rid),
            week_id,
            n,
            now_ts,
        )
        n_rows += 1

    return {
        "ok": True,
        "week_id": week_id,
        "label": label,
        "start_at": start_at,
        "end_at": end_at,
        "ref_rows_updated": n_rows,
    }
