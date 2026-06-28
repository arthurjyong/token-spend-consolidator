"""Plan pro-rating checks. Run: PYTHONPATH=src python3 tests/test_plan.py"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tokenspend.plan import Plan, PlanSegment

DAILY = lambda monthly: monthly * 12 / 365.0


def test_flat_plan_prorates_per_day():
    plan = Plan.flat(100.0)
    paid, runs = plan.amount_paid(date(2026, 6, 1), date(2026, 6, 10))  # 10 days
    assert abs(paid - DAILY(100.0) * 10) < 1e-9
    assert len(runs) == 1 and runs[0].days == 10


def test_multi_segment_breakdown():
    plan = Plan.from_dicts([
        {"from": "2000-01-01", "monthly": 20, "label": "Pro"},
        {"from": "2026-06-06", "monthly": 100, "label": "Max 5x"},
        {"from": "2026-06-28", "monthly": 200, "label": "Max 20x"},
    ])
    paid, runs = plan.amount_paid(date(2026, 5, 29), date(2026, 6, 28))
    days = [r.days for r in runs]
    assert days == [8, 22, 1], days            # Pro / Max5x / Max20x
    expected = DAILY(20) * 8 + DAILY(100) * 22 + DAILY(200) * 1
    assert abs(paid - expected) < 1e-9
    assert [r.segment.monthly for r in runs] == [20, 100, 200]


def test_segment_extends_backward_before_first_date():
    plan = Plan.from_dicts([{"from": "2026-06-06", "monthly": 100}])
    # a day before the first 'from' still resolves to the earliest segment
    assert plan.segment_on(date(2026, 1, 1)).monthly == 100


def _run():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run()
