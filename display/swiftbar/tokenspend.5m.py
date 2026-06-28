#!/usr/bin/env python3
# <xbar.title>Token Spend</xbar.title>
# <xbar.version>2.0</xbar.version>
# <xbar.author>Arthur Yong</xbar.author>
# <xbar.desc>API-equivalent $ spent this Claude session/week/since-subscription, in the menu bar.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
#
# SwiftBar/xbar plugin. Reads ONLY the state file the collector writes — it never
# touches your logs or any credential (blueprint sec.10).
#
# Bar (always visible, NO network): exact Claude Code $ spent this 5-hour session.
# Dropdown: the same per window PLUS the combined estimate incl. claude.ai chat,
# which rides on the cached quota reading. "Refresh + chat estimate" makes the one
# (ToS-grey) quota call on demand — nothing polls it automatically.
#
# Setup: brew install --cask swiftbar; point SwiftBar at this folder. Keep the bar
# fresh with a cron line: */15 * * * * tokenspend --write-state   (no network).
#
# Env: TOKENSPEND_STATE (state.json path) · TOKENSPEND_CMD (default "tokenspend")

import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(os.environ.get("TOKENSPEND_STATE", Path.home() / ".config/tokenspend/state.json"))
CMD = os.environ.get("TOKENSPEND_CMD", "tokenspend")
STALE_MIN = 90


def money(x):
    return f"${x:,.0f}"


def parse_dt(iso):
    try:
        t = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if (t and t.tzinfo is None) else t


def clock(iso):
    t = parse_dt(iso)
    if not t:
        return ""
    return t.astimezone().strftime("%-I:%M %p")


def ago(iso):
    t = parse_dt(iso)
    if not t:
        return "?"
    s = (datetime.now(timezone.utc) - t).total_seconds()
    if s < 90:
        return "just now"
    if s < 3600:
        return f"{int(s//60)}m ago"
    if s < 86400:
        return f"{int(s//3600)}h ago"
    return f"{int(s//86400)}d ago"


def action(label, cmd, **kw):
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f'{label} | shell=/bin/sh param0=-c param1="{cmd}" terminal=false refresh=true {extra}')


def win_line(label, w, reset_iso=None):
    """One window row: exact Code $, plus '+~chat = ~combined' if present."""
    code = w.get("code", 0)
    txt = f"{label}:  {money(code)} Code"
    if "combined" in w and w.get("chat", 0) >= 1:
        txt += f"  +~{money(w['chat'])} chat = ~{money(w['combined'])}"
    if reset_iso:
        txt += f"   · resets {clock(reset_iso)}"
    print(f"{txt} | font=Menlo")


def main():
    if not STATE.exists():
        print("💸 —")
        print("---")
        print("No state yet | color=gray")
        action(f"Write it now ({CMD} --write-state)", f"{CMD} --write-state")
        return

    try:
        data = json.loads(STATE.read_text())
    except (json.JSONDecodeError, OSError):
        print("💸 ⚠️")
        print("---")
        print(f"Can't read {STATE} | color=red size=12")
        return

    win = data.get("windows") or {}
    meta = win.get("_meta") or {}
    sess = win.get("session") or {}
    week = win.get("week") or {}
    sub = win.get("since_sub") or {}

    # Bar: exact Code $ this session (no network).
    print(f"💸 {money(sess.get('code', 0))}")
    print("---")
    tier = f"  [{meta.get('tier')}]" if meta.get("tier") else ""
    print(f"Token Spend — API-equivalent{tier} | size=12 color=gray")

    win_line("This session (5h)", sess, meta.get("session_resets"))
    win_line("This week", week, meta.get("week_resets"))
    if sub:
        sl = sub.get("label", "since subscription")
        print(f"Since {sl}:  {money(sub.get('code', 0))} Code | font=Menlo")

    print("---")
    if "combined" in sess:
        print(f"exact = Claude Code logs · chat = quota estimate | size=12 color=gray")
        print(f"calibration: {meta.get('calibration', '?')} | size=12 color=gray")
    else:
        print("chat estimate off — click below to fetch quota | size=12 color=gray")
    q = meta.get("quota", "none")
    print(f"quota reading: {q} | size=12 color=gray")
    print(f"updated {ago(data.get('generated_at'))} | size=12 color=gray")

    action("↻ Refresh + chat estimate (fetches quota)", f"{CMD} --write-state --quota")
    action("↻ Refresh exact only (no network)", f"{CMD} --write-state")
    print(f"Open state file | href=file://{STATE}")


if __name__ == "__main__":
    main()
