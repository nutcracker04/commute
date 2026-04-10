"""Increment driver_lead_counts when a new lead is inserted (per ref_id × week)."""

from __future__ import annotations

from typing import Any

from dlc_weeks import week_bounds_containing_ts


def _int_env(env: Any, name: str, default: int) -> int:
    raw = getattr(env, name, None)
    if raw is None:
        return default
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return default


async def ensure_week_row_for_ts(
    db: Any,
    env: Any,
    ts: int,
    d1_first: Any,
    d1_run: Any,
) -> int | None:
    offset_min = _int_env(env, "DLC_WEEK_TZ_OFFSET_MINUTES", 330)
    start_at, end_at, _ = week_bounds_containing_ts(ts, offset_min)
    await d1_run(
        db,
        "INSERT OR IGNORE INTO weeks (start_at, end_at) VALUES (?, ?)",
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
        return None
    return int(row["id"])


async def increment_dlc_for_lead(
    db: Any,
    env: Any,
    *,
    ref_id: int,
    created_at: int,
    d1_first: Any,
    d1_run: Any,
) -> None:
    week_id = await ensure_week_row_for_ts(db, env, created_at, d1_first, d1_run)
    if week_id is None:
        return
    await d1_run(
        db,
        """
        INSERT INTO driver_lead_counts (ref_id, week_id, lead_count, computed_at)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(ref_id, week_id) DO UPDATE SET
          lead_count = lead_count + 1,
          computed_at = excluded.computed_at
        """,
        ref_id,
        week_id,
        created_at,
    )
