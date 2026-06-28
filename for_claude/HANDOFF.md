# HANDOFF — token-spend-consolidator

Cross-session bridge. Claude Code memory is path-keyed; open a fresh session **from this folder**, read this file, then `AGENTS.md` (architecture + gotchas) and `docs/BLUEPRINT.md` (locked spec). Full history is in `git log`.

## Goal
A tiny, local-first, **Claude-only** tool answering "what would my AI usage have cost at API rates?" — for Arthur's personal reference (so the $200/mo Max sub *feels* justified). Exact where possible, honestly estimated where not. Architecture stays provider-agnostic but **don't build other providers** (see memory `claude-only-scope`).

## What's built (all committed, on `main`)
- **M0 core** — `model.py`, `valuation.py`, `collectors/claude_code_log.py`, `consolidate.py`, `plan.py`, `cli.py`. `tokenspend` prints API-equivalent Code spend vs your plan-history-aware subscription.
- **Pricing** — `pricing/litellm_prices.json` (vendored LiteLLM, 2376 text models; refresh `scripts/refresh_pricing.py`) + `pricing/overrides.json` (Anthropic models pinned, verified vs `claude-api` skill). `resolve()` overlays overrides on the base.
- **Collectors + registry** — `collectors/registry.py::build_collectors` is the single wiring point. `claude_code_log` (surface `claude-code`, exact) + `anthropic_api_usage` (surface `api`, Admin usage report, needs `ANTHROPIC_ADMIN_KEY`, off if absent). Disjoint surfaces → no double-count.
- **State + menu bar** — `state.py` writes `~/.config/tokenspend/state.json`; `display/swiftbar/tokenspend.5m.py` reads it only (blueprint §10). The bar shows **exact Code $ this 5h session** (no network); dropdown adds **week** + **since-subscription** + the combined-incl-chat estimate (on-demand quota fetch).
- **Whole-account estimate (opt-in, ToS-grey)** — `quota.py` + `--quota`. Reads the Claude Code OAuth token from the **macOS Keychain** (`Claude Code-credentials`) → `GET https://api.anthropic.com/api/oauth/usage` (returns **% only**, e.g. `five_hour`/`seven_day` utilization + `resets_at`; **never dollars**). Endpoint **429s hard if polled** → cache-first, 10-min TTL, never poll. OFF by default; bad key/offline degrades gracefully.
- **Steering** — `AGENTS.md` (tool-agnostic), `CLAUDE.md` (`@AGENTS.md` + Claude specifics), `CLAUDE.local.md` (gitignored, personal), `.claude/` Stop-hook runs stdlib tests. Rationale: `docs/research/steering-practices.md`.
- **Tests** (stdlib, no pytest): `test_valuation`, `test_plan`, `test_state`, `test_api_collector`, `test_quota`. Run: `for t in valuation plan state api_collector quota; do PYTHONPATH=src python3 tests/test_$t.py; done`

## Installed on Arthur's Mac (this session)
- `tokenspend` via **pipx** → `~/.local/bin/tokenspend` (PEP-668 system; the plugin auto-locates it).
- **SwiftBar** (`brew install --cask swiftbar`), running; `PluginDirectory` → `display/swiftbar/`.
- **launchd agent** `com.tokenspend.refresh` (`~/Library/LaunchAgents/com.tokenspend.refresh.plist`) runs `tokenspend --write-state` every 10 min (no network) so the bar stays fresh.
- Runtime files in `~/.config/tokenspend/`: `state.json`, `quota_cache.json`, `quota_calibration.json`, `window_calibration.json`, `plan.json`. Personal calibration inputs in repo `gitignored-data/` (never committed).
- Undo: `launchctl unload ~/Library/LaunchAgents/com.tokenspend.refresh.plist` · `pipx uninstall token-spend-consolidator` · `brew uninstall --cask swiftbar`.

## Quota↔token calibration — the active work
**Owner's method (correct):** the endpoint gives only %, so reverse-calculate $. Segment the quota curve into 5h sessions (from the Usage-for-Claude CSV); the **chat-free** ones (cross-referenced vs the chat-export timestamps) are pure Code, so `$/% = exact Code $ ÷ session-%`. True rate = **MAX** over Code-only sessions. Apply to all sessions → `chat = total − Code`. Reproduce: `PYTHONPATH=src python3 scripts/calibrate_quota.py [--save]` (reads `gitignored-data/`; `--save` writes `window_calibration.json` the menu bar reads).

**Findings (Max 5x era, Jun 6–28):** **~0.9M tokens ≈ 1% of the 5h session ≈ $1.20** (range 0.1–1.8M/% by model mix). Owner's **5:1 rule confirmed**: ~5% session ≈ 1% weekly. **Combined all-Claude ≈ $2,476** (Code $1,165 + est chat ~$1,311 ≈ ~$3,500/mo) vs ~$72 paid = **~34×**. Chat ≈ as big as Code. Method **blind-validated**: it detected today's heavy chat from the quota curve alone, before the fresh export confirmed it.

**⚠️ Why it's "not refined yet" (the open backlog):**
1. **Tier change unmeasured.** Max 5x→20x upgrade reset both counters **Jun 28 ~13:06 local** and ~4× the limits. The menu bar currently **×4-extrapolates** the Max-5x rate (labelled estimate). **Recalibrate on Max 20x:** after a genuinely **chat-free coding stretch on the new plan**, re-export the Usage-for-Claude CSV (`gitignored-data/quota-csv/`) + a fresh chat export (`gitignored-data/chat-exports/<date>/`), run `scripts/calibrate_quota.py --save`.
2. **Weekly chat clamps to $0 this week** (the mid-week reset means weekly% covers only since 13:06 while weekly Code spans 7d) — self-heals next Monday.
3. **Big variance (~8×) in $/%** — driven by model mix; the quota likely weights models differently than $ (Opus counts more than Haiku/cache-reads). A real refinement would be **per-model-weighted calibration** rather than one blended $/%.
4. **Session-window detection is heuristic** (reset = %-drop / gap / event); **sub-start is date-granular** (plan segment midnight, not the actual 13:06 upgrade time).
5. UI is plain SwiftBar text; estimates are order-of-magnitude by nature.

## Watch-outs
Hard-won invariants (de-dup `(message.id, requestId)`, don't-sum `usage.iterations`, cache TTL split, `cwd` basename, `<synthetic>`→$0, pricing-lives-in-JSON) are in **`AGENTS.md` → Gotchas**. Live logs append as you work, so the headline drifts a few $ between runs (expected). Never poll the quota endpoint (429s for hours).

## Sensible next steps (none urgent)
- **Recalibrate on Max 20x** once a chat-free coding stretch exists (item 1 above) — the highest-value refinement.
- Consider **per-model-weighted** quota calibration (item 3).
- Surface the combined estimate in `state.json` history for a trend; optional iOS widget (same read-only state contract).
- Cross-device aggregation (still Claude) — optional.
