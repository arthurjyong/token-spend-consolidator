#!/usr/bin/env python3
"""Quota -> token/$ calibration workbench (the ongoing "what is 1% worth" analysis).

Reverse-calculates the dollar/token value of the Claude quota bar by correlating
three local sources (all under gitignored-data/):

  1. quota CSV   (Usage for Claude -> Export CSV): minute-resolution Session % + Weekly %
  2. chat export (claude.ai data export): timestamps of when you were chatting
  3. Claude Code logs (via the project's collector): exact tokens/$ over time

Method: segment the quota curve into 5-hour sessions; the ones with ZERO chat are
driven only by Code (which we measure exactly), so $/% = exact Code $ / session-%
(and tokens/% likewise). The TRUE rate is the MAX over Code-only sessions — a
session that also had chat looks cheaper-per-%. Apply that rate to every session
to back out chat. See gitignored-data/README.md.

Run:  PYTHONPATH=src python3 scripts/calibrate_quota.py
      (override inputs with --csv / --chat-export)

NOTE: calibration is plan-tier-specific (a % is usage/limit). It auto-detects the
Max 5x -> Max 20x upgrade reset and reports it; recalibrate per tier.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import glob
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tokenspend import quota  # noqa: E402
from tokenspend.collectors import ClaudeCodeLogCollector  # noqa: E402
from tokenspend.plan import Plan  # noqa: E402
from tokenspend.valuation import value  # noqa: E402


def _load_plan():
    for p in (ROOT / "plan.json", Path.home() / ".config" / "tokenspend" / "plan.json"):
        if p.exists():
            return Plan.load(p)
    return None

P = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))


def _latest(pattern: str) -> str | None:
    hits = sorted(glob.glob(pattern))
    return hits[-1] if hits else None


def _default_csv() -> str | None:
    return _latest(str(ROOT / "gitignored-data" / "quota-csv" / "*.csv"))


def _default_chat() -> str | None:
    hits = sorted((ROOT / "gitignored-data" / "chat-exports").glob("*/conversations.json"))
    return str(hits[-1]) if hits else None


def segment_sessions(rows):
    """rows: sorted [(ts, session%, weekly%, reset_event)] -> [(start, end, peak%)]."""
    out, cs, cp, lt, ls = [], rows[0][0], rows[0][1], rows[0][0], rows[0][1]
    for t, s, w, ev in rows[1:]:
        if ev or s < ls - 5 or (t - lt).total_seconds() / 60 > 25:
            out.append((cs, lt, cp)); cs, cp = t, s
        else:
            cp = max(cp, s)
        lt, ls = t, s
    out.append((cs, lt, cp))
    return out


def detect_upgrade_reset(rows):
    """A weekly drop >50 that isn't a Monday reset ~= a plan upgrade rebase."""
    for (t0, s0, w0, _), (t1, s1, w1, _) in zip(rows, rows[1:]):
        if w0 - w1 > 50 and t1.astimezone().weekday() != 0:
            return t1
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=_default_csv(), help="quota usage CSV (default: latest in gitignored-data/quota-csv/)")
    ap.add_argument("--chat-export", default=_default_chat(), help="conversations.json (default: latest in gitignored-data/chat-exports/)")
    ap.add_argument("--save", action="store_true",
                    help="save session/weekly $/% rates to window_calibration.json for the menu bar")
    a = ap.parse_args()
    if not a.csv or not a.chat_export:
        print("Missing inputs. Put a quota CSV in gitignored-data/quota-csv/ and a chat export in "
              "gitignored-data/chat-exports/<date>/ (see gitignored-data/README.md), or pass --csv / --chat-export.")
        return 1

    rows = []
    with open(a.csv) as f:
        for r in csv.DictReader(f):
            rows.append((P(r["Timestamp"]), float(r["Session %"]),
                         float(r["Weekly All Models %"]), r.get("Session Reset Event", "").lower() == "true"))
    rows.sort()
    p0, p1 = rows[0][0], rows[-1][0]
    sessions = segment_sessions(rows)
    upgrade = detect_upgrade_reset(rows)

    chat = sorted(P(m["created_at"]) for c in json.load(open(a.chat_export))
                  for m in c.get("chat_messages", []) if m.get("sender") == "human" and m.get("created_at"))
    chat_cut = max(chat)
    chat_in = lambda x, y: (lambda i: i < len(chat) and chat[i] <= y)(bisect.bisect_left(chat, x))

    recs = sorted((P(r.timestamp), value(r).usd, r.tokens.total)
                  for r in ClaudeCodeLogCollector().collect() if r.timestamp)
    rt = [x[0] for x in recs]
    def win(x, y):
        i, j = bisect.bisect_left(rt, x), bisect.bisect_right(rt, y)
        return sum(recs[k][1] for k in range(i, j)), sum(recs[k][2] for k in range(i, j))

    print(f"quota CSV {p0:%b%d %H:%MZ} -> {p1:%b%d %H:%MZ}  |  chat known thru {chat_cut:%b%d %H:%MZ}  |  {len(sessions)} sessions")
    if upgrade:
        print(f"plan-upgrade reset detected: {upgrade:%b%d %H:%MZ} ({upgrade.astimezone():%b%d %H:%M local}) "
              f"-> readings before/after are on different tiers")

    cal = []
    for s, e, pk in sessions:
        if chat_in(s, e) or e > chat_cut or not (8 <= pk < 99):
            continue
        usd, tok = win(s, e)
        if usd > 0:
            cal.append((usd / pk, tok / pk, s, pk, usd, tok))
    cal.sort(reverse=True)
    if not cal:
        print("\nNo verified Code-only sessions to calibrate from yet.")
        return 0

    usd_per = [c[0] for c in cal]; tok_per = [c[1] for c in cal]
    print(f"\nCode-only calibration sessions: {len(cal)}")
    print(f"  $/session-%   median {statistics.median(usd_per):.2f}  max {max(usd_per):.2f}")
    print(f"  tok/session-% median {statistics.median(tok_per)/1e6:.2f}M  max {max(tok_per)/1e6:.2f}M")
    for r, tp, s, pk, usd, tok in cal[:8]:
        print(f"    {s:%b%d %H:%MZ}  peak {pk:>3.0f}%  ${usd:>6.2f}  {tok/1e6:>5.1f}M  ->  ${r:.2f}/%  {tp/1e6:.2f}M/%")

    med = statistics.median(usd_per); mx = max(usd_per)
    def apply(rate):
        code = chatest = total = 0.0
        for s, e, pk in sessions:
            cu, _ = win(s, e); t = max(pk * rate, cu)
            code += cu; total += t; chatest += max(0.0, t - cu)
        return code, chatest, total
    days = (p1 - p0).days or 1
    print(f"\nCombined estimate over {days}d (Code exact + chat reverse-calc):")
    for lab, rate in (("median", med), ("max", mx)):
        c, ch, comb = apply(rate)
        print(f"  [{lab} ${rate:.2f}/%]  Code ${c:,.0f} + est chat ${ch:,.0f} = ${comb:,.0f}  (~${comb/days*30:,.0f}/mo)")
    print("\nCaveats: order-of-magnitude (per-% varies with model mix); tier-specific (see upgrade above).")

    if a.save:
        plan = _load_plan()
        mid_date = cal[len(cal) // 2][2].date()  # representative calibration date
        seg = plan.segment_on(mid_date) if plan else None
        tier_label = seg.label if seg else None
        tier_mult = quota.tier_multiplier(tier_label)
        session_rate = med
        week_rate = med * 5  # owner's measured 5:1 session:weekly ratio
        path = quota.save_window_calibration(session_rate, week_rate, tier_mult, tier_label)
        print(f"\nSaved window calibration -> {path}")
        print(f"  session ${session_rate:.2f}/%  ·  weekly ${week_rate:.2f}/%  ·  tier {tier_label} (×{tier_mult:.0f})")
        print("  the menu bar tier-scales these to your current plan; recalibrate on Max 20x for accuracy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
