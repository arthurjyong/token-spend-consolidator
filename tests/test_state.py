"""State-builder sanity checks (windows, top projects, daily series, atomic write).
Run: PYTHONPATH=src python3 tests/test_state.py  (also works under pytest)."""

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tokenspend.model import TokenCounts, UsageRecord
from tokenspend.state import SCHEMA, build_state, write_state

NOW = date(2026, 6, 28)


def _rec(day: str, project: str, model: str = "claude-opus-4-8", out: int = 1_000_000,
         fidelity: str = "exact"):
    # 1M opus output = $25; 1M sonnet output = $15 (see pricing table).
    return UsageRecord(
        provider="anthropic", surface="claude-code", model=model,
        timestamp=f"{day}T12:00:00Z", tokens=TokenCounts(output=out),
        fidelity=fidelity, source_ref=f"{day}:{project}", project=project,
    )


# r1 today ($25, A) · r2 within 7d ($15, B) · r3 this-month-not-7d ($25, A) · r4 last month ($25, C)
RECS = [
    _rec("2026-06-28", "A"),
    _rec("2026-06-25", "B", model="claude-sonnet-4-6"),
    _rec("2026-06-02", "A"),
    _rec("2026-05-15", "C"),
]


def test_month_window_is_calendar_month():
    s = build_state(RECS, now=NOW, generated_at="2026-06-28T12:00:00+00:00")
    assert s["month"]["label"] == "2026-06"
    assert abs(s["month"]["usd"] - 65.0) < 1e-9, s["month"]["usd"]  # r1+r2+r3


def test_week_window_is_rolling_7_days():
    s = build_state(RECS, now=NOW, generated_at="x")
    assert s["week"]["since"] == "2026-06-22" and s["week"]["until"] == "2026-06-28"
    assert abs(s["week"]["usd"] - 40.0) < 1e-9, s["week"]["usd"]  # r1+r2 only (r3 is 06-02)


def test_lifetime_counts_everything():
    s = build_state(RECS, now=NOW, generated_at="x")
    assert abs(s["lifetime"]["usd"] - 90.0) < 1e-9  # all four
    assert s["lifetime"]["first"] == "2026-05-15" and s["lifetime"]["last"] == "2026-06-28"


def test_top_projects_sorted_by_spend():
    s = build_state(RECS, now=NOW, generated_at="x")
    tops = s["month"]["top_projects"]
    assert tops[0]["project"] == "A" and abs(tops[0]["usd"] - 50.0) < 1e-9  # r1+r3
    assert tops[1]["project"] == "B"


def test_daily_series_zero_filled_and_windowed():
    s = build_state(RECS, now=NOW, generated_at="x", history_days=30)
    daily = s["daily"]
    assert len(daily) == 30
    assert daily[-1] == {"date": "2026-06-28", "usd": 25.0}
    by_date = {d["date"]: d["usd"] for d in daily}
    assert by_date["2026-06-27"] == 0.0           # zero-filled gap
    assert "2026-05-15" not in by_date            # older than the 30-day window (r4 excluded)
    assert abs(sum(d["usd"] for d in daily) - 65.0) < 1e-9  # r1+r2+r3, not r4


def test_estimated_split_is_zero_for_exact_logs():
    s = build_state(RECS, now=NOW, generated_at="x")
    assert s["month"]["estimated_usd"] == 0.0 and s["month"]["exact_usd"] == s["month"]["usd"]


def test_write_state_roundtrips_atomically():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "nested" / "state.json"  # parent dirs created
        s = build_state(RECS, now=NOW, generated_at="2026-06-28T12:00:00+00:00")
        out = write_state(s, path)
        assert out == path and path.exists()
        assert not path.with_name(path.name + ".tmp").exists()  # tmp cleaned up
        loaded = json.loads(path.read_text())
        assert loaded["schema"] == SCHEMA and loaded["month"]["label"] == "2026-06"


def test_build_windows_exact_and_combined():
    from datetime import datetime, timedelta, timezone
    from tokenspend.state import build_windows
    now = datetime(2026, 6, 28, 17, 0, 0, tzinfo=timezone.utc)

    def rec(dt, out=1_000_000, model="claude-opus-4-8", surface="claude-code"):
        return UsageRecord(provider="anthropic", surface=surface, model=model,
                           timestamp=dt.isoformat().replace("+00:00", "Z"),
                           tokens=TokenCounts(output=out), fidelity="exact", source_ref="x")

    recs = [
        rec(now - timedelta(hours=1)),                               # $25, in session
        rec(now - timedelta(minutes=30), model="claude-sonnet-4-6"),  # $15, in session
        rec(now - timedelta(days=2)),                                # $25, in week not session
        rec(now - timedelta(hours=1), surface="api"),                # excluded (not claude-code)
    ]
    w = build_windows(recs, now=now,
                      session_start=now - timedelta(hours=5),
                      week_start=now - timedelta(days=7),
                      sub_start=now - timedelta(hours=4), sub_label="Max 20x",
                      session_pct=10.0, week_pct=2.0, session_rate=5.0, week_rate=40.0)
    assert abs(w["session"]["code"] - 40.0) < 1e-9, w["session"]   # $25+$15, api excluded
    assert abs(w["week"]["code"] - 65.0) < 1e-9                     # + $25 two days ago
    assert abs(w["since_sub"]["code"] - 40.0) < 1e-9               # last 4h
    assert w["session"]["combined"] == 50.0 and w["session"]["chat"] == 10.0  # 10% * $5
    assert w["week"]["combined"] == 80.0 and abs(w["week"]["chat"] - 15.0) < 1e-9  # 2% * $40
    assert "combined" not in w["since_sub"]                         # exact only


def _run():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run()
