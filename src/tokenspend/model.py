"""The normalized data model shared by every collector.

The one fact true of every LLM provider: they bill on tokens, by type, per model.
So every collector — regardless of provider or surface — emits this same shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenCounts:
    """Token counts by billing type. Any may be 0/absent.

    Cache writes are split by TTL because they bill at different multiples of the
    input rate (5-minute ephemeral = 1.25x, 1-hour = 2x). Cache reads bill at 0.1x.
    """

    input: int = 0          # uncached input tokens (full price)
    output: int = 0
    cache_read: int = 0     # served from cache (~0.1x input)
    cache_write_5m: int = 0  # written to 5-minute cache (~1.25x input)
    cache_write_1h: int = 0  # written to 1-hour cache (~2x input)

    @property
    def total(self) -> int:
        return (
            self.input
            + self.output
            + self.cache_read
            + self.cache_write_5m
            + self.cache_write_1h
        )


@dataclass(frozen=True)
class UsageRecord:
    """One unit of usage, normalized across providers/surfaces.

    fidelity propagates all the way to the headline:
      "exact"     — token counts came from a real source (logs, billing API)
      "estimated" — inferred from a quota signal or a heuristic
    """

    provider: str          # e.g. "anthropic"
    surface: str           # e.g. "claude-code", "api", "claude-chat"
    model: str             # provider's model id, as it appeared in the source
    timestamp: str | None  # ISO-8601 when the usage happened
    tokens: TokenCounts
    fidelity: str          # "exact" | "estimated"
    source_ref: str | None  # opaque id used to de-duplicate (request/message id)
    device: str | None = None   # which machine reported it (cross-device de-dup)
    project: str | None = None  # optional grouping label (e.g. the project dir)
