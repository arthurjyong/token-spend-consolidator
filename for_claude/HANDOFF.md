# HANDOFF — token-spend-consolidator

This bridges the gap created by path-keyed Claude memory: the project was started from the **Work-files hub** session (`/Volumes/Acer FA200 4TB/Work`), so the build conversation lives under the hub's memory, not this folder's. When you open a fresh session **from this folder**, start here.

## Where it came from
Arthur dropped `docs/BLUEPRINT.md` into the hub's Inbox and asked for "something to estimate my spending on tokens — how much would it have cost had I gone by API instead of subscription. Claude only now, maybe other platforms later." Built 2026-06-28.

## What was built (M0, working)
A dependency-free Python package implementing the blueprint's three layers, plus a CLI that reads `~/.claude/projects/**/*.jsonl` and prints the API-equivalent cost of all Claude Code usage. Runs today:

```bash
PYTHONPATH=src python3 -m tokenspend --plan-monthly 200
```

## First real run (Arthur's actual logs, 2026-05-29 → 2026-06-28)
- **~$1,138 API-equivalent**, 1.01B tokens, ~7,900 billed messages, ~11,000 duplicate rows correctly skipped.
- Opus 4.8 = 86% of spend. Biggest projects: my-app (~$635), M&M, PACES, the de-identified decks.
- vs $200/mo Max over 2 months ($400 paid) → **~2.8× ahead.** (Claude Code alone; chat not yet counted.)

These match expectations: heavy Opus use on my-app, and the Max subscription is a clear win.

## State of the layers
- ✅ `model.py`, `pricing/` (vendored Anthropic, LiteLLM-shaped), `valuation.py`, `collectors/claude_code_log.py`, `consolidate.py`, `cli.py`, one test.
- ⛔ Not built: any other collector, the menu-bar/iOS display, the state file, the quota estimator.

## Roadmap (blueprint milestones)
1. **M1 — Glance.** Write a small state JSON + a SwiftBar/xbar plugin that just prints the headline. Display only reads the file (blueprint §10–11).
2. **Vendor the real LiteLLM `model_prices_and_context_window.json`** (WebFetch + drop into `pricing/`, periodic refresh). Field names already match, so valuation needs no change. Add an `overrides.json`.
3. **ApiUsageCollector** for the Anthropic Admin usage/cost API (exact API spend) — proves the second collector type and the plugin model.
4. **QuotaCollector (opt-in, OFF by default).** `GET /api/oauth/usage` whole-account quota % → the whole-pool/residual math in blueprint §6 to fold in opaque chat usage without double-counting. ToS-grey (§12) — keep it an explicit toggle.
5. **Cross-device + second provider (OpenAI)** to prove the abstraction (blueprint §13 M3–M4).

## Watch-outs (also in CLAUDE.md)
- De-dup on `(message.id, requestId)` — non-negotiable; resumed transcripts duplicate rows.
- Don't sum `usage.iterations` (double-counts the turn totals).
- Cache-write TTL split (`ephemeral_5m`/`ephemeral_1h`) → 1.25× / 2× input. Cache read 0.1×.
- Use `cwd` basename for project labels.
- Live sessions append to logs as you work, so the headline drifts a few dollars between back-to-back runs — expected.

## Open question for Arthur
Which subscription tier to hard-code as the default comparison (Max 20x = $200/mo? Max 5x = $100?). Currently passed via `--plan-monthly`; default could be set once confirmed.
