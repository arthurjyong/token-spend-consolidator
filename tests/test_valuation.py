"""Valuation + dedup sanity checks. Run: PYTHONPATH=src python3 tests/test_valuation.py
(also works under pytest)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tokenspend.model import TokenCounts, UsageRecord
from tokenspend.pricing import resolve
from tokenspend.valuation import value


def _rec(model, **tok):
    return UsageRecord(
        provider="anthropic", surface="claude-code", model=model,
        timestamp="2026-06-01T00:00:00Z", tokens=TokenCounts(**tok),
        fidelity="exact", source_ref="x",
    )


def test_sonnet_full_breakdown():
    # 3e-6 in, 15e-6 out, 0.3e-6 read, 3.75e-6 write5m, 6e-6 write1h
    v = value(_rec("claude-sonnet-4-6", input=1000, output=500, cache_read=2000,
                   cache_write_5m=1000, cache_write_1h=1000))
    expected = (1000 * 3e-6 + 500 * 15e-6 + 2000 * 0.3e-6
                + 1000 * 3.75e-6 + 1000 * 6e-6)
    assert abs(v.usd - expected) < 1e-12, (v.usd, expected)
    assert v.priced and v.pricing_key == "claude-sonnet-4-6"


def test_prefix_fallback():
    # an unseen opus point-release still prices at the opus tier
    key, entry = resolve("claude-opus-4-9-20260601")
    assert key == "claude-opus-4-8" and entry is not None


def test_unknown_model_is_unpriced_not_zero_real_spend():
    v = value(_rec("<synthetic>", input=1000, output=1000))
    assert v.priced is False and v.usd == 0.0 and v.pricing_key is None


def test_opus_output_dominates():
    v = value(_rec("claude-opus-4-8", output=1_000_000))  # 1M output @ $25/1M
    assert abs(v.usd - 25.0) < 1e-9


def test_litellm_breadth_prices_other_providers():
    # vendoring the LiteLLM table means non-Anthropic models price with no code change
    for m in ("gpt-4o", "gemini-2.5-pro", "deepseek-chat"):
        key, entry = resolve(m)
        assert entry is not None and entry.get("input_cost_per_token", 0) > 0, m


def test_anthropic_overrides_pin_verified_rates():
    # overrides.json wins over the vendored base and pins the verified rates
    key, entry = resolve("claude-opus-4-8")
    assert key == "claude-opus-4-8"
    assert entry["input_cost_per_token"] == 5e-6 and entry["output_cost_per_token"] == 25e-6
    assert entry["cache_read_input_token_cost"] == 0.5e-6  # 0.1x input


def _run():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run()
