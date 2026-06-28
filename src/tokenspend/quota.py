"""Whole-account quota estimate (opt-in, ToS-grey) — folds in non-Code Claude usage.

The Anthropic quota endpoint (/api/oauth/usage) reports only a *utilization %*,
never dollars. So we reverse-calculate, exactly as the owner intuited:

  - In a window where you used ONLY Claude Code, the quota % is moved entirely by
    usage we already measure exactly. So  $ per % = exact_Code_$ / seven_day_% .
  - The TRUE rate is the MAX "$ per %" ever seen — a window that also had chat
    makes Code look cheaper-per-%, so only Code-only windows reveal the real rate.
  - Then for the current window:  all-Claude ≈ seven_day_% × ($ per %), and
    chat ≈ all-Claude − exact Code.

This is the blueprint §6 whole-pool/residual math, self-calibrated from your own
behaviour instead of a guessed ceiling.

OFF BY DEFAULT. It reuses the Claude Code OAuth credential from a non-Claude-Code
tool — a grey area under Anthropic's ToS — and the endpoint is undocumented and
aggressively rate-limited (so we cache and call it rarely). Every number it
produces is an order-of-magnitude *estimate*, labelled as such.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_BETA = "oauth-2025-04-20"

_CONFIG_DIR = Path.home() / ".config" / "tokenspend"
CACHE_PATH = _CONFIG_DIR / "quota_cache.json"
CALIB_PATH = _CONFIG_DIR / "quota_calibration.json"
CACHE_TTL_MIN = 10  # the endpoint rate-limits hard; never call more often than this

# Bootstrap "$ per %" until your own Code-only weeks calibrate it. ~ $1,400/week at
# 100% on Max 20x is a wide-variance community anchor (blueprint §6). Self-cal wins.
ANCHOR_DOLLARS_PER_PCT = 14.0


@dataclass(frozen=True)
class QuotaReading:
    five_hour_pct: float
    seven_day_pct: float
    fetched: str          # ISO-8601 UTC of when the raw reading was obtained
    from_cache: bool
    note: str = ""


# ---- credential + HTTP ------------------------------------------------------

def read_oauth_token() -> str | None:
    """The Claude Code OAuth access token, from $ANTHROPIC_OAUTH_TOKEN or the macOS Keychain."""
    env = os.environ.get("ANTHROPIC_OAUTH_TOKEN")
    if env:
        return env
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout.strip())
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    oauth = data.get("claudeAiOauth") if isinstance(data.get("claudeAiOauth"), dict) else data
    tok = oauth.get("accessToken") if isinstance(oauth, dict) else None
    return tok or None


def _http_get(token: str) -> dict:
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": OAUTH_BETA,
        "anthropic-version": "2023-06-01",
        "User-Agent": "tokenspend/0.1",
    })
    with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310 (trusted host)
        return json.loads(resp.read().decode())


def parse_reading(raw: dict) -> tuple[float, float]:
    """(five_hour_%, seven_day_%) from the endpoint payload."""
    fh = ((raw.get("five_hour") or {}).get("utilization")) or 0.0
    sd = ((raw.get("seven_day") or {}).get("utilization")) or 0.0
    return float(fh), float(sd)


# ---- tiny json helpers ------------------------------------------------------

def _load(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _save(path: Path, obj: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))


def _age_min(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60.0


# ---- fetch (cache-first; the endpoint 429s if polled) -----------------------

def fetch_usage(token: str | None = None, *, cache_path: Path = CACHE_PATH,
                ttl_min: float = CACHE_TTL_MIN, getter=None) -> QuotaReading | None:
    """Return a quota reading. Reuses a fresh cache without calling; on a live
    failure (429/expired/offline) falls back to any cached reading; returns None
    only when there is neither a token nor a cache."""
    cache = _load(cache_path)

    def from_cache(note: str) -> QuotaReading | None:
        if not cache or "raw" not in cache:
            return None
        fh, sd = parse_reading(cache["raw"])
        return QuotaReading(fh, sd, cache.get("fetched", ""), True, note)

    age = _age_min(cache.get("fetched")) if cache else None
    if age is not None and age < ttl_min:
        return from_cache("cached (fresh)")

    token = token or read_oauth_token()
    if not token:
        return from_cache("no OAuth token found; cached")

    try:
        raw = (getter or _http_get)(token)
    except urllib.error.HTTPError as e:
        reason = "rate-limited (429)" if e.code == 429 else (
            "token expired — open Claude Code to refresh" if e.code == 401 else f"HTTP {e.code}")
        return from_cache(f"live call {reason}; cached")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return from_cache(f"live call failed ({e}); cached")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save(cache_path, {"raw": raw, "fetched": now})
    fh, sd = parse_reading(raw)
    return QuotaReading(fh, sd, now, False, "")


# ---- calibration ("$ per %", taking the max from Code-only weeks) -----------

def update_calibration(code_7d_usd: float, seven_day_pct: float, *,
                       calib_path: Path = CALIB_PATH) -> tuple[float, bool]:
    """Fold this window's (code_$ / 7d_%) into the running MAX "$ per %".
    Returns (dollars_per_pct, calibrated) — calibrated=False means no data yet
    (fall back to the anchor)."""
    calib = _load(calib_path) or {}
    best = float(calib.get("dollars_per_pct") or 0.0)
    if seven_day_pct > 0 and code_7d_usd > 0:
        ratio = code_7d_usd / seven_day_pct
        if ratio > best:
            best = ratio
            _save(calib_path, {
                "dollars_per_pct": best,
                "calibrated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "from_code_7d_usd": round(code_7d_usd, 2),
                "at_seven_day_pct": seven_day_pct,
                "note": "max $ per % seen; raised on Code-heavy weeks (your true ceiling)",
            })
    return (best, True) if best > 0 else (ANCHOR_DOLLARS_PER_PCT, False)


def estimate(code_7d_usd: float, reading: QuotaReading, dollars_per_pct: float) -> dict:
    """Whole-pool/residual estimate for the rolling 7-day window."""
    rate = dollars_per_pct
    combined_7d = reading.seven_day_pct * rate
    # combined can't be less than what we already measured exactly
    combined_7d = max(combined_7d, code_7d_usd)
    chat_7d = max(0.0, combined_7d - code_7d_usd)
    return {
        "dollars_per_pct": rate,
        "ceiling_week": rate * 100.0,          # $ of API-equivalent value at 100% quota
        "five_hour_pct": reading.five_hour_pct,
        "seven_day_pct": reading.seven_day_pct,
        "exact_code_7d": code_7d_usd,
        "combined_7d": combined_7d,
        "chat_7d": chat_7d,
        "combined_month_proj": combined_7d / 7.0 * 30.0,
    }
