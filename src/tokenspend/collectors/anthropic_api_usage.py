"""ApiUsageCollector for Anthropic's Admin Usage & Cost API.

Reads GET /v1/organizations/usage_report/messages (grouped by model, daily
buckets) — the org's own billing record of *API* (pay-as-you-go) usage. Each
bucket carries the exact token counts Anthropic billed, so fidelity is "exact"
and it feeds valuation.py with no special-casing (the field names line up):

    uncached_input_tokens                       -> input
    output_tokens                               -> output
    cache_read_input_tokens                     -> cache_read
    cache_creation.ephemeral_5m_input_tokens    -> cache_write_5m
    cache_creation.ephemeral_1h_input_tokens    -> cache_write_1h

This is the SECOND collector type (after the Claude Code LogCollector) and the
first proof of the provider/surface plugin model. Note: API usage and
subscription Claude Code usage are *disjoint* billing — Claude Code on a Max
subscription does not appear here — so this surface ("api") never double-counts
the log collector's surface ("claude-code"). Requires an Admin API key
(sk-ant-admin...); when none is configured the collector is inactive and the
app degrades gracefully to exact-only log spend.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

from ..model import TokenCounts, UsageRecord

PROVIDER = "anthropic"
SURFACE = "api"
DEFAULT_BASE_URL = "https://api.anthropic.com"
ENDPOINT = "/v1/organizations/usage_report/messages"
API_VERSION = "2023-06-01"
DEFAULT_WINDOW_DAYS = 30
MAX_DAILY_BUCKETS = 31  # API cap for bucket_width="1d"


def _to_rfc3339(s: str) -> str:
    """Accept a 'YYYY-MM-DD' (snap to UTC midnight) or pass through an RFC 3339 string."""
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s}T00:00:00Z"
    return s


def records_from_report_page(page: dict) -> Iterator[UsageRecord]:
    """Map one usage-report page (the JSON envelope) to UsageRecords. Pure — unit-tested."""
    for bucket in page.get("data") or []:
        ts = bucket.get("starting_at")
        for r in bucket.get("results") or []:
            cc = r.get("cache_creation") or {}
            tokens = TokenCounts(
                input=int(r.get("uncached_input_tokens") or 0),
                output=int(r.get("output_tokens") or 0),
                cache_read=int(r.get("cache_read_input_tokens") or 0),
                cache_write_5m=int(cc.get("ephemeral_5m_input_tokens") or 0),
                cache_write_1h=int(cc.get("ephemeral_1h_input_tokens") or 0),
            )
            if tokens.total == 0:
                continue  # empty group (e.g. web-search-only rows) — nothing to value
            model = r.get("model") or "unknown"
            # source_ref makes a bucket×group row unique so re-runs over the same
            # window de-duplicate cleanly when consolidated across devices.
            ws = r.get("workspace_id") or "-"
            tier = r.get("service_tier") or "-"
            yield UsageRecord(
                provider=PROVIDER,
                surface=SURFACE,
                model=model,
                timestamp=ts,
                tokens=tokens,
                fidelity="exact",
                source_ref=f"anthropic-api:{ts}:{model}:{ws}:{tier}",
                project=None,
            )


class AnthropicApiUsageCollector:
    """Pulls exact API token usage from the Anthropic Admin usage report."""

    name = "anthropic-api"
    fidelity = "exact"

    def __init__(
        self,
        admin_key: str | None = None,
        *,
        starting_at: str | None = None,
        ending_at: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        bucket_width: str = "1d",
        fetch=None,
    ):
        self.admin_key = admin_key or os.environ.get("ANTHROPIC_ADMIN_KEY")
        self.starting_at = _to_rfc3339(starting_at) if starting_at else self._default_start()
        self.ending_at = _to_rfc3339(ending_at) if ending_at else None
        self.base_url = base_url.rstrip("/")
        self.bucket_width = bucket_width
        self._fetch = fetch or self._http_fetch  # injectable for tests
        self.stats = {"pages": 0, "buckets": 0, "rows": 0, "error": ""}

    @staticmethod
    def _default_start() -> str:
        start = datetime.now(timezone.utc).date() - timedelta(days=DEFAULT_WINDOW_DAYS)
        return f"{start.isoformat()}T00:00:00Z"

    @property
    def available(self) -> bool:
        return bool(self.admin_key)

    @property
    def coverage_note(self) -> str:
        return ("exact, from the Anthropic Admin usage API (pay-as-you-go API spend; "
                "excludes subscription Claude Code usage)")

    def _http_fetch(self, page_token: str | None) -> dict:
        query = [
            ("starting_at", self.starting_at),
            ("bucket_width", self.bucket_width),
            ("group_by[]", "model"),
            ("limit", str(MAX_DAILY_BUCKETS)),
        ]
        if self.ending_at:
            query.append(("ending_at", self.ending_at))
        if page_token:
            query.append(("page", page_token))
        url = f"{self.base_url}{ENDPOINT}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={
            "x-api-key": self.admin_key or "",
            "anthropic-version": API_VERSION,
        })
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted host)
            return json.loads(resp.read().decode())

    def collect(self) -> Iterator[UsageRecord]:
        if not self.available:
            return
        page_token: str | None = None
        try:
            while True:
                page = self._fetch(page_token)
                self.stats["pages"] += 1
                self.stats["buckets"] += len(page.get("data") or [])
                for rec in records_from_report_page(page):
                    self.stats["rows"] += 1
                    yield rec
                if not page.get("has_more"):
                    break
                page_token = page.get("next_page")
                if not page_token:
                    break
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
            # Graceful degradation: a bad key / network blip never breaks the run.
            self.stats["error"] = str(e)

    def report_line(self) -> str:
        s = self.stats
        if s["error"]:
            return f"  [anthropic-api] skipped — {s['error']}"
        return (f"  [anthropic-api] {s['pages']} page(s) · {s['buckets']:,} day-buckets · "
                f"{s['rows']:,} model-rows  (pay-as-you-go API; excludes subscription Claude Code)")
