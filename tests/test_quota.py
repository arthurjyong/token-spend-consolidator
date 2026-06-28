"""Whole-account quota estimate — parsing, max-ratio calibration, residual math,
cache-first fetch. No live calls (the endpoint is rate-limited). Run:
PYTHONPATH=src python3 tests/test_quota.py  (also works under pytest)."""

import sys
import tempfile
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tokenspend import quota
from tokenspend.quota import (
    QuotaReading,
    ANCHOR_DOLLARS_PER_PCT,
    estimate,
    fetch_usage,
    parse_reading,
    update_calibration,
)

RAW = {"five_hour": {"utilization": 71.0}, "seven_day": {"utilization": 14.0},
       "seven_day_opus": None}


def test_parse_reading():
    assert parse_reading(RAW) == (71.0, 14.0)
    assert parse_reading({}) == (0.0, 0.0)


def test_calibration_takes_running_max():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "calib.json"
        # week A: $280 at 14% -> 20 $/%
        rate, cal = update_calibration(280.0, 14.0, calib_path=p)
        assert cal and abs(rate - 20.0) < 1e-9
        # week B with chat: $200 at 20% -> 10 $/% (lower) must NOT lower the rate
        rate, cal = update_calibration(200.0, 20.0, calib_path=p)
        assert abs(rate - 20.0) < 1e-9, "a chat-heavy week must not drop the ceiling"
        # week C Code-only spike: $600 at 20% -> 30 $/% raises it
        rate, cal = update_calibration(600.0, 20.0, calib_path=p)
        assert abs(rate - 30.0) < 1e-9


def test_calibration_anchor_when_no_data():
    with tempfile.TemporaryDirectory() as d:
        rate, cal = update_calibration(0.0, 0.0, calib_path=Path(d) / "c.json")
        assert cal is False and rate == ANCHOR_DOLLARS_PER_PCT


def test_estimate_residual():
    r = QuotaReading(five_hour_pct=71.0, seven_day_pct=14.0, fetched="", from_cache=False)
    e = estimate(code_7d_usd=500.0, reading=r, dollars_per_pct=40.0)
    assert abs(e["ceiling_week"] - 4000.0) < 1e-9
    assert abs(e["combined_7d"] - 560.0) < 1e-9       # 14 * 40
    assert abs(e["chat_7d"] - 60.0) < 1e-9            # 560 - 500
    assert abs(e["combined_month_proj"] - 2400.0) < 1e-9  # 560/7*30


def test_estimate_never_below_exact():
    # if % * rate understates what logs already prove, clamp up to exact (no negative chat)
    r = QuotaReading(five_hour_pct=0.0, seven_day_pct=5.0, fetched="", from_cache=False)
    e = estimate(code_7d_usd=500.0, reading=r, dollars_per_pct=40.0)  # 5*40=200 < 500
    assert e["combined_7d"] == 500.0 and e["chat_7d"] == 0.0


def test_fetch_fresh_cache_skips_network():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "cache.json"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        quota._save(cache, {"raw": RAW, "fetched": now})

        def boom(_token):
            raise AssertionError("network must not be called when cache is fresh")

        rd = fetch_usage(token="t", cache_path=cache, getter=boom)
        assert rd is not None and rd.from_cache and rd.seven_day_pct == 14.0


def test_fetch_falls_back_to_cache_on_429():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "cache.json"
        quota._save(cache, {"raw": RAW, "fetched": "2000-01-01T00:00:00+00:00"})  # stale

        def rate_limited(_token):
            raise urllib.error.HTTPError(quota.USAGE_URL, 429, "Too Many Requests", None, None)

        rd = fetch_usage(token="t", cache_path=cache, ttl_min=10, getter=rate_limited)
        assert rd is not None and rd.from_cache and "429" in rd.note


def _run():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run()
