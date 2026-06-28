"""Anthropic API usage collector — mapping, pagination, graceful degradation.
Run: PYTHONPATH=src python3 tests/test_api_collector.py  (also works under pytest)."""

import os
import re
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tokenspend.collectors.anthropic_api_usage import (
    AnthropicApiUsageCollector,
    records_from_report_page,
)
from tokenspend.valuation import value

PAGE_1 = {
    "data": [{
        "starting_at": "2026-06-01T00:00:00Z",
        "ending_at": "2026-06-02T00:00:00Z",
        "results": [
            {
                "model": "claude-opus-4-8",
                "uncached_input_tokens": 1000,
                "output_tokens": 2000,
                "cache_read_input_tokens": 500,
                "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 50},
                "workspace_id": None,
                "service_tier": "standard",
            },
            {  # web-search-only row → zero tokens → must be skipped
                "model": "claude-haiku-4-5",
                "uncached_input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
                "server_tool_use": {"web_search_requests": 3},
            },
        ],
    }],
    "has_more": True,
    "next_page": "TOKEN2",
}

PAGE_2 = {
    "data": [{
        "starting_at": "2026-06-02T00:00:00Z",
        "ending_at": "2026-06-03T00:00:00Z",
        "results": [
            {"model": "claude-sonnet-4-6", "uncached_input_tokens": 10, "output_tokens": 20,
             "cache_read_input_tokens": 0, "cache_creation": {}},
        ],
    }],
    "has_more": False,
    "next_page": None,
}


def test_token_mapping_and_zero_skip():
    recs = list(records_from_report_page(PAGE_1))
    assert len(recs) == 1, "the zero-token web-search row should be skipped"
    r = recs[0]
    assert r.provider == "anthropic" and r.surface == "api" and r.fidelity == "exact"
    assert r.model == "claude-opus-4-8" and r.timestamp == "2026-06-01T00:00:00Z"
    t = r.tokens
    assert (t.input, t.output, t.cache_read, t.cache_write_5m, t.cache_write_1h) == (1000, 2000, 500, 100, 50)
    assert r.source_ref.startswith("anthropic-api:2026-06-01T00:00:00Z:claude-opus-4-8")


def test_pagination_follows_next_page():
    calls = []
    pages = [PAGE_1, PAGE_2]

    def fake_fetch(page_token):
        calls.append(page_token)
        return pages[len(calls) - 1]

    c = AnthropicApiUsageCollector(admin_key="sk-ant-admin-test", fetch=fake_fetch)
    recs = list(c.collect())
    assert calls == [None, "TOKEN2"], calls            # first page then next_page token
    assert [r.model for r in recs] == ["claude-opus-4-8", "claude-sonnet-4-6"]
    assert c.stats["pages"] == 2 and c.stats["rows"] == 2 and c.stats["buckets"] == 2


def test_inactive_without_key_yields_nothing():
    saved = os.environ.pop("ANTHROPIC_ADMIN_KEY", None)
    try:
        c = AnthropicApiUsageCollector(admin_key=None)
        assert c.available is False
        assert list(c.collect()) == []
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_ADMIN_KEY"] = saved


def test_network_error_is_graceful():
    def boom(_page_token):
        raise urllib.error.URLError("connection refused")

    c = AnthropicApiUsageCollector(admin_key="sk-ant-admin-test", fetch=boom)
    assert list(c.collect()) == []          # no crash
    assert c.stats["error"] and "skipped" in c.report_line()


def test_api_record_prices_through_valuation():
    r = next(iter(records_from_report_page(PAGE_1)))
    v = value(r)
    # 1000 in @5e-6 + 2000 out @25e-6 + 500 read @0.5e-6 + 100 5m @6.25e-6 + 50 1h @10e-6
    expected = 1000 * 5e-6 + 2000 * 25e-6 + 500 * 0.5e-6 + 100 * 6.25e-6 + 50 * 10e-6
    assert v.priced and abs(v.usd - expected) < 1e-12, (v.usd, expected)


def test_default_window_is_rfc3339_utc_midnight():
    c = AnthropicApiUsageCollector(admin_key="sk-ant-admin-test", fetch=lambda _t: PAGE_2)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00Z", c.starting_at), c.starting_at


def test_date_only_since_is_snapped_to_rfc3339():
    c = AnthropicApiUsageCollector(admin_key="k", starting_at="2026-05-01", fetch=lambda _t: PAGE_2)
    assert c.starting_at == "2026-05-01T00:00:00Z"


def _run():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run()
