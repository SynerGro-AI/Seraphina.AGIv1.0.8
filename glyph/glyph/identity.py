"""Native Glyph identity API.

Every "virgin" glyph package can call these to declare itself a citizen of
the Glyph ecosystem:

    import glyph
    glyph.assert_context()                      # raises if not running under Glyph
    glyph.register_self(__name__, cost=0.3)     # logs into .glyph-meta/

These calls are no-ops outside a Glyph-managed runtime (so a glyph module
remains importable for development/testing) unless `strict=True` is passed.
"""
from __future__ import annotations
import datetime as _dt
import json
import os
import warnings as _warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Set by operations.install() / sandbox.load_entrypoint() when a glyph runs
# under managed execution. Inspectable by glyph code via `glyph.context()`.
_ACTIVE: Optional["GlyphContext"] = None


@dataclass
class GlyphContext:
    name: str
    version: str
    location: Path
    environment: str = "seraphina"
    managed: bool = True

    @property
    def meta_dir(self) -> Path:
        return self.location / ".glyph-meta"


class ContextError(RuntimeError):
    pass


def _set_active(ctx: Optional[GlyphContext]) -> None:
    global _ACTIVE
    _ACTIVE = ctx


def context() -> Optional[GlyphContext]:
    """Return the currently-active Glyph context (or None)."""
    return _ACTIVE


def assert_context(strict: bool = False) -> Optional[GlyphContext]:
    """Confirm this code is executing inside the Glyph runtime.

    - In managed execution (via `glyph install` + loader), returns the context.
    - In non-managed execution (plain `python my_glyph.py`), returns None
      unless `strict=True`, which raises ContextError.
    """
    if _ACTIVE is not None:
        return _ACTIVE
    if strict:
        raise ContextError(
            "not running under Glyph runtime; install via `glyph install` "
            "or pass strict=False to allow dev mode"
        )
    return None


def register_self(component: str, *, cost: float = 0.0,
                  trust_delta: float = 0.0, note: str = "") -> None:
    """Append a usage/registration event to .glyph-meta/usage.jsonl.

    No-op if no active managed context.
    """
    ctx = _ACTIVE
    if ctx is None:
        return
    meta = ctx.meta_dir
    try:
        meta.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    event = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "component": component,
        "cost": cost,
        "trust_delta": trust_delta,
        "note": note,
        "pid": os.getpid(),
    }
    try:
        with (meta / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        # also bump aggregate trust score
        score_path = meta / "trust.json"
        score = {"score": 0.5}
        if score_path.exists():
            try:
                score = json.loads(score_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        score["score"] = max(0.0, min(1.0, score.get("score", 0.5) + trust_delta))
        score["updated"] = event["ts"]
        score_path.write_text(json.dumps(score, indent=2), encoding="utf-8")
    except OSError:
        return


def emit_signal(name: str, payload: Optional[dict] = None) -> None:
    """Append a structured signal event to ``.glyph-meta/signals.jsonl``.

    No-op (with a RuntimeWarning) if there is no active managed context.
    Signals are how .GL ``signal <name> ...`` statements (and host code) emit
    structured events that Seraphina (v0.5+) can subscribe to.
    """
    payload = dict(payload) if payload else {}
    ctx = _ACTIVE
    if ctx is None:
        _warnings.warn(
            f"glyph.emit_signal({name!r}) called outside a managed glyph context",
            RuntimeWarning,
            stacklevel=2,
        )
        return
    meta = ctx.meta_dir
    try:
        meta.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    event = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "name": name,
        "payload": payload,
    }
    try:
        with (meta / "signals.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        return
    # Also fan out to any in-process subscribers (Seraphina core, etc).
    try:
        from . import signals as _signals
        _signals.publish(name, payload)
    except Exception:  # noqa: BLE001 — never let pub/sub break identity calls
        pass
