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

# Digits only: avoids "#RefID:12." where \S+ captured "12." and int() failed → silent LCS fallback
REF_ID_PATTERN = re.compile(r"#RefID:\s*(\d+)", re.IGNORECASE)
REF_SUFFIX_PATTERN = re.compile(r"#RefID:\s*\d+", re.IGNORECASE)

# Extra weight for greeting / lead-in match so near-identical bodies (same offer line)
# don't all tie and pick the wrong QR by scan recency alone.
GREET_ALIGN_WEIGHT = 0.08
# How well the template's context line (between "!" and ",") appears in the message;
# helps when greeting + #RefID are stripped but "I saw the offer" vs "I came across…" remains.
CONTEXT_ALIGN_WEIGHT = 0.12
# Match on the request clause (after first ",") — differs per QR via REQUEST_VARIANTS.
REQUEST_ALIGN_WEIGHT = 0.12
# Recency bonus: session scanned moments ago scores higher than one scanned hours ago.
# Uses the same exponential decay as `final` (tau_minutes). Never drops a lead — only
# breaks ties more accurately between candidates with similar text scores.
RECENCY_BONUS_WEIGHT = 0.10


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


def strip_ref_suffix(text: str) -> str:
    """Remove trailing #RefID:N so LCS compares message bodies only."""
    if not text:
        return ""
    return REF_SUFFIX_PATTERN.sub("", text).strip()


def _leading_phrase_normalized(text: str) -> str:
    """First exclamation phrase (e.g. 'hello!') or, if none, text before first comma."""
    t = strip_ref_suffix(text).strip()
    if not t:
        return ""
    bang = t.find("!")
    if bang != -1:
        return normalize_text(t[: bang + 1])
    comma = t.find(",")
    frag = t[:comma].strip() if comma != -1 else t[:48]
    return normalize_text(frag)


def greeting_alignment_score(user_text: str, candidate_full_text: str) -> float:
    """How well the opening of the message matches the template (0..2)."""
    pu = _leading_phrase_normalized(user_text)
    pc = _leading_phrase_normalized(candidate_full_text)
    if not pu or not pc:
        return 0.0
    if pu == pc:
        return 2.0
    if pu.startswith(pc) or pc.startswith(pu):
        return 1.0
    if pu in pc or pc in pu:
        return 0.5
    return 0.0


def context_middle_normalized(text: str) -> str:
    """Context fragment: after first '!', up to first ',' (prefill shape ``{g} {c}, {r}``)."""
    t = strip_ref_suffix(text).strip()
    if not t:
        return ""
    bang = t.find("!")
    after = t[bang + 1 :].strip() if bang != -1 else t
    comma = after.find(",")
    mid = after[:comma].strip() if comma != -1 else after.strip()
    return normalize_text(mid)


def context_alignment_score(user_text: str, candidate_full_text: str) -> float:
    """0..1 — LCS coverage of the template's context line inside the user message."""
    nm = context_middle_normalized(candidate_full_text)
    if not nm:
        return 0.0
    nu = normalize_text(strip_ref_suffix(user_text))
    if not nu:
        return 0.0
    return lcs_length(nu, nm) / max(len(nm), 1)


def request_tail_normalized(text: str) -> str:
    """Request fragment: everything after the first comma (prefill ``{g} {c}, {r}``)."""
    t = strip_ref_suffix(text).strip()
    if not t:
        return ""
    comma = t.find(",")
    if comma == -1:
        return ""
    return normalize_text(t[comma + 1 :].strip())


def request_alignment_score(user_text: str, candidate_full_text: str) -> float:
    """0..1 — LCS coverage of the template's request line in the user message."""
    nr = request_tail_normalized(candidate_full_text)
    if not nr:
        return 0.0
    nu = normalize_text(strip_ref_suffix(user_text))
    if not nu:
        return 0.0
    return lcs_length(nu, nr) / max(len(nr), 1)


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
    session_id: int | None = None  # scan_sessions.id — None for legacy/test rows


@dataclass
class MatchResult:
    qr_id: int
    final_score: float
    raw_score: float
    method: str  # "lcs"
    session_id: int | None = None  # the exact scan_sessions row that was matched


def pick_best_match(
    user_text: str,
    candidates: list[MatchCandidate],
    *,
    now_ts: int,
    min_score: float = 0.35,
    min_gap: float = 0.08,
    tau_minutes: float = 60.0,
    require_confidence: bool = False,
    prefer_recent_scan_on_tie: bool = True,
) -> MatchResult | None:
    if not candidates:
        return None
    nu = normalize_text(strip_ref_suffix(user_text))
    if not nu:
        return None

    scored: list[tuple[float, float, float, float, float, MatchCandidate]] = []
    for c in candidates:
        ns = normalize_text(strip_ref_suffix(c.full_prefilled_text))
        if not ns:
            continue
        lcs = lcs_length(nu, ns)
        raw = lcs / max(len(ns), 1)
        age_min = max(0.0, (now_ts - c.anchor_at) / 60.0)
        final = raw * math.exp(-age_min / max(tau_minutes, 1e-6))
        greet = greeting_alignment_score(user_text, c.full_prefilled_text)
        ctx = context_alignment_score(user_text, c.full_prefilled_text)
        req = request_alignment_score(user_text, c.full_prefilled_text)
        scored.append((final, raw, greet, ctx, req, c))

    if not scored:
        return None

    if not require_confidence:
        def _combined(row: tuple[float, float, float, float, float, MatchCandidate]) -> float:
            final, raw, greet, ctx, req, c = row
            recency = math.exp(
                -max(0.0, (now_ts - c.anchor_at) / 60.0) / max(tau_minutes, 1e-6)
            )
            return (
                raw
                + GREET_ALIGN_WEIGHT * greet
                + CONTEXT_ALIGN_WEIGHT * ctx
                + REQUEST_ALIGN_WEIGHT * req
                + RECENCY_BONUS_WEIGHT * recency
            )

        scored.sort(key=_combined, reverse=True)
        best_final, best_raw, _g, _x, _r, best_c = scored[0]
        return MatchResult(
            qr_id=best_c.qr_id,
            final_score=best_final,
            raw_score=best_raw,
            method="lcs",
            session_id=best_c.session_id,
        )

    scored.sort(key=lambda t: t[0], reverse=True)
    best_final, best_raw, _g0, _x0, _r0, best_c = scored[0]
    second_final = scored[1][0] if len(scored) > 1 else 0.0

    if best_final < min_score:
        return None
    if (
        len(scored) > 1
        and best_final - second_final < min_gap
        and second_final >= min_score
    ):
        _, _, _g1, _x1, _rq1, c1 = scored[0]
        _, _, _g2, _x2, _rq2, c2 = scored[1]
        if c2.anchor_at > c1.anchor_at:
            best_final, best_raw, _a, _b, _rq, best_c = scored[1]
        else:
            best_final, best_raw, _a, _b, _rq, best_c = scored[0]
    elif len(scored) > 1 and best_final - second_final < min_gap:
        return None

    return MatchResult(
        qr_id=best_c.qr_id,
        final_score=best_final,
        raw_score=best_raw,
        method="lcs",
        session_id=best_c.session_id,
    )


def candidate_from_row(row: dict[str, Any]) -> MatchCandidate:
    anchor = row.get("scanned_at")
    if anchor is None:
        anchor = row.get("match_anchor_at")
    if anchor is None:
        anchor = row.get("created_at")
    if anchor is None:
        raise KeyError("row must include scanned_at, match_anchor_at, or created_at")
    sid = row.get("session_id")
    return MatchCandidate(
        qr_id=int(row["qr_id"]),
        full_prefilled_text=str(row["full_prefilled_text"]),
        anchor_at=int(anchor),
        session_id=int(sid) if sid is not None else None,
    )
