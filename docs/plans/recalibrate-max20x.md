# Recalibrate quota $/% on Max 20x (post-Fable-5 reset)

Date: 2026-07-04. Inputs arrived in `inbox/`: fresh quota CSV (Jun 6 → Jul 4) + fresh chat export zip.

## Why now
- HANDOFF backlog item 1: the menu bar has been ×4-extrapolating the Max-5x rate since the Jun 28 tier upgrade. We now have a week of genuine Max-20x sessions to measure.
- The Fable 5 release reset the weekly counter mid-week (CSV shows weekly 48→0 with `Weekly Reset Event=true` at Jul 2 05:16 local, a Thursday). The script's reset detection only knew the ">50 weekly drop on non-Monday = upgrade" heuristic, and never read the `Weekly Reset Event` column at all.

## Changes
1. **Data placement**: `inbox/claude-usage-history-Custom.csv` → `gitignored-data/quota-csv/usage-history-2026-07-04.csv`; extract chat-export zip → `gitignored-data/chat-exports/2026-07-04/`.
2. **`scripts/calibrate_quota.py`**:
   - Read the `Weekly Reset Event` column; report every non-Monday weekly counter reset (tier upgrades *and* goodwill/release resets like Fable 5's), instead of the single >50-drop "upgrade" guess.
   - Tier-aware calibration: label each Code-only session with its plan segment (`plan.segment_on`), refine the Jun-28 boundary to the exact reset instant when one exists on that date, and compute/save the median-$/% from **current-tier sessions only**. Prior behaviour (blend all sessions) silently mixed Max-5x and Max-20x rates.
3. Run `calibrate_quota.py --save`, then `tokenspend --write-state` so the menu bar drops the "×4 estimate" label.

## Verified facts
- `claude-fable-5` pricing already pinned in `pricing/overrides.json`; matches claude-api skill ($10/$50 per 1M, 0.1×/1.25×/2× cache). Fable-5 rows in the Code logs value correctly — no pricing change needed.
- Reset timeline from CSV (local = UTC+8): Jun 28 13:06 upgrade reset (89→0), Jun 29 Mon 10:02 scheduled, **Jul 2 05:16 Fable-5 release reset (48→0)**.
