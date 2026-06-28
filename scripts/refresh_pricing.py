#!/usr/bin/env python3
"""Refresh the vendored LiteLLM pricing table.

Downloads LiteLLM's model_prices_and_context_window.json, filters it to
token-billed text LLMs (the only thing valuation.py can price), and writes it to
src/tokenspend/pricing/litellm_prices.json. Stdlib only — no install needed.

  python3 scripts/refresh_pricing.py

Field names already match valuation.py, so refreshing never needs a code change.
Custom or pinned rates live in pricing/overrides.json (which wins over this file)
— don't hand-edit the vendored file; it's overwritten on every refresh.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, timezone, datetime
from pathlib import Path

URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
OUT = Path(__file__).resolve().parents[1] / "src" / "tokenspend" / "pricing" / "litellm_prices.json"

# valuation.py prices input/output/cache TOKENS. Keep modes billed that way; drop
# image/audio/embedding/etc. so a model id can never match a non-token entry.
KEEP_MODES = {"chat", "completion", "responses"}


def _keep(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("mode") in KEEP_MODES:
        return True
    # entries without a declared mode but priced on input+output tokens
    return "mode" not in entry and "input_cost_per_token" in entry and "output_cost_per_token" in entry


def main(url: str = URL) -> int:
    print(f"fetching {url}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (trusted upstream)
        raw = json.loads(r.read().decode())
    raw.pop("sample_spec", None)

    kept = {k: v for k, v in raw.items() if _keep(v)}
    out = {
        "_meta": {
            "note": ("Vendored from LiteLLM, filtered to token-billed text LLMs "
                     "(modes: chat/completion/responses). Field names match valuation.py. "
                     "Do not hand-edit — regenerate with scripts/refresh_pricing.py. "
                     "Custom/pinned rates go in overrides.json, which takes precedence."),
            "source": url,
            "fetched": datetime.now(timezone.utc).date().isoformat(),
            "entries": len(kept),
            "dropped_non_text": len(raw) - len(kept),
        },
    }
    for k in sorted(kept):
        out[k] = kept[k]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT}  ({len(kept)} entries, dropped {len(raw) - len(kept)} non-text)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else URL))
