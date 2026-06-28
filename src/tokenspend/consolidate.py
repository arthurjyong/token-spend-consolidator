"""Consolidator: merge valued records into the headline number + breakdowns."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from .model import UsageRecord
from .valuation import value


@dataclass
class Bucket:
    usd: float = 0.0
    tokens: int = 0
    records: int = 0

    def add(self, usd: float, tokens: int) -> None:
        self.usd += usd
        self.tokens += tokens
        self.records += 1


@dataclass
class Report:
    total_usd: float = 0.0
    exact_usd: float = 0.0
    estimated_usd: float = 0.0
    total_tokens: int = 0
    records: int = 0
    unpriced_records: int = 0          # rows whose model had no pricing entry
    unpriced_models: set[str] = field(default_factory=set)
    by_model: dict[str, Bucket] = field(default_factory=lambda: defaultdict(Bucket))
    by_month: dict[str, Bucket] = field(default_factory=lambda: defaultdict(Bucket))
    by_project: dict[str, Bucket] = field(default_factory=lambda: defaultdict(Bucket))
    first_ts: str | None = None
    last_ts: str | None = None


def consolidate(records: Iterable[UsageRecord]) -> Report:
    r = Report()
    for rec in records:
        v = value(rec)
        tokens = rec.tokens.total
        r.total_usd += v.usd
        r.total_tokens += tokens
        r.records += 1
        if rec.fidelity == "estimated":
            r.estimated_usd += v.usd
        else:
            r.exact_usd += v.usd
        if not v.priced and rec.model:
            r.unpriced_records += 1
            r.unpriced_models.add(rec.model)

        label = v.pricing_key or (rec.model or "unknown")
        r.by_model[label].add(v.usd, tokens)
        r.by_project[rec.project or "unknown"].add(v.usd, tokens)
        if rec.timestamp:
            r.by_month[rec.timestamp[:7]].add(v.usd, tokens)  # YYYY-MM
            if r.first_ts is None or rec.timestamp < r.first_ts:
                r.first_ts = rec.timestamp
            if r.last_ts is None or rec.timestamp > r.last_ts:
                r.last_ts = rec.timestamp
    return r
