"""tokenspend CLI — print what your Claude Code usage would have cost at API rates.

  tokenspend                      # headline + breakdowns over all local logs
  tokenspend --by month           # focus one breakdown
  tokenspend --project my-app   # filter to projects whose label contains this
  tokenspend --since 2026-06-01   # only usage on/after this date
  tokenspend --plan-monthly 200   # compare against a $200/mo subscription
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path

from .collectors import build_collectors
from .consolidate import Bucket, Report, consolidate
from .model import UsageRecord
from .plan import Plan
from .state import DEFAULT_STATE_PATH, build_state, write_state

# Where to look for a saved subscription history when none is given on the CLI.
_PLAN_SEARCH = (
    Path("plan.json"),
    Path.home() / ".config" / "tokenspend" / "plan.json",
)


def _resolve_plan(args) -> Plan | None:
    if args.plan_monthly is not None:
        return Plan.flat(args.plan_monthly)
    if args.plan_file:
        return Plan.load(args.plan_file)
    for p in _PLAN_SEARCH:
        if p.exists():
            return Plan.load(p)
    return None


def _fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def _fmt_tokens(n: int) -> str:
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= div:
            return f"{n / div:.2f}{unit}"
    return str(n)


def _filtered(records: Iterable[UsageRecord], *, project: str | None,
              since: str | None, until: str | None) -> Iterable[UsageRecord]:
    for rec in records:
        if project and project.lower() not in (rec.project or "").lower():
            continue
        ts = rec.timestamp or ""
        if since and ts[:10] < since:
            continue
        if until and ts[:10] > until:
            continue
        yield rec


def _print_bucket_table(title: str, buckets: dict[str, Bucket], total: float, top: int) -> None:
    print(f"\n{title}")
    rows = sorted(buckets.items(), key=lambda kv: kv[1].usd, reverse=True)
    shown = rows[:top] if top else rows
    width = max((len(k) for k, _ in shown), default=10)
    for key, b in shown:
        share = (b.usd / total * 100) if total else 0
        print(f"  {key:<{width}}  {_fmt_usd(b.usd):>12}  {share:5.1f}%  "
              f"{_fmt_tokens(b.tokens):>9} tok  ({b.records:,} msgs)")
    if top and len(rows) > top:
        rest = sum(b.usd for _, b in rows[top:])
        print(f"  {'… ' + str(len(rows) - top) + ' more':<{width}}  {_fmt_usd(rest):>12}")


def _print_report(r: Report, args, plan: Plan | None) -> None:
    print("=" * 64)
    print("  Token Spend — API-equivalent cost of your Claude Code usage")
    print("=" * 64)
    span = ""
    if r.first_ts and r.last_ts:
        span = f"  ({r.first_ts[:10]} → {r.last_ts[:10]})"
    print(f"\n  HEADLINE: {_fmt_usd(r.total_usd)}{span}")
    print(f"  ≈ {_fmt_usd(r.exact_usd)} exact (local logs) + "
          f"{_fmt_usd(r.estimated_usd)} estimated")
    print(f"  {_fmt_tokens(r.total_tokens)} tokens across {r.records:,} assistant messages")
    if r.unpriced_records:
        print(f"  note: {r.unpriced_records:,} messages on unpriced models "
              f"({', '.join(sorted(r.unpriced_models))}) counted as $0")

    which = args.by
    if which in ("all", "model"):
        _print_bucket_table("By model:", r.by_model, r.total_usd, top=0)
    if which in ("all", "project"):
        _print_bucket_table("By project (top 12):", r.by_project, r.total_usd, top=12)
    if which in ("all", "month"):
        # months read best chronologically, not by spend
        print("\nBy month:")
        for month in sorted(r.by_month):
            b = r.by_month[month]
            print(f"  {month}  {_fmt_usd(b.usd):>12}  {_fmt_tokens(b.tokens):>9} tok  "
                  f"({b.records:,} msgs)")

    if plan is not None and r.first_ts and r.last_ts:
        start = date.fromisoformat(r.first_ts[:10])
        end = date.fromisoformat(r.last_ts[:10])
        paid, runs = plan.amount_paid(start, end)
        print("\n" + "-" * 64)
        print(f"  vs subscription actually paid ({start} → {end}, pro-rated daily):")
        for run in runs:
            print(f"    {run.name:<22} {run.days:>3} day(s)  = {_fmt_usd(run.subtotal):>9}")
        print(f"  total paid ≈ {_fmt_usd(paid)}")
        if paid > 0:
            ratio = r.total_usd / paid
            verdict = "you came out AHEAD" if ratio > 1 else "the subscription cost more"
            print(f"  API-equivalent / subscription = {ratio:.1f}×  →  {verdict}")
            print("  (Claude Code alone; chat usage not yet counted)")

    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tokenspend", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="Claude Code projects dir (default ~/.claude/projects)")
    p.add_argument("--by", choices=["all", "model", "month", "project"], default="all",
                   help="which breakdown(s) to show")
    p.add_argument("--project", help="only projects whose label contains this substring")
    p.add_argument("--since", help="only usage on/after this date (YYYY-MM-DD)")
    p.add_argument("--until", help="only usage on/before this date (YYYY-MM-DD)")
    p.add_argument("--plan-file",
                   help="JSON file with your subscription history (see plan.example.json); "
                        "auto-detected from ./plan.json or ~/.config/tokenspend/plan.json")
    p.add_argument("--plan-monthly", type=float,
                   help="shorthand: a single flat monthly fee (overrides --plan-file)")
    p.add_argument("--write-state", action="store_true",
                   help="write the consolidated state JSON for displays (menu bar) and exit")
    p.add_argument("--state-file",
                   help=f"where to write state with --write-state (default {DEFAULT_STATE_PATH})")
    p.add_argument("--no-api", action="store_true",
                   help="skip the Anthropic API usage collector even if ANTHROPIC_ADMIN_KEY is set")
    args = p.parse_args(argv)

    # Registry decides which collectors are active; the API one joins only when an
    # Admin key is present. starting_at/ending_at scope the API window to --since/--until.
    collectors = build_collectors(
        root=args.root, starting_at=args.since, ending_at=args.until,
        enable_api=not args.no_api,
    )
    records = [rec for c in collectors for rec in c.collect()]

    if args.write_state:
        # Canonical ambient view: build from ALL records (ignore display/date filters).
        state = build_state(
            records,
            now=date.today(),
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        path = write_state(state, args.state_file or DEFAULT_STATE_PATH)
        m, w = state["month"], state["week"]
        print(f"wrote {path}")
        print(f"  this month ({m['label']}): {_fmt_usd(m['usd'])}   "
              f"last 7 days: {_fmt_usd(w['usd'])}")
        _print_scan(collectors)
        return 0

    plan = _resolve_plan(args)
    filtered = _filtered(records, project=args.project, since=args.since, until=args.until)
    report = consolidate(filtered)
    _print_report(report, args, plan)
    _print_scan(collectors)
    return 0


def _print_scan(collectors) -> None:
    for c in collectors:
        line = c.report_line()
        if line:
            print(line)


if __name__ == "__main__":
    raise SystemExit(main())
