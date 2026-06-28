# CLAUDE.md — token-spend-consolidator

Orientation for any Claude session working in this project. Read this first.

## What this is
A small, local-first tool that answers: **"if I'd paid API rates for everything I actually used, what would it have cost?"** Claude-only today, designed to extend to other providers. Full design intent is in `docs/BLUEPRINT.md` (the hard decisions are already made there — treat it as the spec).

## ⚠️ Path-keyed memory
This project was scaffolded and given its working M0 from a *different* Claude session (the Work-files hub, `…/Work`). Claude Code memory lives at `~/.claude/projects/<encoded-abs-path>/`, so that build history is recorded under the hub, not here. **Run Claude Code from inside this folder** so this project accrues its own memory going forward. `for_claude/HANDOFF.md` bridges the gap — read it for what was built and why.

## Architecture (three layers — keep them separate)
- `src/tokenspend/model.py` — `UsageRecord` + `TokenCounts` (the normalized shape every collector emits).
- `src/tokenspend/collectors/` — per-source adapters. `claude_code_log.py` is the only one implemented. New providers/surfaces are new collectors here and (almost) nothing else.
- `src/tokenspend/pricing/` — `anthropic_prices.json` (vendored, LiteLLM-compatible field names) + `resolve(model)`.
- `src/tokenspend/valuation.py` — `value(record) → usd`. Provider-agnostic; knows nothing about sources.
- `src/tokenspend/consolidate.py` — merges valued records into the headline + breakdowns.
- `src/tokenspend/cli.py` — the `tokenspend` command.

## Key facts learned the hard way
- **Claude Code log schema**: each `*.jsonl` line is a record; billed turns are `type=="assistant"` with `message.usage`. Usage keys: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, and crucially `cache_creation: {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}` — the TTL split that makes pricing exact. There's also a `usage.iterations` array: **do not sum it**, it's a per-turn breakdown of the same totals (double-counts).
- **De-dup is mandatory**: resuming a session copies earlier messages into the new transcript. Key on `(message.id, requestId)`. In testing this skipped ~11k duplicate rows out of ~19k.
- **Project label**: prefer the record's `cwd` basename (real folder name); the transcript *dir* name is a lossy path-encoding.
- **Pricing/caching** (per token, verified against the `claude-api` skill): cache read = 0.1× input, 5m write = 1.25×, 1h write = 2×. Opus 4.x $5/$25 per 1M, Sonnet 4.6 $3/$15, Haiku 4.5 $1/$5, Fable 5 $10/$50.
- `<synthetic>` model rows exist (system messages) — they price to $0 and are reported as unpriced, not silently counted.

## Run / test
```bash
PYTHONPATH=src python3 -m tokenspend --plan-monthly 200
PYTHONPATH=src python3 -m pytest -q        # or: python3 tests/test_valuation.py
```

## Owner context
Arthur is on **Claude Max** and barely touches the quota — so the interesting story is how far the API-equivalent number exceeds the subscription. Don't gate token spend anxiously. Prefers clear, glanceable output over billing-grade precision.

## Next steps
See `for_claude/HANDOFF.md` → Roadmap. Short version: M1 menu-bar display, vendor the full LiteLLM pricing file, Anthropic usage API collector, then the opt-in whole-account quota estimator (blueprint §6).
