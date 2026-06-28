# AGENTS.md — token-spend-consolidator

Tool-agnostic orientation for any AI coding agent (Claude Code, Codex, Cursor, Copilot, …). Read this first. In Claude Code this file is imported by `CLAUDE.md`, which adds Claude-specific notes on top.

**Your role:** a careful steward of a deliberately tiny, dependency-free CLI. Favour honest, glanceable output over precision; keep the three layers separate; stay small (stdlib only).

## What this is
A small, local-first, single-user tool that answers: **"if I'd paid API rates for everything I actually used, what would it have cost?"** Claude-only today, designed to extend to other providers. Full design intent is in `docs/BLUEPRINT.md` — the hard decisions are made there; treat it as the spec and don't re-argue them.

## Architecture — three layers, kept separate
Data flows **collectors → valuation → consolidate**. A new provider touches only layer 1.
- `src/tokenspend/model.py` — `UsageRecord` + `TokenCounts`: the normalized shape every collector emits. e.g. `UsageRecord(provider="anthropic", surface="claude-code", model="claude-opus-4-8", timestamp=…, tokens=TokenCounts(input=12, output=340, cache_read=9001, cache_write_5m=120, cache_write_1h=0), source_ref="<msgid>:<reqid>", project="my-app")`.
- `src/tokenspend/collectors/` — per-source adapters; each emits `UsageRecord`s and exposes `collect()` + `name` / `coverage_note` / `report_line()`. Built: `claude_code_log.py` (LogCollector, exact, surface `claude-code`) and `anthropic_api_usage.py` (ApiUsageCollector, exact, surface `api` — the Anthropic Admin usage report). `registry.py` (`build_collectors`) decides which are active — **add a new provider/surface there**. `claude_code_log.py` is the canonical template to copy.
- `src/tokenspend/pricing/` — `anthropic_prices.json` (vendored, LiteLLM-compatible field names) + `resolve(model)`.
- `src/tokenspend/valuation.py` — `value(record) → usd`. Provider-agnostic; imports only `model` + `pricing`.
- `src/tokenspend/consolidate.py` — merges valued records into the headline + breakdowns; imports `model` + `valuation`.
- `src/tokenspend/state.py` — writes the small JSON that displays read (month + rolling-7-day windows, top projects, daily series); imports `consolidate` + `valuation`.
- `src/tokenspend/cli.py` — the `tokenspend` command; the **only** module that wires in `collectors` (via `build_collectors`).
- `display/swiftbar/tokenspend.5m.py` — read-only menu-bar plugin. **Displays only READ the state file** (blueprint §10) — never logs, never credentials. New display surfaces (iOS) follow the same contract.

**Layer rule (verifiable):** `valuation.py` and `consolidate.py` must NOT import from `collectors/`; only `cli.py` does.

## Gotchas — hard-won, non-obvious, do not relearn
- **Claude Code log schema:** each `~/.claude/projects/**/*.jsonl` line is a record; billed turns are `type=="assistant"` with `message.usage`. Keys: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, and crucially `cache_creation: {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}` — the TTL split that makes pricing exact.
- **NEVER sum `usage.iterations`** — it's a per-turn breakdown of the same totals and double-counts. Sum the top-level `message.usage`.
- **Always de-dup on `(message.id, requestId)`** before valuing — resumed sessions re-copy earlier rows (~11k of ~19k in testing).
- **Cache pricing:** cache read = 0.1× input, 5m write = 1.25×, 1h write = 2×. These multipliers are *fallbacks* in `valuation.py`, used only when a pricing entry omits explicit cache rates.
- **Pricing rates live in `src/tokenspend/pricing/`** — `litellm_prices.json` is the vendored LiteLLM base (don't hand-edit; regenerate with `python3 scripts/refresh_pricing.py`); `overrides.json` overlays and **wins** (custom / not-yet-upstream / verified-pinned rates, e.g. the Anthropic models). **Never restate the per-model $ numbers in prose; they drift.** Verify Anthropic rates against the `claude-api` skill on price/model changes.
- **Project label:** use the record's `cwd` basename (real folder name); the transcript *dir* name is a lossy path-encoding.
- **`<synthetic>` model rows** (system messages) price to $0 and are reported as *unpriced* — never folded silently into spend.
- **Anthropic API usage** (surface `api`) comes from the Admin usage report (`GET /v1/organizations/usage_report/messages`, grouped by model, daily buckets) and needs `ANTHROPIC_ADMIN_KEY` (`sk-ant-admin…`) in the environment. Its response fields map 1:1 to `TokenCounts` (`uncached_input_tokens`→input, `cache_creation.ephemeral_5m/1h`→cache_write_5m/1h). It's pay-as-you-go API spend, **disjoint** from subscription Claude Code logs — no double-count. No key → the app degrades to exact log-only.

## Run / test
```bash
PYTHONPATH=src python3 -m tokenspend             # headline + breakdowns over all local logs
PYTHONPATH=src python3 -m tokenspend --by month  # one breakdown; also --project / --since / --until / --plan-monthly N
PYTHONPATH=src python3 -m tokenspend --write-state  # refresh ~/.config/tokenspend/state.json for the menu bar
```
Tests are **stdlib-only (no pytest)**. Run both and read the output — don't assume success:
```bash
PYTHONPATH=src python3 tests/test_valuation.py && PYTHONPATH=src python3 tests/test_plan.py
```
**Definition of done** for a change: both test scripts pass *and* `python3 -m tokenspend` runs clean. The CLI headline is **not** a deterministic assert target — live logs append as you work, so the $ figure drifts a few dollars run-to-run. Point pass/fail at the tests; use the CLI only to prove it executes.

## Boundaries
- **NEVER** add a third-party runtime dependency (stdlib only — flag the need, don't add it).
- **NEVER** count usage without de-duping; **NEVER** sum `usage.iterations`; **NEVER** fold `<synthetic>` $0 rows into spend.
- **ASK FIRST** before changing pricing/cache constants, and before enabling the ToS-grey whole-account quota collector (off by default — see BLUEPRINT §12).
