"""LogCollector for Claude Code — reads ~/.claude/projects/**/*.jsonl.

Each assistant record carries the exact usage Anthropic billed, including the
cache-write TTL split. Fidelity is "exact". We de-duplicate across files because
resuming a session copies earlier messages into the new transcript.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

from ..model import TokenCounts, UsageRecord

DEFAULT_ROOT = Path.home() / ".claude" / "projects"

PROVIDER = "anthropic"
SURFACE = "claude-code"


def _decode_project_dir(name: str) -> str:
    """The dir name is the encoded absolute path (every '/'+space -> '-').

    We can't reverse it unambiguously, so just return a readable tail: the last
    path-ish segment. Good enough as a grouping label.
    """
    return name.rsplit("-", 1)[-1] or name


def _token_counts(usage: dict) -> TokenCounts:
    cc = usage.get("cache_creation") or {}
    write_5m = cc.get("ephemeral_5m_input_tokens")
    write_1h = cc.get("ephemeral_1h_input_tokens")
    if write_5m is None and write_1h is None:
        # Older/edge records without the split: treat the lump as a 5m write
        # (the default TTL) rather than dropping it.
        write_5m = usage.get("cache_creation_input_tokens", 0) or 0
        write_1h = 0
    return TokenCounts(
        input=usage.get("input_tokens", 0) or 0,
        output=usage.get("output_tokens", 0) or 0,
        cache_read=usage.get("cache_read_input_tokens", 0) or 0,
        cache_write_5m=write_5m or 0,
        cache_write_1h=write_1h or 0,
    )


class ClaudeCodeLogCollector:
    """Walks the Claude Code transcript tree and yields exact UsageRecords."""

    def __init__(self, root: Path | str | None = None, device: str | None = None):
        self.root = Path(root) if root else DEFAULT_ROOT
        self.device = device or os.uname().nodename
        # de-dup ledger: a usage row can recur across resumed transcripts
        self._seen: set[str] = set()
        self.stats = {"files": 0, "rows": 0, "deduped": 0, "no_usage": 0}

    def collect(self) -> Iterator[UsageRecord]:
        if not self.root.exists():
            return
        for jf in sorted(self.root.rglob("*.jsonl")):
            self.stats["files"] += 1
            project = _decode_project_dir(jf.parent.name)
            yield from self._read_file(jf, project)

    def _read_file(self, path: Path, project: str) -> Iterator[UsageRecord]:
        try:
            fh = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            return
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict) or msg.get("role") != "assistant":
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    self.stats["no_usage"] += 1
                    continue

                # De-dup key: (message id, request id) is how the same billed turn
                # is identified across resumed transcripts; fall back to record uuid.
                msg_id = msg.get("id")
                req_id = rec.get("requestId") or rec.get("request_id")
                dedup = f"{msg_id}|{req_id}" if msg_id else rec.get("uuid", "")
                if dedup:
                    if dedup in self._seen:
                        self.stats["deduped"] += 1
                        continue
                    self._seen.add(dedup)

                # Prefer the record's real working directory for a clean project
                # label; fall back to the (lossy) decoded transcript-dir name.
                cwd = rec.get("cwd")
                label = Path(cwd).name if cwd else project

                self.stats["rows"] += 1
                yield UsageRecord(
                    provider=PROVIDER,
                    surface=SURFACE,
                    model=msg.get("model") or "",
                    timestamp=rec.get("timestamp"),
                    tokens=_token_counts(usage),
                    fidelity="exact",
                    source_ref=msg_id,
                    device=self.device,
                    project=label,
                )
