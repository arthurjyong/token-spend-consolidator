"""Valuation engine: turn a UsageRecord into dollars.

value(record) -> usd. It looks up (model) in the pricing table, multiplies each
token type by its rate, and sums. Provider-agnostic — it knows nothing about
where the usage came from.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import UsageRecord
from .pricing import resolve


@dataclass(frozen=True)
class Valuation:
    usd: float
    pricing_key: str | None  # which pricing entry was used (None = unpriced model)
    priced: bool             # False when the model had no pricing entry


def _rate(entry: dict, key: str, *, fallback_from_input: float | None) -> float:
    """Read a rate, deriving cache rates from the input rate if the entry omits them."""
    if key in entry and entry[key] is not None:
        return float(entry[key])
    if fallback_from_input is not None:
        return float(entry.get("input_cost_per_token", 0.0)) * fallback_from_input
    return 0.0


def value(record: UsageRecord) -> Valuation:
    key, entry = resolve(record.model)
    if entry is None:
        return Valuation(usd=0.0, pricing_key=None, priced=False)

    t = record.tokens
    in_rate = float(entry.get("input_cost_per_token", 0.0))
    out_rate = float(entry.get("output_cost_per_token", 0.0))
    read_rate = _rate(entry, "cache_read_input_token_cost", fallback_from_input=0.1)
    write5m_rate = _rate(entry, "cache_creation_input_token_cost", fallback_from_input=1.25)
    write1h_rate = _rate(
        entry, "cache_creation_input_token_cost_above_1hr", fallback_from_input=2.0
    )

    usd = (
        t.input * in_rate
        + t.output * out_rate
        + t.cache_read * read_rate
        + t.cache_write_5m * write5m_rate
        + t.cache_write_1h * write1h_rate
    )
    return Valuation(usd=usd, pricing_key=key, priced=True)
