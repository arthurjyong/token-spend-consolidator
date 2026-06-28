# gitignored-data/ — personal calibration inputs (NOT committed)

The folder name says it: everything here except this README is **personal data and is git-ignored** — it never goes in the open-source repo. This is where the raw inputs for **quota↔token calibration** live (the ongoing work of turning a quota % into a defensible dollar/token figure). When you bring a new export/CSV/screenshot in, put it here and remove the original from wherever it landed (e.g. the Desktop) so nothing personal lingers outside this folder.

## Layout
```
gitignored-data/
  chat-exports/<YYYY-MM-DD>/        # a Claude data export (conversations.json + projects/ + …)
  quota-csv/usage-history-<date>.csv # "Usage for Claude" app → Usage History → Export CSV
  screenshots/                       # reference screenshots of the usage dashboard
```

## How to refresh each input
- **Chat export** — claude.ai → Settings → Privacy → *Export data*; unzip the result into a new dated folder under `chat-exports/`. Gives the *timestamps* of when you chatted (no token counts — chat doesn't expose them).
- **Quota CSV** — the *Usage for Claude* menu-bar app → **Usage History** panel → set range (90d) → **Export CSV**. Gives minute-resolution Session % + Weekly % over time — the historical signal the API won't give.
- **Screenshots** — optional, for reference.

## Why these together
The quota endpoint reports only a **%**, never dollars. We reverse-calculate the "$/%" (and "tokens/%") from windows where you used **only Claude Code** (the % is moved entirely by usage the local logs measure exactly). Cross-referencing the chat-export timestamps tells us which windows were genuinely chat-free. See `scripts/calibrate_quota.py`.

## Calibration is tier-specific
A quota % is `usage ÷ plan-limit`, so it **changes when the plan changes**. The Jun-2026 inputs here are mostly **Max 5x**; the Max 5x → **Max 20x** upgrade (~Jun 28 13:06 local) reset both counters and quadrupled the limits, so the per-% rate is ~4× higher on Max 20x. **Re-export both files after a Code-only stretch on the new plan** to recalibrate.
