"""Pricing table: load the vendored rates and resolve a raw model id to an entry.

Provider-agnostic by construction. The base table is LiteLLM's vendored
model_prices_and_context_window.json (filtered to text LLMs — see
scripts/refresh_pricing.py), which prices OpenAI / Gemini / xAI / DeepSeek /
Anthropic and 100+ others with no code change. overrides.json overlays on top
and always wins (custom, not-yet-upstream, or verified-and-pinned rates).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PRICES_DIR = Path(__file__).resolve().parent
_OVERRIDES_FILE = "overrides.json"
_SKIP_KEYS = {"sample_spec"}  # LiteLLM's documentation template, not a model


def _load_into(table: dict[str, dict], path: Path) -> None:
    for key, entry in json.loads(path.read_text()).items():
        if key.startswith("_") or key in _SKIP_KEYS or not isinstance(entry, dict):
            continue
        table[key] = entry


@lru_cache(maxsize=1)
def _table() -> dict[str, dict]:
    table: dict[str, dict] = {}
    for jf in sorted(p for p in _PRICES_DIR.glob("*.json") if p.name != _OVERRIDES_FILE):
        _load_into(table, jf)
    overrides = _PRICES_DIR / _OVERRIDES_FILE
    if overrides.exists():
        _load_into(table, overrides)  # overrides always win
    return table


# Prefix fallbacks: every model in a tier shares the tier's pricing, so a raw id
# we don't have an exact entry for (e.g. a future opus point release) still prices
# correctly. Order matters — first match wins.
_PREFIX_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("claude-opus", "claude-opus-4-8"),
    ("claude-sonnet", "claude-sonnet-4-6"),
    ("claude-haiku", "claude-haiku-4-5"),
    ("claude-3-5-haiku", "claude-haiku-4-5"),
    ("claude-3-haiku", "claude-haiku-4-5"),
    ("claude-fable", "claude-fable-5"),
    ("claude-mythos", "claude-fable-5"),
)


def resolve(model: str) -> tuple[str | None, dict | None]:
    """Return (pricing_key, entry) for a raw model id, or (None, None) if unknown.

    Unknown models (e.g. "<synthetic>" system rows) price to nothing and are
    surfaced by the caller rather than silently counted as $0 of real spend.
    """
    if not model:
        return None, None
    table = _table()
    if model in table:
        return model, table[model]
    low = model.lower()
    for prefix, key in _PREFIX_FALLBACKS:
        if low.startswith(prefix) and key in table:
            return key, table[key]
    return None, None


def known_models() -> list[str]:
    return sorted(_table())
