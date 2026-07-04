# HANDOFF — token-spend-consolidator

Cross-session bridge. Claude Code memory is path-keyed; open a fresh session **from this folder**, read this file, then `AGENTS.md` (architecture + gotchas) and `docs/BLUEPRINT.md` (locked spec). Full history is in `git log`.

## Goal
A tiny, local-first, **Claude-only** tool answering "what would my AI usage have cost at API rates?" — for Arthur's personal reference (so the $200/mo Max sub *feels* justified). Exact where possible, honestly estimated where not. Architecture stays provider-agnostic but **don't build other providers** (see memory `claude-only-scope`).

## What's built (committed on `main` through 0f2a10a; ⚠️ the Jul 4 session's work — tier-aware `scripts/calibrate_quota.py`, `quota.py` note fix, polished SwiftBar plugin, this file, `docs/plans/recalibrate-max20x.md` — is in the working tree, NOT yet committed)
- **M0 core** — `model.py`, `valuation.py`, `collectors/claude_code_log.py`, `consolidate.py`, `plan.py`, `cli.py`. `tokenspend` prints API-equivalent Code spend vs your plan-history-aware subscription.
- **Pricing** — `pricing/litellm_prices.json` (vendored LiteLLM, 2376 text models; refresh `scripts/refresh_pricing.py`) + `pricing/overrides.json` (Anthropic models pinned, verified vs `claude-api` skill). `resolve()` overlays overrides on the base.
- **Collectors + registry** — `collectors/registry.py::build_collectors` is the single wiring point. `claude_code_log` (surface `claude-code`, exact) + `anthropic_api_usage` (surface `api`, Admin usage report, needs `ANTHROPIC_ADMIN_KEY`, off if absent). Disjoint surfaces → no double-count.
- **State + menu bar** — `state.py` writes `~/.config/tokenspend/state.json`; `display/swiftbar/tokenspend.5m.py` reads it only (blueprint §10). The bar shows **exact Code $ this 5h session** (no network); dropdown adds **week** + **since-subscription** + the combined-incl-chat estimate (on-demand quota fetch). Polished Jul 4: small-caps section headers, Menlo-bold $ lines (explicit `INK` color — SwiftBar dims non-clickable rows otherwise), Unicode `▓░` quota bars from the cached %, explicit "chat ≈ $0" + why-line when the estimate clamps, red staleness warning past 90 min. Owner wants it *more* refined still — a native SwiftUI `MenuBarExtra(.window)` popover (Usage-for-Claude style, same read-only state contract) is the agreed candidate next milestone if the polish doesn't satisfy; NSMenu text rows are SwiftBar's ceiling.
- **Whole-account estimate (opt-in, ToS-grey)** — `quota.py` + `--quota`. Reads the Claude Code OAuth token from the **macOS Keychain** (`Claude Code-credentials`) → `GET https://api.anthropic.com/api/oauth/usage` (returns **% only**, e.g. `five_hour`/`seven_day` utilization + `resets_at`; **never dollars**). Endpoint **429s hard if polled** → cache-first, 10-min TTL, never poll. OFF by default; bad key/offline degrades gracefully.
- **Steering** — `AGENTS.md` (tool-agnostic), `CLAUDE.md` (`@AGENTS.md` + Claude specifics), `CLAUDE.local.md` (gitignored, personal), `.claude/` Stop-hook runs stdlib tests. Rationale: `docs/research/steering-practices.md`.
- **Tests** (stdlib, no pytest): `test_valuation`, `test_plan`, `test_state`, `test_api_collector`, `test_quota`. Run: `for t in valuation plan state api_collector quota; do PYTHONPATH=src python3 tests/test_$t.py; done`

## Installed on Arthur's Mac (this session)
- `tokenspend` via **pipx, editable install** → `~/.local/bin/tokenspend`; the venv's `.pth` points at the repo's `src/`, so the installed CLI (and the plugin, whose directory SwiftBar points at) always run current repo code — **no reinstall needed after edits**, but both break if the external volume is unmounted.
- **SwiftBar** (`brew install --cask swiftbar`), running; `PluginDirectory` → `display/swiftbar/`.
- **launchd agent** `com.tokenspend.refresh` (`~/Library/LaunchAgents/com.tokenspend.refresh.plist`) runs `tokenspend --write-state` every 10 min (no network) so the bar stays fresh.
- Runtime files in `~/.config/tokenspend/`: `state.json`, `quota_cache.json`, `quota_calibration.json`, `window_calibration.json`, and `plan.json` — the last is a **symlink to the repo's `plan.json`** (added Jul 4). It matters: the CLI finds the plan via `./plan.json` or that config path, and the launchd agent runs with no repo CWD — without the symlink every background refresh wrote a plan-less state (no tier, wrong since-sub, calibration mis-scaled ÷20), which masqueraded as "chat estimate not syncing". Personal calibration inputs in repo `gitignored-data/` (never committed).
- Undo: `launchctl unload ~/Library/LaunchAgents/com.tokenspend.refresh.plist` · `pipx uninstall token-spend-consolidator` · `brew uninstall --cask swiftbar`.

## Quota↔token calibration — the active work
**Owner's method (correct):** the endpoint gives only %, so reverse-calculate $. Segment the quota curve into 5h sessions (from the Usage-for-Claude CSV); the **chat-free** ones (cross-referenced vs the chat-export timestamps) are pure Code, so `$/% = exact Code $ ÷ session-%`. True rate = **MAX** over Code-only sessions. Apply to all sessions → `chat = total − Code`. Reproduce: `PYTHONPATH=src python3 scripts/calibrate_quota.py [--save]` (reads `gitignored-data/`; `--save` writes `window_calibration.json` the menu bar reads).

**Findings (Max 20x era, calibrated Jul 4 from 4 chat-free sessions Jun 29–Jul 1):** **~1.3M tokens ≈ 1% of the 5h session ≈ $1.86** (range 1.06–1.75M/%; max $3.87/%). Striking: that's only **~1.5× the Max-5x rate, not the ×4** the menu bar had been extrapolating from the tier multiplier — session limits evidently don't scale linearly with the weekly tier factor (or quota weights the model mix differently). The saved `window_calibration.json` is now measured-on-tier (`tier_label: Max 20x`), so `window_rates()` applies it at scale 1.0 with no "estimate" label. The script is now tier-aware: sessions are labelled via `plan.segment_on` (boundary refined to the exact reset instant), per-tier stats are printed, and `--save` uses **current-tier sessions only**. It also reads the CSV's `Weekly Reset Event` column and reports every non-Monday counter reset — the Jun 28 upgrade **and** the **Jul 2 05:16 local Fable-5-release goodwill reset** (weekly 48→0) both show up.

**Findings (Max 5x era, Jun 6–28, superseded):** ~0.9M tokens ≈ 1% ≈ $1.20 (range 0.1–1.8M/%). Owner's **5:1 rule confirmed**: ~5% session ≈ 1% weekly (still assumed for the weekly rate on 20x — remeasure someday). Combined all-Claude ≈ $2,476 over that window vs ~$72 paid = **~34×**; chat ≈ as big as Code. Method **blind-validated**: it detected heavy chat from the quota curve alone before the export confirmed it.

**⚠️ Remaining refinements (the open backlog):**
1. ~~Tier change unmeasured~~ **done Jul 4** (see findings above). New caveat in its place: the 4 calibration sessions predate the Fable 5 release (Jul 2), so the 20x rate reflects an Opus-4.8-heavy mix — Fable 5 is 2× Opus $/token and its quota weighting is unknown; recheck after a chat-free Fable-heavy coding stretch (same drill: fresh CSV + chat export into `gitignored-data/`, `scripts/calibrate_quota.py --save`).
2. **Mid-week counter resets clamp the weekly chat estimate to $0** until the next Monday (weekly% covers only since the reset while weekly Code spans 7d) — happened on Jun 28 (upgrade) and again Jul 2 (Fable 5 release); self-heals each Monday. Also: window *boundaries* in `state.json` come from the cached quota reading, so after a long gap the session/week windows are stale until the menu bar's "Refresh + chat estimate" does a live fetch.
3. **Big variance (~8×) in $/%** — driven by model mix; the quota likely weights models differently than $ (Opus counts more than Haiku/cache-reads). A real refinement would be **per-model-weighted calibration** rather than one blended $/%.
4. **Session-window detection is heuristic** (reset = %-drop / gap / event); **sub-start is date-granular** (plan segment midnight, not the actual 13:06 upgrade time).
5. UI is plain SwiftBar text; estimates are order-of-magnitude by nature.

## Watch-outs
Hard-won invariants (de-dup `(message.id, requestId)`, don't-sum `usage.iterations`, cache TTL split, `cwd` basename, `<synthetic>`→$0, pricing-lives-in-JSON) are in **`AGENTS.md` → Gotchas**. Live logs append as you work, so the headline drifts a few $ between runs (expected). Never poll the quota endpoint (429s for hours).

## Sensible next steps (none urgent)
- **Recheck the 20x rate on a Fable-5-heavy mix** (backlog item 1 above) — the pre-Fable calibration may drift as usage shifts to the 2×-priced model.
- Consider **per-model-weighted** quota calibration (item 3).
- Surface the combined estimate in `state.json` history for a trend; optional iOS widget (same read-only state contract).
- Cross-device aggregation (still Claude) — optional.
