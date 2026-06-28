# HANDOFF — token-spend-consolidator

Cross-session bridge. Claude Code memory is path-keyed, and M0 was built from the Work-files hub session (`…/Work`), so that build conversation lives under the hub, not this folder. Opening a fresh session from here: start with this file, then `AGENTS.md`.

## Goal
Ship `docs/BLUEPRINT.md` incrementally: a local-first tool that consolidates "what my AI usage would have cost at API rates." Claude-only today; the architecture exists to add providers cheaply.

## Status (2026-06-28)
- ✅ **Built (M0 + plan-history comparison):** `model.py`, `pricing/` (vendored Anthropic, LiteLLM-shaped) + `resolve`, `valuation.py`, `collectors/claude_code_log.py`, `consolidate.py`, `plan.py`, `cli.py`; tests `test_valuation.py`, `test_plan.py`. Runs: `PYTHONPATH=src python3 -m tokenspend`.
- ✅ **Built (M1 — Glance):** `state.py` writes `~/.config/tokenspend/state.json` (month + rolling-7-day windows, top projects, 30-day daily series; atomic write) via `tokenspend --write-state`; `display/swiftbar/tokenspend.5m.py` is a read-only menu-bar plugin (month headline, 7-day, sparkline, top projects, staleness, Refresh-now). Test `test_state.py`. Decoupling per BLUEPRINT §10: the display only reads the file.
- ✅ **Built (M2 — second collector + registry):** `collectors/anthropic_api_usage.py` (ApiUsageCollector, surface `api`) reads the Anthropic Admin usage report (`GET /v1/organizations/usage_report/messages`); fields map 1:1 to `TokenCounts`, fidelity exact. `collectors/registry.py` (`build_collectors`) is the single wiring point; `cli.py` no longer hard-wires a collector. Gated on `ANTHROPIC_ADMIN_KEY` (graceful exact-only fallback; bad key → skipped, headline intact). Test `test_api_collector.py` (mock-based: mapping, pagination, errors, valuation). Disjoint from subscription Claude Code logs — no double-count.
- ✅ **Built (whole-account estimate — opt-in, ToS-grey):** `quota.py` + `tokenspend --quota`. Reads the Claude Code OAuth token from the macOS Keychain → `GET /api/oauth/usage` (returns utilization % only — `five_hour`/`seven_day`; no dollars). Reverse-calculates all-Claude spend: `$/% = max(exact Code $ ÷ 7-day %)` across weeks (Code-only weeks set the true ceiling — owner's insight), then `combined ≈ 7d% × $/%`, `chat ≈ combined − exact Code`. Cached + calibration persisted to `~/.config/tokenspend/` (endpoint 429s hard — never poll). OFF by default. Live-verified: 5h 75% / 7d 15%, ~$38/% → ceiling ≈ $3.8k/week. Chat shows $0 until a Code-only week calibrates a higher ceiling than a later chat week. Test `test_quota.py` (mock). Owner's goal here is a personal "feel-justified-about-the-$200" number, not precision — keep it simple.
- ⛔ **Not built:** the iOS widget, cross-device aggregation. (Other *providers* intentionally out of scope — see `claude-only-scope` memory.)
- **First real run** (Arthur's logs, 2026-05-29 → 2026-06-28): ~$1,143 API-equivalent, 1.01B tokens, ~7,900 billed messages, ~11k duplicate rows correctly skipped. Opus 4.8 ≈ 86% of spend; biggest project my-app (~$635). vs ~$84 actually paid over the window = **~13.6× ahead** (Claude Code alone; chat not yet counted).

## Decisions + why
- **Subscription comparison is plan-history aware**, not a flat fee. Arthur's plan changed mid-window, so a flat $200 was wrong (it gave a misleading ~2.8×). `plan.py` models time-varying segments pro-rated daily (monthly×12/365); `plan.json` config is auto-detected from `./plan.json` or `~/.config/tokenspend/plan.json` (`plan.example.json` is the committed template; the real `plan.json` is gitignored). Arthur's history: Pro $20/mo → Max 5x $100/mo (6 Jun) → Max 20x $200/mo (28 Jun). Correct result ≈ $84 paid → **~13.6×**.
- **Steering layer reorganised** (2026-06-28, research-backed): tool-agnostic orientation + gotchas → `AGENTS.md`; Claude-specifics → thin `CLAUDE.md` (`@AGENTS.md`); personal context → gitignored `CLAUDE.local.md`; one canonical source per topic; a `Stop` hook runs the stdlib tests. Rationale + the practices deliberately rejected as overhead are in `docs/research/steering-practices.md`.

## Dead-ends / watch-outs
The hard-won invariants (de-dup key, don't-sum-`iterations`, cache TTL split, `cwd` basename, `<synthetic>` rows, pricing-lives-in-JSON) are in **`AGENTS.md` → Gotchas** — read them there, not duplicated here. Also: live sessions append to logs as you work, so the headline drifts a few dollars between back-to-back runs (expected — don't chase it).

## Next step / roadmap
1. ✅ **Done — LiteLLM pricing vendored.** `pricing/litellm_prices.json` (LiteLLM, filtered to text LLMs, 2376 models) refreshed via `scripts/refresh_pricing.py`; `pricing/overrides.json` overlays/pins (Anthropic models verified vs claude-api). Non-Anthropic models now price with no code change.
2. ✅ **Done — M2 ApiUsageCollector + registry** (see Status). The collector type and provider/surface plugin model are proven.
3. ✅ **Done — whole-account quota estimate** (`quota.py`, `--quota`; see Status). The blueprint §6 residual math + §12 opt-in toggle are implemented.
4. **Surface the quota estimate in the menu bar / state** (optional) — fold the `--quota` combined number into `state.json` so SwiftBar can show "all-Claude (est.)". Keep it clearly labelled estimate.
5. **iOS widget** (Scriptable or WidgetKit) reading the published state — same read-only contract as the menu bar.
6. **Calibration polish** (only if it bugs you): the chat residual needs a Code-only week to set the ceiling before it shows non-zero; could seed/blend the community anchor, or weight recent samples. Low priority — it self-corrects with use.

## Quota↔token calibration — findings & workbench (in progress)
Personal inputs live in `gitignored-data/` (**never committed**): `chat-exports/<date>/` (claude.ai export → chat timestamps), `quota-csv/` (Usage-for-Claude app → Export CSV → minute-res Session%/Weekly%), `screenshots/`. Reproduce: `PYTHONPATH=src python3 scripts/calibrate_quota.py`.

**Method (owner's insight):** the quota endpoint gives only %, never $. Segment the quota curve into 5h sessions; the chat-free ones (cross-referenced vs chat-export timestamps) are pure Code, so `$/% = exact Code $ ÷ session-%`. True rate = **MAX** over Code-only sessions (a session with chat looks cheaper-per-%). Apply to all sessions → `chat = total − Code`.

**Findings (Max 5x era, Jun 6–28):**
- **~0.9M tokens ≈ 1% of the 5h session (≈ $1.20)**; range 0.1–1.8M/% (model mix).
- Owner's **5:1 rule confirmed** (today's post-reset 72%:14%): ~5% session ≈ 1% weekly → 1% weekly ≈ ~4M tok ≈ $6; full week ≈ ~450M tok ≈ $600.
- **Combined all-Claude ≈ $2,476** (Code $1,165 + est chat ~$1,311) ≈ ~$3,500/mo; vs ~$72 paid (Max 5x) = **~34×**. Chat ≈ as big as Code.
- **Validated:** method blind-detected today's heavy chat (the export didn't contain it) purely from the quota curve.

**⚠️ TIER CAVEAT:** a % is usage÷limit. The Max 5x→20x upgrade **reset both counters Jun 28 13:06 local** and ~4× the limits, so per-% is ~4× higher on Max 20x (≈3–4M tok/% session, ≈17M/% weekly) — **UNVERIFIED** until a Code-only session on the new plan. Re-export both files after a chat-free coding stretch to recalibrate.

**✅ BUILT — $-denominated menu-bar UI** (mirrors "Usage for Claude" but in $). `state.build_windows` + `cli._windows_for_state` compute session/week/since-sub windows; the SwiftBar plugin shows exact Code $ in the bar (no network) and the combined-incl-chat estimate in the dropdown (on-demand quota fetch via "Refresh + chat estimate"). Boundaries from the cached quota reset times; sub-start from the current plan segment date. Chat layer needs `scripts/calibrate_quota.py --save` (writes `~/.config/tokenspend/window_calibration.json`); the tool tier-scales the rate (×4 Max5x→Max20x, labelled estimate). Refresh: `tokenspend --write-state` (no network) / `--write-state --quota` (one live call). KNOWN ARTIFACT: the weekly chat estimate clamps to $0 this week because the mid-week upgrade reset the weekly counter (so weekly% covers only since Jun28 13:06 while weekly Code spans 7d) — self-heals next Monday / after Max-20x recalibration. See memory `claude-only-scope`.

**Scope (2026-06-28):** Claude-only — this is Arthur's personal tool for his own (Claude) usage. **Don't build other-provider collectors** (OpenAI/Gemini; former blueprint M4) unless asked. The multi-provider extensibility (LiteLLM pricing + collector registry) stays as a free architectural property. The most relevant remaining Claude work is the opt-in claude.ai chat/quota estimator (#4), which captures his *Claude consumer* usage. Cross-device aggregation (multiple Macs, still Claude) is optional. See memory `claude-only-scope`.
