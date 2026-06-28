# Token Spend Consolidator — Build Blueprint

A design spec to hand to Claude Code. No implementation here on purpose — this defines
*what to build and why*, with the hard decisions already made, so the build is mechanical.

---

## 1. North Star

One headline number, always visible:

> **"If I paid API rates for everything I actually used — across every AI provider and every
> surface — this is what it would cost."**

Money out. Consolidated across all sources. **Exact where it can be, honestly estimated where
it can't, and every component labelled which one it is.** The estimate doesn't need to be
precise; it needs to be *defensible and transparent*.

The app is deliberately small and "useless" — a glanceable spend gauge, not a billing system.

## 2. Non-goals (keep scope honest)

- Not real-time, invoice-grade accuracy. Order-of-magnitude on the estimated parts is fine.
- Not a replacement for any provider's own dashboard.
- Not a proxy/router/gateway. It *observes* usage; it never sits in the request path.
- Not a SaaS. Single-user, local-first, open source.

## 3. The three layers

Everything hangs off a clean split. This split is what makes the app both honest and extensible.

1. **Collectors** — per-provider, per-surface adapters that read usage from wherever it lives and
   emit a normalized record. Pluggable.
2. **Valuation engine** — turns normalized usage into dollars using a shared pricing table.
   Provider-agnostic; knows nothing about *where* usage came from.
3. **Consolidator + Display** — merges all collector output, de-duplicates, fills estimate gaps,
   produces the headline number + breakdown, writes it to a small state file. Display surfaces
   (menu bar, iOS) only read that file.

A new provider touches only layer 1 (and sometimes a one-line pricing override). Layers 2 and 3
never change. That is the whole extensibility story.

## 4. Normalized data model

The unifying fact across *every* LLM provider: they all bill on **tokens, by type, per model**.
So every collector, regardless of provider, emits the same record shape.

**UsageRecord**
- `provider` — e.g. `anthropic`, `openai`, `google`, `xai`, `deepseek`
- `surface` — where it happened: e.g. `claude-code`, `claude-chat`, `api`, `chatgpt-app`
- `model` — provider's model id, normalized to the key the pricing table uses
- `timestamp`
- `device` — which machine reported it (for cross-device de-dup)
- `tokens` — `{ input, output, cache_read, cache_write, reasoning }` (any may be 0/absent)
- `fidelity` — `exact` | `estimated` (this propagates all the way to the UI)
- `source_ref` — opaque id (e.g. requestId/sessionId) used for de-duplication

That's it. If a collector can fill `tokens` exactly, the record is `exact`. If it can only infer
spend from a quota signal or a heuristic, it's `estimated` and may carry a dollar value directly
instead of token counts (see §6).

## 5. Collector taxonomy

This is the core abstraction. There are only **four kinds** of collector, defined by *what signal
the source exposes*. Every present and future provider/surface maps onto one of them.

| Collector type | Reads | Fidelity | Example |
|---|---|---|---|
| **LogCollector** | Local log files with real token counts | exact | Claude Code `~/.claude/projects/*.jsonl` |
| **ApiUsageCollector** | Provider's own usage/billing API (needs a key) | exact | Anthropic Admin Usage/Cost API; OpenAI usage API; xAI / DeepSeek / Google billing |
| **QuotaCollector** | A utilization %/quota signal — *no token counts* | estimated | Anthropic `GET /api/oauth/usage` (returns 5h + 7d utilization %) |
| **ManualCollector** | User-entered figures or a usage heuristic | estimated | Any consumer chat app that exposes nothing |

**Collector contract (all four implement the same interface):**
- Input: a time window.
- Output: `{ records: [UsageRecord...], fidelity, coverage_note }` where `coverage_note` is a
  short human-readable string for the methodology view (e.g. "exact, from local logs, this device
  only" or "estimate, derived from whole-account quota %").

A **provider module** simply declares: its `provider` id, its model-name normalization, and a map
of `surface → collector type` for each surface it supports. The registry discovers provider
modules; nothing else needs to know they exist.

### Honest reality this taxonomy encodes
- **API usage is always retrievable and exact.** Every provider has a usage/billing endpoint.
- **Agentic-CLI usage is exact** where the CLI writes local logs with token counts (Claude Code).
- **Consumer chat is almost never token-exposed by anyone.** Claude is unusual in exposing even a
  whole-account quota %. ChatGPT / Gemini / Grok / DeepSeek consumer apps generally expose nothing,
  so their `*-chat` surfaces fall to ManualCollector. **Set expectations accordingly:** the app is
  most accurate for API + agentic-CLI usage; consumer-chat is best-effort.

## 6. The money math (consolidation methodology)

This is the part to document *inside the app* (a "Methodology" view — see §8). Spell it out.

**Per provider, consolidated value for a window =**

**(a) Sum of exact components.** Every `exact` record → dollars via the valuation engine (§7),
summed across devices, de-duplicated by `source_ref`. This covers logs + API usage.

**(b) Plus estimated components.** Two sub-cases:

- *Provider has a QuotaCollector (Anthropic today).* The quota % is **whole-account** — it already
  includes the exact components above plus everything invisible (chat, other devices). So:
  - `whole_pool_estimate = (utilization% / 100) × calibrated_ceiling`
  - `invisible_portion (≈ chat) = whole_pool_estimate − exact_components`
  - This is how exact Code usage and opaque chat usage consolidate into **one** number *without
    double-counting*: subtract the exact part you can already see from the whole-pool estimate.
  - **Ceiling calibration:** `calibrated_ceiling` = the API-dollar value of a *full* window at
    100%. Bootstrap from a published community anchor (≈ **$1,400/week at 100% on Max 20x** — wide
    variance, one data point). Refine automatically: during windows where the only thing moving the
    quota % is the exact log activity (i.e. `exact_components ≈ all activity`), fit
    `ceiling = exact_$ ÷ (utilization% / 100)` and store a running estimate. Show *both* the anchor
    and the user's own calibrated value in the methodology view.

- *Provider has only ManualCollector.* Use whatever the user entered / the heuristic produced. If
  nothing, the surface contributes $0 and is flagged "no signal" so the user isn't misled.

**Across providers:** just add each provider's consolidated value. No cross-provider interaction.

**Headline output:**
- Big number: `Σ provider consolidated values`.
- Always paired with a split: `≈ $A exact + ≈ $B estimated`.
- Drill-down: per provider, per surface, with each line tagged exact/estimated.

Graceful degradation: with only a LogCollector wired up, the app still works — it shows exact
Code spend and nothing fictional. Each added collector widens coverage.

## 7. Valuation engine (pricing backend)

**Adopt LiteLLM's `model_prices_and_context_window.json` as the pricing source.**
(github.com/BerriAI/litellm — the same file ccusage and ccost use.)

- It already prices OpenAI, Anthropic, Gemini/Vertex, xAI Grok, DeepSeek, and 100+ others, keyed by
  a normalized `litellm_provider` + model name.
- It has the granular fields this app needs: `input_cost_per_token`, `output_cost_per_token`,
  `cache_read_input_token_cost`, `cache_creation_input_token_cost`, reasoning-token and
  batch/flex tiers.
- **Adding a provider's models is usually zero-code** — the rates are already in the file.
- Vendor a copy for offline use + refresh periodically (ccusage-style). Provide a small
  **overrides file** for models not yet upstream or for custom rates.

Engine interface: `value(UsageRecord) → usd`. It looks up `(provider, model)` in the pricing table,
multiplies each token type by its rate, sums. Provider-agnostic by construction.

## 8. Transparency is a feature, not a footnote

The user explicitly wants the methodology visible. Make it first-class:

- Every number in the UI carries its `exact`/`estimated` tag.
- A **Methodology view** that states, per active source: how the number was obtained, the ceiling
  value and where it came from (anchor vs self-calibrated), and the key assumptions/limitations.
- The headline always shows the exact-vs-estimated split so a glance tells you how solid it is.

This honesty is also the app's main differentiation (see §12) — own it.

## 9. Cross-device consolidation

- Each device runs its own LogCollector and writes device-keyed records to a **shared state store**
  (see §10). An aggregator sums exact components across devices and de-duplicates by `source_ref`.
- The QuotaCollector is **device-independent** (whole-account), so a single call from any one
  device covers it — don't multiply it per device.

## 10. State store + display decoupling

- The collector/consolidator process writes a small JSON: latest consolidated totals + a short
  history series. Optionally also pushes it to a **private published URL** (private Gist,
  Cloudflare Worker KV, S3 object, or iCloud) for remote displays.
- **Displays only read this state** — they never call provider APIs or touch credentials. This
  keeps all secrets on the collector host and makes new display surfaces trivial.

## 11. Display adapters (also pluggable)

- **macOS menu bar** — primary. Simplest path is a SwiftBar/xbar plugin (a script that prints the
  bar text); a native `MenuBarExtra` app is a later polish option.
- **iOS** — a widget that *reads the published state URL*. Build it in Scriptable (JavaScript, no
  Xcode) for near-zero effort, or native WidgetKit for portfolio polish. iOS never holds
  credentials and never calls the provider — it just renders the number the Mac published.
- **CLI** — a one-shot "print current consolidated spend" command falls out for free.

## 12. Known limitations (put these in the README)

- **Consumer-chat coverage is weak by nature.** Most providers expose no per-token chat data;
  Claude's whole-account quota % is the exception. The app is accurate for API + agentic-CLI usage
  and best-effort for chat. Don't oversell it.
- **The Anthropic QuotaCollector is a grey area.** It reuses the Claude Code OAuth credential from a
  non-Claude-Code tool, and the endpoint is undocumented (can break or be locked anytime). Anthropic's
  Feb 2026 ToS restricts that token to Claude Code/claude.ai. **Make this collector an explicit
  opt-in toggle.** With it off, the app runs in a fully ToS-clean, exact-only mode (logs + API). With
  it on, you gain the chat estimate. User's choice, clearly stated.
- **The estimated portion is order-of-magnitude.** The ceiling has wide variance; surface it as a
  range, not a precise figure.
- **Pricing drifts.** Refresh the LiteLLM data; flag staleness.
- **Prior art exists** (multi-provider menu-bar spend monitors and Claude usage meters already ship,
  some commercial). Position this as open-source/learning, and differentiate on the *honest,
  self-documenting consolidation* — the part the existing tools don't do well.

## 13. Suggested build order (milestones for Claude Code)

- **M0 — Core spine.** Data model + LiteLLM valuation engine + one LogCollector (Claude Code) →
  a CLI that prints exact Code spend. Smallest thing that's already useful and proves valuation.
- **M1 — Glance.** State store + menu-bar display (SwiftBar) showing exact Code spend.
- **M2 — Consolidation + honesty.** Anthropic QuotaCollector (opt-in) + the §6 whole-pool/residual
  math + Methodology view. Now the headline = "all my Anthropic usage, in dollars."
- **M3 — Cross-device.** Multi-device aggregation + de-dup.
- **M4 — Prove the abstraction.** Add a second provider via ApiUsageCollector (e.g. OpenAI API) —
  this is the test that the provider plugin model actually works. Add the iOS Scriptable widget
  reading the published state.
- **M5 — Polish.** Packaging, refresh logic, docs, the "add a provider" guide (§14).

If M4 lands cleanly with minimal new code, the architecture succeeded.

## 14. "Add a new provider" recipe (the extensibility promise, concretely)

For the next person who wants Gemini / Grok / ChatGPT / DeepSeek:

1. **Write a provider module** declaring: `provider` id, model-name normalization, and a
   `surface → collector type` map.
2. **Wire the collector(s):**
   - API usage available? → configure an **ApiUsageCollector** pointed at that provider's
     usage/billing endpoint + key. (Exact. This is the common case and the easiest.)
   - Local logs with token counts? → a **LogCollector** with the parse rules.
   - Only a consumer app with no signal? → a **ManualCollector** (and document the gap).
3. **Pricing:** confirm the models exist in the LiteLLM table (usually yes) or add an override.
4. **Register** the module in config.

Valuation, consolidation, cross-device, state store, and every display surface keep working
unchanged. That's the design paying off.

## 15. Decisions (locked 2026-06-28)

- **Stack — LOCKED: Python core + SwiftBar.** Python for the core (M0 already is; matches the
  ccusage/LiteLLM ecosystem). The M1 menu bar is a SwiftBar Python plugin (a script that prints the
  bar text). A native Swift `MenuBarExtra` app is deferred to a later polish milestone.
- **Vendor vs fetch pricing — LOCKED: vendor + periodic refresh.** Vendor the LiteLLM file for
  offline use, refresh on a cadence, plus an `overrides.json` for gaps.
- **Accounting window — LOCKED: calendar month (headline) + rolling 7-day (secondary).** Month is
  how people read a bill; the 7-day figure also lines up with the Anthropic 5h/7d quota signal added
  in M2.
- **Default fidelity mode — LOCKED: quota collector OFF by default, opt-in.** Ships exact-only and
  ToS-clean; the whole-account estimate is an explicit toggle with a clear explanation (§12).
- **Publish target for the iOS state URL — DEFERRED to M4** (Gist vs Worker KV vs iCloud vs S3); not
  needed until the iOS widget exists. Decide when M4 starts.

## 16. Steering & docs layer (how this repo is built)

This project is built and maintained almost entirely by AI coding agents, so the steering files are
the primary control surface — treat them like code. **One canonical source per topic, no duplication:**

- `AGENTS.md` — tool-agnostic orientation: architecture, hard-won gotchas, run/test, boundaries (any agent).
- `CLAUDE.md` — Claude-Code-specific notes; imports `AGENTS.md`.
- `for_claude/HANDOFF.md` — cross-session bridge (what's built + history); may be stale.
- `docs/BLUEPRINT.md` (this file) — the locked product spec; read before any milestone.
- `CLAUDE.local.md` (gitignored) — personal/owner context.

**Precedence on conflict:** this blueprint wins on design intent; `AGENTS.md`/`CLAUDE.md` win on how the
code runs today; `HANDOFF` defers to both. Pricing rates live only in `pricing/anthropic_prices.json`,
never restated in prose. A committed `Stop` hook runs the stdlib tests as a deterministic backstop.

The practices behind this split — and what was deliberately rejected as overhead for a tool this small —
are documented in `docs/research/steering-practices.md`.
