"""Collectors — per-source adapters that emit normalized UsageRecords.

Four kinds exist (see docs/BLUEPRINT.md sec.5):
  LogCollector      — local logs with real token counts (exact)   <- implemented
  ApiUsageCollector — provider billing/usage API (exact)          <- future
  QuotaCollector    — a utilization % signal, no token counts     <- future, opt-in
  ManualCollector   — user-entered figures / heuristic            <- future
"""

from .claude_code_log import ClaudeCodeLogCollector

__all__ = ["ClaudeCodeLogCollector"]
