#!/usr/bin/env python3
# <xbar.title>Token Spend</xbar.title>
# <xbar.version>1.0</xbar.version>
# <xbar.author>Arthur Yong</xbar.author>
# <xbar.desc>API-equivalent cost of your AI usage, glanceable in the menu bar.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
#
# SwiftBar/xbar plugin. It ONLY reads the state file the collector writes
# (blueprint sec.10) — it never touches Claude logs or any credential, which is
# what keeps it portable (the iOS widget will read the same shape).
#
# Setup:
#   1. brew install --cask swiftbar   (then point SwiftBar at this folder)
#   2. Refresh the data periodically so the number stays fresh, e.g. a cron line:
#        */15 * * * * tokenspend --write-state
#      (or use the "Refresh now" item in the dropdown). The filename's `.5m.`
#      only controls how often the bar re-RENDERS the file, not data collection.
#
# Env overrides:
#   TOKENSPEND_STATE        path to state.json (default ~/.config/tokenspend/state.json)
#   TOKENSPEND_REFRESH_CMD  command the "Refresh now" item runs (default: tokenspend --write-state)

import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(os.environ.get("TOKENSPEND_STATE", Path.home() / ".config/tokenspend/state.json"))
REFRESH_CMD = os.environ.get("TOKENSPEND_REFRESH_CMD", "tokenspend --write-state")
STALE_MIN = 90  # flag the readout if the data is older than this many minutes

BLOCKS = "▁▂▃▄▅▆▇█"


def money(x: float) -> str:
    return f"${x:,.0f}"


def parse_dt(iso: str):
    try:
        t = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def ago(secs: float) -> str:
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def sparkline(values) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return BLOCKS[0] * len(vals)
    return "".join(BLOCKS[int((v - lo) / (hi - lo) * (len(BLOCKS) - 1))] for v in vals)


def refresh_item(label="Refresh now"):
    print(f'{label} | shell=/bin/sh param0=-c param1="{REFRESH_CMD}" terminal=false refresh=true')


def main() -> None:
    if not STATE.exists():
        print("💸 —")
        print("---")
        print("No state file yet | color=gray")
        print(f"Run:  {REFRESH_CMD} | font=Menlo size=12")
        refresh_item("Write it now")
        return

    try:
        data = json.loads(STATE.read_text())
    except (json.JSONDecodeError, OSError):
        print("💸 ⚠️")
        print("---")
        print(f"Can't read {STATE} | color=red size=12")
        refresh_item()
        return

    m = data.get("month", {})
    w = data.get("week", {})
    life = data.get("lifetime", {})

    dt = parse_dt(data.get("generated_at", ""))
    secs_old = (datetime.now(timezone.utc) - dt).total_seconds() if dt else None
    stale = secs_old is not None and secs_old > STALE_MIN * 60

    title = f"💸 {money(m.get('usd', 0))}"
    if stale or dt is None:
        title += " ⚠️"
    print(title)

    print("---")
    print("Token Spend — API-equivalent | size=12 color=gray")
    print(f"This month ({m.get('label', '?')}):  {money(m.get('usd', 0))} | font=Menlo")
    print(f"Last 7 days:  {money(w.get('usd', 0))} | font=Menlo")
    if life.get("first"):
        print(f"Lifetime:  {money(life.get('usd', 0))}  "
              f"({life['first']} → {life.get('last')}) | font=Menlo size=12")

    spark = sparkline([d.get("usd", 0) for d in data.get("daily", [])][-14:])
    if spark:
        print(f"Last 14 days  {spark} | font=Menlo size=12 color=gray")

    tops = m.get("top_projects", [])
    if tops:
        print("---")
        print("Top projects this month | size=12 color=gray")
        for tp in tops:
            print(f"{tp.get('project', '?')}   {money(tp.get('usd', 0))} | font=Menlo")

    print("---")
    note = data.get("fidelity_note")
    if note:
        print(f"{note} | size=12 color=gray")
    updated = ago(secs_old) if secs_old is not None else "unknown time"
    print(f"updated {updated} | size=12 color={'red' if stale else 'gray'}")
    refresh_item()
    print(f"Open state file | href=file://{STATE}")


if __name__ == "__main__":
    main()
