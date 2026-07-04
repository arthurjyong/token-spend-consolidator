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
import shutil
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(os.environ.get("TOKENSPEND_STATE", Path.home() / ".config/tokenspend/state.json"))


def _resolve_cmd():
    """Find the `tokenspend` command. SwiftBar runs with a minimal GUI PATH that
    misses pipx's ~/.local/bin, so fall back to common absolute locations."""
    env = os.environ.get("TOKENSPEND_CMD")
    if env:
        return env
    found = shutil.which("tokenspend")
    if found:
        return found
    for p in (Path.home() / ".local/bin/tokenspend",
              Path("/opt/homebrew/bin/tokenspend"), Path("/usr/local/bin/tokenspend")):
        if p.exists():
            return str(p)
    return "tokenspend"


CMD = _resolve_cmd()
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


def day_clock(iso):
    t = parse_dt(iso)
    if not t:
        return ""
    return t.astimezone().strftime("%a %-I:%M %p")


GRAY = "#6e6e73,#98989d"      # light,dark — SwiftBar picks per appearance
ACCENT = "#d96c47,#e8825a"    # progress-bar salmon
INK = "#1d1d1f,#ffffff"       # $ values: non-clickable rows render "disabled"-dim without an explicit color


def bar(pct, width=20):
    """Unicode progress bar for a 0–100 quota % (None -> no bar)."""
    if pct is None:
        return None
    filled = max(0, min(width, round(pct * width / 100)))
    return "▓" * filled + "░" * (width - filled) + f"  {pct:.0f}%"


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


def gap():
    print(" | size=3 trim=false")


def section(title, w, reset_txt=None):
    """One window block: small-caps header, bold $ line, optional quota bar."""
    hdr = title.upper()
    if reset_txt:
        hdr += f"   ·  resets {reset_txt}"
    print(f"{hdr} | size=11 color={GRAY} trim=false")
    val = f"  {money(w.get('code', 0))} Code"
    if "combined" in w:
        if w.get("chat", 0) >= 1:
            val += f"   +~{money(w['chat'])} chat  =  ~{money(w['combined'])}"
        else:
            val += "   ·  chat ≈ $0"
    print(f"{val} | font=Menlo-Bold size=14 color={INK} trim=false")
    b = bar(w.get("pct"))
    if b:
        print(f"  {b} | font=Menlo size=12 color={ACCENT} trim=false")


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
    tier = f"   [{meta.get('tier')}]" if meta.get("tier") else ""
    print(f"Token Spend — API-equivalent{tier} | size=12 color={GRAY}")

    gap()
    section("Session (5h)", sess, clock(meta.get("session_resets")))
    gap()
    section("Week", week, day_clock(meta.get("week_resets")))
    gap()
    if sub:
        sl = sub.get("label", "subscription")
        section(f"Since {sl}", sub)
    gap()

    print("---")
    if "combined" in sess:
        print(f"exact = Claude Code logs · chat = quota estimate | size=11 color={GRAY}")
        print(f"calibration: {meta.get('calibration', '?')} | size=11 color={GRAY}")
        if sess.get("chat", 0) < 1 and week.get("chat", 0) < 1:
            print(f"chat ≈ $0 while Code $ ≥ what the quota % implies — Code-heavy window, "
                  f"or a mid-week counter reset (weekly realigns at the Monday reset) | size=11 color={GRAY}")
    else:
        print(f"chat estimate off — click below to fetch quota | size=11 color={GRAY}")
    stale = (lambda t: t and (datetime.now(timezone.utc) - t).total_seconds() > STALE_MIN * 60)(
        parse_dt(data.get("generated_at")))
    upd = f"quota {meta.get('quota', 'none')} · updated {ago(data.get('generated_at'))}"
    print(f"{upd} | size=11 color={'#ff453b' if stale else GRAY}")

    action("Refresh + chat estimate (fetches quota)", f"{CMD} --write-state --quota", sfimage="arrow.clockwise")
    action("Refresh exact only (no network)", f"{CMD} --write-state", sfimage="arrow.clockwise.circle")
    print(f"Open claude.ai usage page | href=https://claude.ai/settings/usage sfimage=chart.line.uptrend.xyaxis")
    print(f"Open state file | href=file://{STATE} sfimage=doc.text")


if __name__ == "__main__":
    main()
