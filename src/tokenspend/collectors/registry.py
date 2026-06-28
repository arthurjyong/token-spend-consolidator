"""Collector registry — the one place that decides which collectors are active.

cli.py asks for the active collectors and consumes them uniformly; it does not
hard-wire any single one. Adding a provider/surface (e.g. an OpenAI usage API,
blueprint M4) is a new collector module plus one line here — layers 2 and 3
(valuation, consolidate) never change.

Every collector exposes: collect() -> Iterable[UsageRecord], `name`,
`coverage_note`, and report_line() -> str (its one-line scan summary, "" to omit).
"""

from __future__ import annotations

from .anthropic_api_usage import AnthropicApiUsageCollector
from .claude_code_log import ClaudeCodeLogCollector


def build_collectors(
    *,
    root=None,
    admin_key: str | None = None,
    starting_at: str | None = None,
    ending_at: str | None = None,
    enable_api: bool = True,
):
    """Return the active collectors. The Anthropic API collector joins only when
    an Admin key is configured (graceful degradation to exact-only log spend)."""
    collectors = [ClaudeCodeLogCollector(root=root)]
    if enable_api:
        api = AnthropicApiUsageCollector(
            admin_key=admin_key, starting_at=starting_at, ending_at=ending_at,
        )
        if api.available:
            collectors.append(api)
    return collectors
