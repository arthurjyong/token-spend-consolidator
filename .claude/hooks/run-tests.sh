#!/usr/bin/env bash
# Stop hook: run the stdlib tests when a Claude Code session ends; block stopping
# (exit 2 → stderr fed back to the agent) if they fail, so regressions get fixed.
# Dependency-free: python3 is already required to run the tool. Respects
# stop_hook_active so it nudges at most once and can never wedge the session.
set -uo pipefail

input="$(cat)"
if printf '%s' "$input" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
out="$(PYTHONPATH=src python3 tests/test_valuation.py 2>&1 && PYTHONPATH=src python3 tests/test_plan.py 2>&1)"
if [ $? -eq 0 ]; then
  exit 0
fi

{ echo "tokenspend tests FAILED — fix before finishing:"; printf '%s\n' "$out"; } >&2
exit 2
