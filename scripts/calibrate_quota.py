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

NOTE: calibration is plan-tier-specific (a % is usage/limit). Sessions are
labelled with their plan segment and the median/max used for --save comes from
CURRENT-tier sessions only. Mid-week weekly-counter resets (tier upgrades, and
goodwill resets on big model releases, e.g. Fable 5 on 2026-07-02) are detected
from the CSV's Weekly Reset Event column and reported.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import glob
import json
import statistics
import sys
from datetime import date, datetime, timedelta
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
    """rows: sorted [(ts, session%, weekly%, reset_event, wk_event)] -> [(start, end, peak%)]."""
    out, cs, cp, lt, ls = [], rows[0][0], rows[0][1], rows[0][0], rows[0][1]
    for t, s, w, ev, _ in rows[1:]:
        if ev or s < ls - 5 or (t - lt).total_seconds() / 60 > 25:
            out.append((cs, lt, cp)); cs, cp = t, s
        else:
            cp = max(cp, s)
        lt, ls = t, s
    out.append((cs, lt, cp))
    return out


def detect_counter_resets(rows):
    """Non-Monday weekly counter resets -> [(ts, weekly% lost)]. Catches both plan
    upgrades (Jun 28 5x->20x) and goodwill resets on releases (Jul 2, Fable 5)."""
    out = []
    for (t0, s0, w0, e0, we0), (t1, s1, w1, e1, we1) in zip(rows, rows[1:]):
        if (we1 or w0 - w1 > 25) and w1 < w0 and t1.astimezone().weekday() != 0:
            if not out or (t1 - out[-1][0]).total_seconds() > 3600:
                out.append((t1, w0))
    return out


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
                         float(r["Weekly All Models %"]), r.get("Session Reset Event", "").lower() == "true",
                         r.get("Weekly Reset Event", "").lower() == "true"))
    rows.sort()
    p0, p1 = rows[0][0], rows[-1][0]
    sessions = segment_sessions(rows)
    resets = detect_counter_resets(rows)

    plan = _load_plan()
    def tier_of(ts):
        """Plan-segment label for a reading, refined from date-granular to the exact
        reset instant when a counter reset landed on the segment's start date."""
        if not plan:
            return None
        seg = plan.segment_on(ts.astimezone().date())
        for rt, _ in resets:  # chronological: first same-date reset = the tier-change instant
            if rt.astimezone().date() == seg.start:
                return seg.label if ts >= rt else plan.segment_on(seg.start - timedelta(days=1)).label
        return seg.label
    cur_tier = plan.segment_on(date.today()).label if plan else None

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
    for reset_t, lost in resets:
        print(f"weekly counter reset: {reset_t:%b%d %H:%MZ} ({reset_t.astimezone():%a %b%d %H:%M local})  "
              f"weekly {lost:.0f}% -> 0  [tier after: {tier_of(reset_t) or '?'}]")

    cal = []
    for s, e, pk in sessions:
        if chat_in(s, e) or e > chat_cut or not (8 <= pk < 99):
            continue
        usd, tok = win(s, e)
        if usd > 0:
            cal.append((usd / pk, tok / pk, s, pk, usd, tok, tier_of(s)))
    cal.sort(reverse=True)
    if not cal:
        print("\nNo verified Code-only sessions to calibrate from yet.")
        return 0

    for tier in sorted({c[6] for c in cal}, key=lambda t: str(t)):
        grp = [c for c in cal if c[6] == tier]
        usd_per = [c[0] for c in grp]; tok_per = [c[1] for c in grp]
        tag = " (current)" if tier == cur_tier else ""
        print(f"\nCode-only calibration sessions on {tier or 'unknown tier'}{tag}: {len(grp)}")
        print(f"  $/session-%   median {statistics.median(usd_per):.2f}  max {max(usd_per):.2f}")
        print(f"  tok/session-% median {statistics.median(tok_per)/1e6:.2f}M  max {max(tok_per)/1e6:.2f}M")
        for r, tp, s, pk, usd, tok, _ in grp[:8]:
            print(f"    {s:%b%d %H:%MZ}  peak {pk:>3.0f}%  ${usd:>6.2f}  {tok/1e6:>5.1f}M  ->  ${r:.2f}/%  {tp/1e6:.2f}M/%")

    cal_tier = cur_tier
    cur_cal = [c for c in cal if c[6] == cal_tier]
    if not cur_cal:  # nothing measured on the current tier yet: use the most recently measured tier
        cal_tier = max(cal, key=lambda c: c[2])[6]
        cur_cal = [c for c in cal if c[6] == cal_tier]
    usd_per = [c[0] for c in cur_cal]
    med = statistics.median(usd_per); mx = max(usd_per)
    cal_mult = quota.tier_multiplier(cal_tier)
    def apply(rate):
        # rate is $/% as measured on cal_tier; rescale per session's own tier
        # (a % elsewhere is a slice of a different limit)
        code = chatest = total = 0.0
        for s, e, pk in sessions:
            r = rate * quota.tier_multiplier(tier_of(s)) / cal_mult if cal_mult else rate
            cu, _ = win(s, e); t = max(pk * r, cu)
            code += cu; total += t; chatest += max(0.0, t - cu)
        return code, chatest, total
    days = (p1 - p0).days or 1
    src = cal_tier or "unknown tier"
    if cal_tier != cur_tier:
        src += f" (no {cur_tier} sessions yet)"
    print(f"\nCombined estimate over {days}d (Code exact + chat reverse-calc; rates measured on {src}, tier-scaled):")
    for lab, rate in (("median", med), ("max", mx)):
        c, ch, comb = apply(rate)
        print(f"  [{lab} ${rate:.2f}/%]  Code ${c:,.0f} + est chat ${ch:,.0f} = ${comb:,.0f}  (~${comb/days*30:,.0f}/mo)")
    print("\nCaveats: order-of-magnitude (per-% varies with model mix); tier-specific (see resets above).")

    if a.save:
        # label the calibration with the tier it was MEASURED on — if that isn't the
        # current tier, window_rates() tier-scales it and labels the result an estimate
        session_rate = med
        week_rate = med * 5  # owner's measured 5:1 session:weekly ratio
        path = quota.save_window_calibration(session_rate, week_rate, cal_mult, cal_tier)
        print(f"\nSaved window calibration -> {path}")
        print(f"  session ${session_rate:.2f}/%  ·  weekly ${week_rate:.2f}/%  ·  tier {cal_tier} (×{cal_mult:.0f})")
        if cal_tier != cur_tier:
            print(f"  no {cur_tier} Code-only sessions yet — the menu bar will tier-scale this (labelled estimate);")
            print("  rerun after a chat-free coding stretch on the current plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
