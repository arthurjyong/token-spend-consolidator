"""Subscription plan history → how much you actually paid over a window.

A plan is a list of segments, each "from this date, the monthly fee is X".
Fees change over time (Pro → Max 5x → Max 20x), so the only honest comparison
against API-equivalent spend is to pro-rate the active fee day-by-day across the
usage window. Daily rate = monthly × 12 / 365.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class PlanSegment:
    start: date          # fee takes effect on this date (inclusive)
    monthly: float       # monthly fee in USD
    label: str | None = None


@dataclass(frozen=True)
class PaidRun:
    segment: PlanSegment
    days: int
    subtotal: float

    @property
    def name(self) -> str:
        base = f"${self.segment.monthly:,.0f}/mo"
        return f"{self.segment.label} ({base})" if self.segment.label else base


class Plan:
    def __init__(self, segments: list[PlanSegment]):
        if not segments:
            raise ValueError("a plan needs at least one segment")
        self.segments = sorted(segments, key=lambda s: s.start)

    @classmethod
    def flat(cls, monthly: float, label: str | None = None) -> "Plan":
        return cls([PlanSegment(date(1970, 1, 1), monthly, label)])

    @classmethod
    def from_dicts(cls, items: list[dict]) -> "Plan":
        return cls([
            PlanSegment(date.fromisoformat(it["from"]), float(it["monthly"]),
                        it.get("label"))
            for it in items
        ])

    @classmethod
    def load(cls, path: Path | str) -> "Plan":
        data = json.loads(Path(path).read_text())
        return cls.from_dicts(data["segments"])

    def segment_on(self, d: date) -> PlanSegment:
        active = self.segments[0]  # extends backward before the first 'from'
        for s in self.segments:
            if s.start <= d:
                active = s
            else:
                break
        return active

    def amount_paid(self, start: date, end: date) -> tuple[float, list[PaidRun]]:
        """Pro-rate the active fee per day over [start, end]; group contiguous runs."""
        total = 0.0
        runs: list[PaidRun] = []
        cur_seg: PlanSegment | None = None
        cur_days = 0
        cur_sub = 0.0
        d = start
        while d <= end:
            seg = self.segment_on(d)
            daily = seg.monthly * 12 / DAYS_PER_YEAR
            total += daily
            if seg is not cur_seg:
                if cur_seg is not None:
                    runs.append(PaidRun(cur_seg, cur_days, cur_sub))
                cur_seg, cur_days, cur_sub = seg, 0, 0.0
            cur_days += 1
            cur_sub += daily
            d += timedelta(days=1)
        if cur_seg is not None:
            runs.append(PaidRun(cur_seg, cur_days, cur_sub))
        return total, runs
