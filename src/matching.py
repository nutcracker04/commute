"""
Pure-Python text normalization, #RefID extraction, and LCS-based fuzzy matching.
Safe to test locally without Workers bindings.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

REF_ID_PATTERN = re.compile(r"#RefID:\s*(\S+)", re.IGNORECASE)


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    out: list[str] = []
    for ch in s:
        cat = unicodedata.category(ch)
        # Drop most symbols that behave like emoji / decorative symbols
        if cat in ("So", "Sk"):
            continue
        out.append(ch)
    s = "".join(out)
    s = " ".join(s.split())
    return s.strip()


def extract_ref_id(text: str) -> str | None:
    if not text:
        return None
    m = REF_ID_PATTERN.search(text)
    return m.group(1) if m else None


def lcs_length(a: str, b: str) -> int:
    """Length of longest common subsequence (classic O(n*m) DP)."""
    if not a or not b:
        return 0
    n, m = len(a), len(b)
    prev = [0] * (m + 1)
    for i in range(1, n + 1):
        cur = [0] * (m + 1)
        ai = a[i - 1]
        for j in range(1, m + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
            else:
                cur[j] = max(prev[j], cur[j - 1])
        prev = cur
    return prev[m]


@dataclass
class MatchCandidate:
    qr_id: int
    full_prefilled_text: str
    anchor_at: int  # unix seconds; scan_sessions.scanned_at


@dataclass
class MatchResult:
    qr_id: int
    final_score: float
    raw_score: float
    method: str  # "lcs"


def pick_best_match(
    user_text: str,
    candidates: list[MatchCandidate],
    *,
    now_ts: int,
    min_score: float = 0.35,
    min_gap: float = 0.08,
    tau_minutes: float = 60.0,
) -> MatchResult | None:
    if not candidates:
        return None
    nu = normalize_text(user_text)
    if not nu:
        return None

    scored: list[tuple[float, float, MatchCandidate]] = []
    for c in candidates:
        ns = normalize_text(c.full_prefilled_text)
        if not ns:
            continue
        lcs = lcs_length(nu, ns)
        raw = lcs / max(len(ns), 1)
        age_min = max(0.0, (now_ts - c.anchor_at) / 60.0)
        final = raw * math.exp(-age_min / max(tau_minutes, 1e-6))
        scored.append((final, raw, c))

    if not scored:
        return None

    scored.sort(key=lambda t: t[0], reverse=True)
    best_final, best_raw, best_c = scored[0]
    second_final = scored[1][0] if len(scored) > 1 else 0.0

    if best_final < min_score:
        return None
    if best_final - second_final < min_gap:
        return None

    return MatchResult(
        qr_id=best_c.qr_id,
        final_score=best_final,
        raw_score=best_raw,
        method="lcs",
    )


def candidate_from_row(row: dict[str, Any]) -> MatchCandidate:
    anchor = row.get("scanned_at")
    if anchor is None:
        anchor = row.get("match_anchor_at")
    if anchor is None:
        anchor = row.get("created_at")
    if anchor is None:
        raise KeyError("row must include scanned_at, match_anchor_at, or created_at")
    return MatchCandidate(
        qr_id=int(row["qr_id"]),
        full_prefilled_text=str(row["full_prefilled_text"]),
        anchor_at=int(anchor),
    )
