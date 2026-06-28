# token-spend-consolidator

**One number: if you'd paid API rates for everything you actually used, what would it have cost?**

A small, honest spend gauge. Exact where it can be (local logs with real token counts), transparently estimated where it can't, and every component labelled which one it is. Built from `docs/BLUEPRINT.md`.

Today it answers that question for **Claude Code** usage — read straight from the transcripts under `~/.claude/projects/`, which record the exact tokens Anthropic billed (including the cache-write TTL split). That makes the Claude Code number **exact**, not a guess.

## Quick start

No dependencies — pure Python stdlib (3.10+).

```bash
# from the repo root
PYTHONPATH=src python3 -m tokenspend
```

Or install the `tokenspend` command:

```bash
pip install -e .
tokenspend
```

### Examples

```bash
tokenspend                      # headline + by-model + by-project + by-month
tokenspend --by month           # just the monthly trend
tokenspend --project my-app   # filter to one project
tokenspend --since 2026-06-01   # date window
tokenspend --plan-monthly 200   # quick: compare against a flat $200/mo
```

For an accurate subscription comparison when your plan changed over time, drop a `plan.json` next to the tool (or at `~/.config/tokenspend/plan.json`) — see `plan.example.json`. It lists each fee and the date it took effect; the tool pro-rates the active fee day-by-day across your usage window. `tokenspend` picks it up automatically.

## Menu bar (glance)

Keep the number ambient in your macOS menu bar:

```bash
tokenspend --write-state        # writes ~/.config/tokenspend/state.json
brew install --cask swiftbar    # then point SwiftBar at display/swiftbar/
```

The plugin (`display/swiftbar/tokenspend.5m.py`) shows this month's API-equivalent spend in the bar, with a dropdown for the rolling 7-day total, a 14-day sparkline, and top projects. By design the **display only reads the state file** — it never touches your logs or any credential (blueprint §10), which is what makes the upcoming iOS widget trivial. Refresh the data on a schedule (e.g. `*/15 * * * * tokenspend --write-state`) or with the dropdown's "Refresh now".

## What it shows

- **Headline**: total API-equivalent dollars, always split into `exact` + `estimated`.
- **By model / project / month**: where the spend went.
- **vs subscription**: API-equivalent ÷ what you actually paid → how far ahead you are.

## How the money math works

Every billed assistant message in the logs carries `input`, `output`, `cache_read`, and `cache_creation` tokens (the last split into 5-minute and 1-hour cache writes). Each is multiplied by its rate from the vendored pricing table (`src/tokenspend/pricing/anthropic_prices.json`):

| Token type | Rate (× input) |
|---|---|
| input | 1× |
| output | (separate output rate) |
| cache read | 0.1× |
| cache write, 5-minute TTL | 1.25× |
| cache write, 1-hour TTL | 2× |

Rows that resume an earlier session are de-duplicated by `(message id, request id)` so the same billed turn is never counted twice.

## Architecture (three layers)

1. **collectors/** — per-source adapters that emit a normalized `UsageRecord`. `ClaudeCodeLogCollector` is implemented; `ApiUsageCollector` / `QuotaCollector` / `ManualCollector` are the documented next adapters.
2. **valuation** — `value(record) → usd`, provider-agnostic, driven by the pricing table.
3. **consolidate** — merges + de-duplicates into the headline number and breakdowns.

A new provider touches only layer 1 (+ maybe a pricing entry). See `docs/BLUEPRINT.md`.

## Known limitations (be honest)

- **Claude Code only, for now.** API usage and consumer-chat are not yet counted. The headline says "Claude Code alone" so it's never oversold.
- **Exact-only mode.** No quota/chat estimation yet — `estimated` is always $0 today. The whole-account quota estimate (blueprint §6) is deliberately deferred and will be opt-in.
- **Pricing is vendored, not live.** Numbers are current as of the file's `_meta.source` date; field names mirror LiteLLM's `model_prices_and_context_window.json` so the full multi-provider file can be dropped in later.

## Roadmap

See `for_claude/HANDOFF.md` for current state and next steps (LiteLLM vendoring, Anthropic usage API, the opt-in quota estimator, iOS widget). The menu-bar glance (M1) ships above.

MIT licensed. Single-user, local-first.
