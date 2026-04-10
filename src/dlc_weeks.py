"""
IST-aligned (or configurable offset) Monday 00:00 week boundaries for DLC.
Shared by live increment and weekly reconciliation cron.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def week_bounds_containing_ts(ts: int, offset_minutes: int) -> tuple[int, int, str]:
    """
    Half-open [start_at, end_at) for the local calendar week containing unix `ts`.
    Week starts Monday 00:00 in (UTC + offset_minutes).
    """
    offset = timedelta(minutes=offset_minutes)
    tz = timezone(offset)
    t = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)
    days = t.weekday()
    week_start = (t - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=7)
    start_at = int(week_start.timestamp())
    end_at = int(week_end.timestamp())
    label = week_start.strftime("%Y-%m-%d")
    return start_at, end_at, label


def previous_completed_ist_week_bounds(
    now_ts: int, offset_minutes: int
) -> tuple[int, int, str]:
    """
    Half-open [start_at, end_at) for the prior Mon 00:00 — Mon 00:00 week
    (the week that ended at this week's Monday 00:00 local).
    Used by Sunday cron to aggregate the just-finished commission week.
    """
    offset = timedelta(minutes=offset_minutes)
    tz = timezone(offset)
    now = datetime.fromtimestamp(now_ts, tz=timezone.utc).astimezone(tz)
    days = now.weekday()
    this_week_mon = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    prev_week_mon = this_week_mon - timedelta(days=7)
    start_at = int(prev_week_mon.timestamp())
    end_at = int(this_week_mon.timestamp())
    label = prev_week_mon.strftime("%Y-%m-%d")
    return start_at, end_at, label
