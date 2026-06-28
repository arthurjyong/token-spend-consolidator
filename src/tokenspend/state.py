"""State store: write the small JSON that display surfaces read.

The collector/consolidator writes this file; displays (menu bar, iOS widget) only
READ it (blueprint sec.10) — they never touch logs or credentials. That decoupling
is what makes new display surfaces trivial, so keep this shape small and stable.

build_state() is pure (takes `now` + `generated_at` as args) so it's testable;
the CLI supplies the real clock. write_state() writes atomically so a reader never
sees a half-written file.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .consolidate import Report, consolidate
from .model import UsageRecord
from .valuation import value

DEFAULT_STATE_PATH = Path.home() / ".config" / "tokenspend" / "state.json"

# Bump when the JSON shape changes; a display can refuse a version it predates.
SCHEMA = 1


def _between(records: Iterable[UsageRecord], lo: date, hi: date) -> list[UsageRecord]:
    lo_s, hi_s = lo.isoformat(), hi.isoformat()
    return [r for r in records if lo_s <= (r.timestamp or "")[:10] <= hi_s]


def _summary(r: Report) -> dict:
    return {
        "usd": round(r.total_usd, 2),
        "exact_usd": round(r.exact_usd, 2),
        "estimated_usd": round(r.estimated_usd, 2),
        "tokens": r.total_tokens,
        "records": r.records,
    }


def _top_projects(r: Report, n: int) -> list[dict]:
    rows = sorted(r.by_project.items(), key=lambda kv: kv[1].usd, reverse=True)[:n]
    return [{"project": k, "usd": round(b.usd, 2)} for k, b in rows]


def _daily_series(records: Iterable[UsageRecord], *, end: date, days: int) -> list[dict]:
    """Per-day total spend for the trailing `days` (for a sparkline). Zero-filled."""
    start = end - timedelta(days=days - 1)
    lo_s, hi_s = start.isoformat(), end.isoformat()
    sums: dict[str, float] = {}
    for r in records:
        d = (r.timestamp or "")[:10]
        if d and lo_s <= d <= hi_s:
            sums[d] = sums.get(d, 0.0) + value(r).usd
    return [
        {"date": (start + timedelta(days=i)).isoformat(),
         "usd": round(sums.get((start + timedelta(days=i)).isoformat(), 0.0), 2)}
        for i in range(days)
    ]


def build_state(
    records: Iterable[UsageRecord],
    *,
    now: date,
    generated_at: str,
    top: int = 5,
    history_days: int = 30,
) -> dict:
    """Build the display state from usage records. Windows: calendar-month (headline)
    + rolling 7-day (blueprint sec.15)."""
    recs = list(records)
    month_start = now.replace(day=1)
    week_start = now - timedelta(days=6)  # 7 calendar days incl. today

    month = consolidate(_between(recs, month_start, now))
    week = consolidate(_between(recs, week_start, now))
    allr = consolidate(recs)

    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "currency": "USD",
        "fidelity_note": "exact = Claude Code local logs; chat/API not yet counted",
        "month": {
            "label": now.strftime("%Y-%m"),
            **_summary(month),
            "top_projects": _top_projects(month, top),
        },
        "week": {
            "since": week_start.isoformat(),
            "until": now.isoformat(),
            **_summary(week),
        },
        "lifetime": {
            "first": (allr.first_ts or "")[:10] or None,
            "last": (allr.last_ts or "")[:10] or None,
            **_summary(allr),
        },
        "daily": _daily_series(recs, end=now, days=history_days),
    }


def _parse_iso(s: str | None):
    try:
        t = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def build_windows(
    records: Iterable[UsageRecord],
    *,
    now: datetime,
    session_start: datetime,
    week_start: datetime,
    sub_start: datetime,
    sub_label: str,
    session_pct: float = 0.0,
    week_pct: float = 0.0,
    session_rate: float | None = None,
    week_rate: float | None = None,
) -> dict:
    """Exact Claude Code $ for the session / weekly / since-subscription windows,
    plus an optional combined (Code + reverse-calc chat) when a quota % and a
    calibrated $/% rate are supplied. Pure — the CLI feeds it the boundaries
    (from the cached quota reading) and the calibration. See quota.py / blueprint §6."""
    code = [(dt, value(r).usd) for r in records
            if r.surface == "claude-code" and (dt := _parse_iso(r.timestamp)) is not None]

    def code_since(start: datetime) -> float:
        return round(sum(u for dt, u in code if start <= dt <= now), 2)

    def combined(code_usd: float, pct: float, rate: float | None) -> dict:
        if not rate or pct <= 0:
            return {}
        total = max(code_usd, round(pct * rate, 2))
        return {"combined": round(total, 2), "chat": round(max(0.0, total - code_usd), 2)}

    cs, cw = code_since(session_start), code_since(week_start)
    return {
        "session": {"code": cs, "since": session_start.isoformat(),
                    "pct": session_pct, **combined(cs, session_pct, session_rate)},
        "week": {"code": cw, "since": week_start.isoformat(),
                 "pct": week_pct, **combined(cw, week_pct, week_rate)},
        "since_sub": {"code": code_since(sub_start), "since": sub_start.isoformat(),
                      "label": sub_label},
    }


def write_state(state: dict, path: Path | str = DEFAULT_STATE_PATH) -> Path:
    """Write state atomically (tmp + rename) so a concurrent reader is never torn."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)
    return path
