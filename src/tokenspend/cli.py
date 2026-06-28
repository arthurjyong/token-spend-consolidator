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

from .collectors import ClaudeCodeLogCollector
from .consolidate import Bucket, Report, consolidate
from .model import UsageRecord


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


def _print_report(r: Report, args) -> None:
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

    if args.plan_monthly and r.first_ts and r.last_ts:
        months = _months_between(r.first_ts[:7], r.last_ts[:7])
        sub_total = args.plan_monthly * months
        print("\n" + "-" * 64)
        print(f"  vs subscription: {_fmt_usd(args.plan_monthly)}/mo × {months} month(s) "
              f"= {_fmt_usd(sub_total)} paid")
        if sub_total > 0:
            ratio = r.total_usd / sub_total
            verdict = "you came out AHEAD" if ratio > 1 else "the subscription cost more"
            print(f"  API-equivalent / subscription = {ratio:.2f}×  →  {verdict}")
            print(f"  (Claude Code alone; chat usage not yet counted — see --help)")

    print()


def _months_between(start_ym: str, end_ym: str) -> int:
    sy, sm = (int(x) for x in start_ym.split("-"))
    ey, em = (int(x) for x in end_ym.split("-"))
    return (ey - sy) * 12 + (em - sm) + 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tokenspend", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="Claude Code projects dir (default ~/.claude/projects)")
    p.add_argument("--by", choices=["all", "model", "month", "project"], default="all",
                   help="which breakdown(s) to show")
    p.add_argument("--project", help="only projects whose label contains this substring")
    p.add_argument("--since", help="only usage on/after this date (YYYY-MM-DD)")
    p.add_argument("--until", help="only usage on/before this date (YYYY-MM-DD)")
    p.add_argument("--plan-monthly", type=float,
                   help="monthly subscription fee to compare against (e.g. 200 for Max 20x)")
    args = p.parse_args(argv)

    collector = ClaudeCodeLogCollector(root=args.root)
    records = _filtered(collector.collect(), project=args.project,
                        since=args.since, until=args.until)
    report = consolidate(records)
    _print_report(report, args)

    s = collector.stats
    print(f"  [scanned {s['files']:,} transcripts · {s['rows']:,} billed messages · "
          f"{s['deduped']:,} duplicates skipped]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
