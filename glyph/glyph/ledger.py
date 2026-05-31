"""Append-only emotional ledger for Glyph gate decisions.

Every gate evaluation writes one JSON line to ``$GLYPH_HOME/ledger.jsonl``.
The ledger is the durable record Seraphina's emotional engine reads to
understand the history of trust accrual and rejections.
"""
from __future__ import annotations
import datetime as _dt
import json
import os
from pathlib import Path
from typing import Optional

from .index import DEFAULT_ROOT


def _root(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root)
    env = os.environ.get("GLYPH_HOME")
    if env:
        return Path(env)
    return DEFAULT_ROOT


def ledger_path(root: Optional[Path] = None) -> Path:
    return _root(root) / "ledger.jsonl"


def _now_z() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def append(event: dict, *, root: Optional[Path] = None) -> Path:
    """Append a structured event to the ledger and return its path."""
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": _now_z(), **event}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return p


def read(*, root: Optional[Path] = None,
         name: Optional[str] = None,
         limit: Optional[int] = None) -> list[dict]:
    """Read ledger entries (newest last). Optionally filter by package name."""
    p = ledger_path(root)
    if not p.exists():
        return []
    out: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if name and rec.get("name") != name:
                continue
            out.append(rec)
    if limit is not None and limit > 0:
        out = out[-limit:]
    return out
