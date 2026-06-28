<!-- Maintainers: this file is injected in full into EVERY Claude Code session. Keep it lean (target <150 lines incl. the @AGENTS.md import) and high-signal. Prune test: if removing a line wouldn't cause an agent to make a mistake, cut it. Orientation/architecture/gotchas → AGENTS.md; spec → docs/BLUEPRINT.md; history → for_claude/HANDOFF.md (all load separately). Treat steering edits like code: commit them with the behaviour they document, and resolve any contradiction to a single source in the same pass — the commit is the review. -->
@AGENTS.md

# CLAUDE.md — Claude Code specifics

`AGENTS.md` (imported above) is the shared orientation: what this is, the architecture, the gotchas, run/test, boundaries. Below is **only** what's specific to Claude Code.

## ⚠️ Path-keyed memory — run from this folder
Claude Code memory lives at `~/.claude/projects/<encoded-abs-path>/`. M0 was built from a *different* session (the Work-files hub, `…/Work`), so that history is recorded under the hub, not here. **Run Claude Code from inside this folder** so the project accrues its own memory. `for_claude/HANDOFF.md` bridges the gap — **read it first** for what's built, what's next, and why.

## Pricing & models
Before touching pricing or model facts, verify rates against the **`claude-api` skill** (current model ids, $/1M, cache multipliers). The actual numbers live in `pricing/anthropic_prices.json`, not in prose (see AGENTS.md → Gotchas) — don't restate them here.

## Doc map & precedence
Four committed files, **one canonical source per topic — don't duplicate:**
- `AGENTS.md` — orientation, architecture, gotchas, commands (any agent).
- `CLAUDE.md` (this file) — Claude-Code-specific notes.
- `for_claude/HANDOFF.md` — cross-session bridge: what's built + history. May be stale; lowest precedence.
- `docs/BLUEPRINT.md` — the locked product spec; read before any new milestone.

On conflict: **BLUEPRINT** wins on design intent; **AGENTS.md/CLAUDE.md** win on how the code runs today; **HANDOFF** defers to both. Pricing rates → `pricing/anthropic_prices.json`, never restated in prose.

## Working style here
- **Stay small.** This is deliberately tiny and dependency-free. Add an abstraction when the *second* provider actually lands, not before; don't reach for a library to save a few lines of stdlib.
- For **multi-layer / new-provider work** (touches `collectors/` + invariants + `consolidate` + tests), write a short plan to `docs/plans/<slug>.md` first — memory is path-keyed and sessions compact, so the plan file is what survives. Skip the plan for one-liners (bump a price, add a model id).
- Use the bundled **`/code-review`** on diffs touching the de-dup key or pricing multipliers; ask it for correctness gaps only, not style.
- Personal/owner context (subscription, machine-specific flags) lives in gitignored `CLAUDE.local.md`, not here.

## Next steps
See `for_claude/HANDOFF.md` → roadmap: M1 menu-bar display, vendor the full LiteLLM pricing file, Anthropic usage API collector, then the opt-in whole-account quota estimator (BLUEPRINT §6).
