# HANDOFF — token-spend-consolidator

Cross-session bridge. Claude Code memory is path-keyed, and M0 was built from the Work-files hub session (`…/Work`), so that build conversation lives under the hub, not this folder. Opening a fresh session from here: start with this file, then `AGENTS.md`.

## Goal
Ship `docs/BLUEPRINT.md` incrementally: a local-first tool that consolidates "what my AI usage would have cost at API rates." Claude-only today; the architecture exists to add providers cheaply.

## Status (2026-06-28)
- ✅ **Built (M0 + plan-history comparison):** `model.py`, `pricing/` (vendored Anthropic, LiteLLM-shaped) + `resolve`, `valuation.py`, `collectors/claude_code_log.py`, `consolidate.py`, `plan.py`, `cli.py`; tests `test_valuation.py`, `test_plan.py`. Runs: `PYTHONPATH=src python3 -m tokenspend`.
- ✅ **Built (M1 — Glance):** `state.py` writes `~/.config/tokenspend/state.json` (month + rolling-7-day windows, top projects, 30-day daily series; atomic write) via `tokenspend --write-state`; `display/swiftbar/tokenspend.5m.py` is a read-only menu-bar plugin (month headline, 7-day, sparkline, top projects, staleness, Refresh-now). Test `test_state.py`. Decoupling per BLUEPRINT §10: the display only reads the file.
- ⛔ **Not built:** any second collector, the iOS widget, cross-device aggregation, the quota estimator.
- **First real run** (Arthur's logs, 2026-05-29 → 2026-06-28): ~$1,143 API-equivalent, 1.01B tokens, ~7,900 billed messages, ~11k duplicate rows correctly skipped. Opus 4.8 ≈ 86% of spend; biggest project my-app (~$635). vs ~$84 actually paid over the window = **~13.6× ahead** (Claude Code alone; chat not yet counted).

## Decisions + why
- **Subscription comparison is plan-history aware**, not a flat fee. Arthur's plan changed mid-window, so a flat $200 was wrong (it gave a misleading ~2.8×). `plan.py` models time-varying segments pro-rated daily (monthly×12/365); `plan.json` config is auto-detected from `./plan.json` or `~/.config/tokenspend/plan.json` (`plan.example.json` is the committed template; the real `plan.json` is gitignored). Arthur's history: Pro $20/mo → Max 5x $100/mo (6 Jun) → Max 20x $200/mo (28 Jun). Correct result ≈ $84 paid → **~13.6×**.
- **Steering layer reorganised** (2026-06-28, research-backed): tool-agnostic orientation + gotchas → `AGENTS.md`; Claude-specifics → thin `CLAUDE.md` (`@AGENTS.md`); personal context → gitignored `CLAUDE.local.md`; one canonical source per topic; a `Stop` hook runs the stdlib tests. Rationale + the practices deliberately rejected as overhead are in `docs/research/steering-practices.md`.

## Dead-ends / watch-outs
The hard-won invariants (de-dup key, don't-sum-`iterations`, cache TTL split, `cwd` basename, `<synthetic>` rows, pricing-lives-in-JSON) are in **`AGENTS.md` → Gotchas** — read them there, not duplicated here. Also: live sessions append to logs as you work, so the headline drifts a few dollars between back-to-back runs (expected — don't chase it).

## Next step / roadmap
1. **Vendor the real LiteLLM `model_prices_and_context_window.json`** + an `overrides.json` (field names already match, so valuation is unchanged).
2. **M2 — ApiUsageCollector** for the Anthropic Admin usage/cost API — proves the second collector type and the plugin model.
3. **QuotaCollector (opt-in, OFF by default).** `GET /api/oauth/usage` whole-account % → the whole-pool/residual math (BLUEPRINT §6) to fold in opaque chat usage without double-counting. ToS-grey (§12) — keep it an explicit toggle.
4. **Cross-device + a second provider (OpenAI)** to prove the abstraction (BLUEPRINT §13 M3–M4).
5. **iOS widget** (Scriptable or WidgetKit) reading the published state — same read-only contract as the menu bar.
