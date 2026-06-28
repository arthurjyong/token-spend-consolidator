<!-- Reference doc, not steering. Loaded on demand only — never @imported into CLAUDE.md. -->

# Research — steering-file best practices (provenance)

Generated 2026-06-28 by a multi-agent research workflow (6 parallel web-survey angles → dedup → adversarial per-practice verification against primary sources → synthesis). Funnel: 96 raw candidate practices → 34 canonical → 33 verified (9 adopt / 24 adapt / 0 skip-as-wrong). Primary sources include Anthropic's Claude Code docs (memory, best-practices, context-engineering), the AGENTS.md standard (now under the Linux Foundation), GitHub's 2,500-repo study, and 2026 academic work on config smells/instruction-following. The adopted subset is reflected in `AGENTS.md`, `CLAUDE.md`, `for_claude/HANDOFF.md`, and `docs/BLUEPRINT.md` §16.

---

# Steering-file best practices for `token-spend-consolidator`

Audience: Arthur, deciding what to adopt before (re)writing this project's steering docs. The project is a tiny, dependency-free, single-user, open-source Python CLI, built and maintained *almost entirely by Claude Code sessions* — so the steering files are not documentation, they are the primary control surface. The current `CLAUDE.md` (36 lines) is already close to best-in-class; most recommendations below are "keep doing this, formalize it, fix two drifts" rather than "rewrite."

## 1. TL;DR

- **You're already 90% there. Don't rewrite — guard and prune.** A 36-line `CLAUDE.md` with detail offloaded to `BLUEPRINT.md`/`HANDOFF.md` is exactly what Anthropic's own docs prescribe (target <200 lines, ruthless pruning) [1][2]. The highest-value moves are tiny: kill the drift, add a couple of guardrails, reorder.
- **Fix the live drift now.** `CLAUDE.md` pastes pricing rates that the canonical `pricing/anthropic_prices.json` owns, and `HANDOFF.md` carries a stale "~2.8× / $1,138" headline (line 18) that its own line 41 corrects to "~13.6×". These are the two most-cited failure modes — restated-data drift and conflicting instructions [1][6]. Replace pasted numbers with pointers; one canonical source per topic [1][6].
- **Reorder, don't restructure.** The runnable commands sit at the very bottom; the two correctness landmines (de-dup key, don't-sum-`iterations`) are buried mid-prose. Commands-early + dangerous-rules-prominent is the one near-free win [5][2].
- **Add AGENTS.md as a thin, lean bridge — split, don't symlink.** Since this is open-source, a contributor's Codex/Cursor/Copilot currently reads *nothing*. Put the tool-agnostic orientation in `AGENTS.md` (~40 lines), keep Claude-Code-specifics in `CLAUDE.md`, and make line 1 of `CLAUDE.md` be `@AGENTS.md` [1][7][8].
- **Enforce the one real invariant with one hook, not prose.** A `Stop` hook that runs the dependency-free tests is the single deterministic guardrail worth adding for an ephemeral-session, agent-maintained repo [1][11]. Skip everything else hook/CI-shaped.
- **Reject the enterprise toolkit explicitly.** No nested per-dir files, no `.claude/rules/`, no lint/format hooks, no PR/branch ceremony, no custom subagent files, no coverage gates, no auto-memory-writeback loop. At ~10 source files in one package, all of that is overhead with no payoff [16][2].

## 2. Verified practices

### ADOPT — keep doing it, lightly formalize

**Keep files short, high-signal, and prune ruthlessly (<200 lines).** *What:* every line must earn its place; bloat makes the agent ignore the rules that matter. *Breadth:* widely adopted — verbatim Anthropic policy ("target under 200 lines"; the prune test "would removing this cause a mistake? if not, cut it") [1][2], corroborated by HumanLayer (<60-line root) [4] and a June-2026 study finding "Context Bloat" in 42% of 100 mined repos [6]. *Fit:* amplified here — the files *are* the interface and agents tend to append over time. *Apply:* you already comply (36 lines). Lock it in with a zero-token block-level HTML comment near the top (Claude strips `<!-- … -->` before injection, but it stays visible to any agent that opens the file to edit it) [25]: a one-line "keep this <150 lines, prune test, detail goes to BLUEPRINT/HANDOFF" note. Do **not** `@import` the 240-line `BLUEPRINT.md` — imports load in full at launch [1].

**Include only non-inferable content (the include/exclude test).** *What:* record gotchas, project-specific decisions, env quirks, exact commands; exclude anything discoverable from code, standard conventions, and frequently-changing data [2]. *Breadth:* widely adopted — near-verbatim Anthropic Include/Exclude table [2]; "Lint Leakage" found in 62% of repos [6]. *Fit:* pays off *more* with no human reviewer — a duplicated fact that drifts silently misleads the next agent. *Apply:* your "Key facts learned the hard way" section is the model done right (keep it). Trim the most self-evident line (`cli.py — the tokenspend command`); keep contract lines (`valuation.py is provider-agnostic`).

**Prefer pointers over pasted copies; never restate volatile data.** *What:* link to the source of truth (with a `file:line` or path) instead of copying [1][4][9]; know that `@import` loads in full, a backtick path does not [1]. *Breadth:* widely adopted; pydantic's `genai-prices` `CLAUDE.md` does exactly this ("NEVER edit the generated data file") [16]. *Fit:* the project's core domain *is* pricing data that must never drift. *Apply (load-bearing fix):* `CLAUDE.md` line 23 pastes the rate table (`Opus $5/$25 … Fable $10/$50`) and multipliers that already live in `src/tokenspend/pricing/anthropic_prices.json` and `valuation.py`. Replace with a pointer: "Per-token rates + 5m/1h cache split live in `pricing/anthropic_prices.json`; the 0.1×/1.25×/2× multipliers are fallbacks in `valuation.py`. Never restate the numbers here — they drift." Keep the *logic* rules (de-dup key, don't-sum-iterations) inline; they aren't a copy of anything.

**Capture hard-won gotchas and non-obvious invariants.** *What:* the traps a cold read can't reveal are the highest-value lines [2]. *Apply:* keep "Key facts" as-is; add a one-line vendored-file invariant ("`pricing/*.json` is vendored upstream data — never hand-edit; refresh by re-import + bump a date") ahead of the roadmap's "vendor the full LiteLLM file" step, and anchor each gotcha to a cheap re-check (e.g. "asserted in `tests/test_valuation.py`; verified against the `claude-api` skill").

**Write concrete rules at the right altitude; phrase as imperatives + alternatives.** *What:* GitHub's headline finding — "most agent files fail because they're too vague" [5]; pair every prohibition with the right path, reserve bare "NEVER" for true correctness boundaries [13][5]. *Apply:* convert "keep them separate" → "`valuation.py`/`consolidate.py` must not import from `collectors/`." Rewrite "do not sum it" → "Sum the top-level `message.usage` totals; **NEVER** sum `usage.iterations` — it double-counts." Convert "De-dup is mandatory" → "Always de-dup on `(message.id, requestId)` before valuing — resumed sessions re-copy rows (~11k/19k in testing)."

**Use emphasis (IMPORTANT / YOU MUST) sparingly.** *What:* a few all-caps markers improve adherence; if everything is IMPORTANT, nothing is [2]. *Apply:* reserve it for the 2-3 silently-wrong traps (de-dup, don't-sum-iterations). Don't emphasize the architecture list or pricing. Phrase calmly — current models over-trigger on aggressive language [13].

**Include exact, runnable commands.** *What:* "bash commands Claude can't guess" is Anthropic's #1 include [2][5]. *Fit:* acute here — no Makefile/pyproject scripts, so the `PYTHONPATH=src` prefix and `python3 -m tokenspend` module-run are genuinely non-discoverable. *Apply:* keep the `PYTHONPATH=src` prefix on every command (don't abbreviate); add new CLI flags as milestones land.

**Remove contradictory instructions; one canonical source per topic.** *What:* if two rules conflict the agent picks one arbitrarily, run-to-run [1]; "Conflicting Instructions" is a named smell [6]. *Apply (fix):* strike the stale "~2.8× / $1,138" headline in `HANDOFF.md` line 18 so only the corrected "~13.6×" remains; make `HANDOFF.md`'s "Watch-outs" a pointer to `CLAUDE.md`'s "Key facts" rather than a second copy. Add a short precedence note (see §3).

### ADAPT — take the cheap core, drop the ceremony

**Treat steering files like code (iterate, prune, validate by behavior).** Adapt the team parts: there are no PRs here, so "the commit is the review" — commit `CLAUDE.md`/`HANDOFF.md` edits alongside the behavior they document [2]. The old `#` in-session shortcut is gone; capture via "add this to CLAUDE.md", `/memory`, or auto-memory [27][1]. Add a 1-line "Maintaining this file" note: time-sensitive lines (pricing, roadmap) rot first — re-verify pricing against the `claude-api` skill on new model releases.

**Progressive disclosure + match the mechanism to the goal.** Keep the lean always-on file plus on-demand pointers — you already do this [1][14][26]. *Adapt:* do **not** pre-build `.claude/skills/` or `.claude/rules/` now. Pre-commit to the one trigger that matters: the project's stated growth path is *more providers*, so when a "Key facts" bullet becomes a multi-step procedure (the Claude-Code-log parse + de-dup + TTL-pricing playbook), extract it to `.claude/skills/add-collector/SKILL.md` — not before the second collector lands [6][26].

**Cross-session continuity via committed files.** This is the project's defining quirk and the practice pays off by *number of sessions*, not lines of code [1][3]. Keep the handoff *out* of `CLAUDE.md` (just point to it). Give `HANDOFF.md` a stable structure each session: Goal / Status / Decisions+WHY / Dead-ends / Next step. Note: 2026 auto-memory is now git-repo-keyed (shared across worktrees) so the path-keying pain is *partly* solved — but auto-memory is machine-local and uncommitted, so `HANDOFF.md` stays the durable, clonable bridge [1].

**AGENTS.md as the cross-tool standard; CLAUDE.md a thin bridge.** The standard is real and widely adopted (donated to the Linux Foundation's Agentic AI Foundation, Dec 2025) [7][8], and Claude Code still does **not** read `AGENTS.md` natively — so the bridge is mandatory, not optional [1]. *Adapt — split, don't blanket-symlink:* ~half your current `CLAUDE.md` is Claude-Code-specific (path-keyed memory, `~/.claude/projects/**`, the `claude-api` skill, the `HANDOFF.md` bridge). Put only tool-agnostic content in a lean `AGENTS.md` (~40-50 lines: "what this is", the three-layer map, run/test commands, the provider-not-tool-specific gotchas). Make `CLAUDE.md` line 1 `@AGENTS.md` and keep the Claude-specifics below it. Keep `AGENTS.md` lean — every tool pays its token cost [1][7].

**Order by priority — commands early, dangerous rules prominent.** At 36 lines, lost-in-the-middle *within* the file is moot; brevity matters more [3]. But the cheap misalignment is real: move the `## Run / test` block up near the top (it's currently last), and promote the two correctness-critical rules to the first bullets of "Key facts" or a tiny `## Must not break` block [5][18].

**Definition of done — run the check, show evidence.** Anthropic's top-listed practice: give the agent a check it can run and require it to show output, not assert success [2][20]. *Two real gaps to fix:* `python3 -m pytest -q` is listed first but **pytest isn't installed** (it fails); and the dependency-free fallback runs only `test_valuation.py` while `test_plan.py` is silently skipped. Rewrite the section: run **both** `PYTHONPATH=src python3 tests/test_valuation.py` and `tests/test_plan.py`, then smoke-run the CLI. Crucial tailoring: the CLI headline is **not** a deterministic assertion target — live logs make it drift a few dollars run-to-run (per `HANDOFF.md` line 38) — so point pass/fail at the tests/fixtures, CLI only to prove it executes.

**Enforce the one must-happen rule with a hook (CLAUDE.md is advisory).** Anthropic: instructions are advisory, only hooks are deterministic [1][11]. *Adapt narrowly:* the project's non-negotiables are *semantic* (de-dup, don't-sum-iterations, cache multipliers) — hooks can't judge those, but the tests do. Add a committed `.claude/settings.json` with a `Stop` hook running the two stdlib tests (zero new deps; the gate auto-releases after 8 blocks so it can't wedge). Committing it is the point — it survives the ephemeral/path-keyed quirk. Do **not** add lint/format hooks (no formatter, stdlib-only ethos) or write-protect the pricing JSON (the roadmap updates it) [1][11].

**Boundaries (Always / Ask-first / Never).** The "Never" tier is high-value here because the tool's whole job is a correct dollar figure [5]. *Apply a short block, skip the enterprise Always tier:* NEVER sum `usage.iterations`; NEVER count without de-duping; NEVER fold `<synthetic>` $0 rows into spend; NEVER add a third-party runtime dependency. ASK FIRST: before enabling the ToS-grey `QuotaCollector` (off by default, BLUEPRINT §12); before changing pricing/cache constants (verify vs `claude-api` skill).

**Counteract the over-engineering tendency.** The documented Opus failure mode (extra files, abstractions, reaching for libraries) is the single tendency worth naming for a deliberately-tiny tool [13]. *Apply:* a calm-prose "Stay small" note — stdlib only (flag, don't add, if you think you need a dep); add the abstraction when the *second* provider actually lands, not before; implement correct-for-all-valid-inputs in `valuation.py`, don't hard-code to the one test. Skip the no-comments rule (Claude Code already enforces it) [13].

**One focused role line + show-don't-tell example.** A single identity sentence is near-free and directly endorsed [13][5]; one canonical example beats prose about style [5][3]. *Apply:* one role line atop the file ("careful steward of a deliberately tiny, dependency-free CLI; honest glanceable output over precision; keep the three layers separate"). Upgrade the `model.py` bullet to show a small populated `UsageRecord` literal + "copy `collectors/claude_code_log.py` as the canonical collector template." Don't add a roster of per-layer personas or an exhaustive field rulebook.

**Memory scope + auto-memory separation.** Personal/machine content shouldn't sit in a committed, open-source file [1]. *Apply:* move the "Arthur is on Claude Max…" owner block and any machine-specific `--plan-monthly 200` to gitignored `CLAUDE.local.md` (or `~/.claude`); keep Arthur's prose-wrapping prefs where they already correctly live (`~/.claude/CLAUDE.md`). Add a 1-line note that committed `CLAUDE.md` + `HANDOFF.md` are the source of truth (they survive a fresh clone); auto-memory `MEMORY.md` is machine-local and does **not** replace `HANDOFF.md` [1].

**Explore→Plan→Code→Commit; persist the plan.** Adapt to scale: skip the plan for one-liners (bump a price, add a model id); write a short `docs/plans/<slug>.md` only for multi-layer/new-provider work (which genuinely touches `collectors/` + invariants + `consolidate` + tests) [2][12]. The rationale is project-specific: memory is path-keyed and sessions `/compact`, so a plan file is the only artifact that reliably survives.

**Fresh-eyes review via the bundled `/code-review`.** Use the already-bundled skill (no custom `.claude/agents/*.md` files) to review diffs touching the de-dup key and pricing multipliers; tell the reviewer to flag only correctness gaps, not style/speculation (a reviewer told to find gaps always will → over-engineering) [2][22].

**HTML comments for provenance/TODO.** Use `<!-- … -->` (stripped from context, zero tokens; visible on Read/Edit) for backstory, TODOs, and "re-verify pricing" notes — but keep all *operational* steering (run from this folder, read HANDOFF) as visible text [25].

### SKIP / REJECT (verified, but enterprise overhead for this tool)

- **Nested per-directory `CLAUDE.md` / `.claude/rules/`.** Scoped by every source to large/multi-area codebases; you have ~10 files in one package [12][2]. Record the trigger only: split out `collectors/CLAUDE.md` once `collectors/` holds 3+ providers with real quirks.
- **Full git/PR/branch-naming section + "install gh".** No remote exists; `gh` is already installed; the Co-Authored-By trailer and branch-first are already enforced by the harness. Adding it duplicates harness behavior [2][5]. (Revisit only if a GitHub remote is added.)
- **Automated `Stop`/`SessionEnd` memory-writeback loop.** Every working implementation calls the LLM via the `anthropic` library + API key — breaks the dependency-free promise and spends tokens, ironic in a token-spend tool [10][11]. Keep memory maintenance manual.
- **`InstructionsLoaded` hook / `claudeMdExcludes` / `--append-system-prompt`.** A monorepo debugging toolkit; verified there are no ancestor/nested/conflicting memory files here [1]. The one useful nugget: an `@for_claude/HANDOFF.md` import would *guarantee* the handoff loads (and shows in `/memory`) instead of hoping the agent reads it [1].
- **CI/coverage gates, MCP, plugins, agent teams, multi-persona stacks.** No team, no second repo, no service — pure overhead against the stated ethos [26][13].
- **Regenerating with `/init`.** The file is already curated; treat `/init` output (if ever used for a new section) as a skeleton to cut, not ship. A 2026 ETH study found redundant auto-generated context cut task success ~3% while raising cost ~20% [17].

## 3. What the project's steering layer should look like

Four files, **one canonical source per topic, no duplication**:

- **`AGENTS.md`** (~40-50 lines, new) — tool-agnostic entry point for *any* agent. Role line; "what this is"; the three-layer architecture map (`collectors/` → `valuation.py` → `consolidate.py`, plus `model.py`/`pricing/`/`cli.py`) with a small `UsageRecord` example; exact run/test commands; the provider-not-tool-specific gotchas (de-dup key, don't-sum-iterations, cache TTL split, `cwd` basename, `<synthetic>` rows). Canonical for orientation + gotchas.
- **`CLAUDE.md`** (~30-40 lines) — line 1 `@AGENTS.md`; below it only Claude-Code-specifics: the path-keyed-memory note + HANDOFF pointer, "verify pricing against the `claude-api` skill", the doc-map/precedence block, the maintenance guardrail (HTML comment), and a pointer to pricing data (no pasted numbers). Canonical for "how the code runs/tests today."
- **`for_claude/HANDOFF.md`** (~40 lines) — cross-session bridge only: Goal / Status / Decisions+WHY / Dead-ends / Next step. Watch-outs become a pointer to `CLAUDE.md`. Canonical for "what's built + history." May be stale; lowest precedence.
- **`docs/BLUEPRINT.md`** (~240 lines, unchanged) — the locked product spec. Read before any new milestone. Canonical for product/design intent; don't re-argue decisions elsewhere.

**Precedence rule** (add to `CLAUDE.md`, ~3 lines): on conflict, `BLUEPRINT.md` wins on design intent; `CLAUDE.md` wins on how the code runs today; `HANDOFF.md` defers to both. Pricing *rates* → `pricing/anthropic_prices.json`, never restated in prose.

**Maintenance rule** (1 line + HTML comment): treat these like code — commit steering edits with the behavior they document; prune on the prune-test; resolve contradictions to a single source in the same pass; keep `CLAUDE.md`/`AGENTS.md` lean (the commit is the review).

**Optional deterministic backstop:** committed `.claude/settings.json` with a `Stop` hook running both stdlib test scripts.

## 4. References

1. Anthropic — Claude Code memory: https://code.claude.com/docs/en/memory
2. Anthropic — Claude Code best practices: https://code.claude.com/docs/en/best-practices
3. Anthropic — Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
4. HumanLayer — Writing a good CLAUDE.md: https://www.humanlayer.dev/blog/writing-a-good-claude-md
5. GitHub — How to write a great AGENTS.md (lessons from 2,500+ repositories): https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/
6. arXiv 2606.15828 — Configuration Smells in AGENTS.md Files: https://arxiv.org/abs/2606.15828
7. AGENTS.md spec: https://agents.md/
8. Linux Foundation — Agentic AI Foundation formation: https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation
9. Phil Schmid — Writing good agents: https://www.philschmid.de/writing-good-agents
10. Anthropic — Claude Code hooks: https://code.claude.com/docs/en/hooks
11. Anthropic — Claude Code features overview: https://code.claude.com/docs/en/features-overview
12. Anthropic — Claude Code large codebases: https://code.claude.com/docs/en/large-codebases
13. Anthropic — Claude prompting best practices: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
14. Anthropic — Claude Code skills: https://code.claude.com/docs/en/skills
16. pydantic genai-prices CLAUDE.md (exemplar): https://github.com/pydantic/genai-prices/blob/main/CLAUDE.md
17. InfoQ — Coverage of the ETH Zurich agent context-file study (arXiv 2602.11988): https://www.infoq.com/news/2026/03/agents-context-file-value-review/
18. arXiv 2307.03172 — Lost in the Middle: https://arxiv.org/abs/2307.03172
20. Anthropic — Effective harnesses for long-running agents: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
22. Anthropic — Claude Code sub-agents: https://code.claude.com/docs/en/sub-agents
25. GitHub issue #32688 — HTML comments stripped from CLAUDE.md context: https://github.com/anthropics/claude-code/issues/32688
26. Anthropic — Steering Claude Code (skills, hooks, rules, subagents): https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
27. dev.to — Claude's memory feature and why the `#` prefix is gone: https://dev.to/rajeshroyal/the-prefix-claudes-memory-feature-and-why-you-dont-need-it-anymore-3ggn
