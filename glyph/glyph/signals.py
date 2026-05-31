"""In-process pub/sub for Glyph signals.

Used by `glyph.identity.emit_signal` and the `signal <name>` .GL statement.
Seraphina (or any host) can `subscribe(name, fn)` to react to events from
installed glyphs. Synchronous, deterministic, dependency-free.

This module is intentionally minimal — no async, no threads, no priority
queues. v0.5 = wire it up; smarter routing arrives with the emotional engine.
"""
from __future__ import annotations
from typing import Callable, Optional
import threading
import warnings as _warnings

# name -> list of (token, callback)
_SUBS: dict[str, list[tuple[int, Callable[[str, dict], None]]]] = {}
_LOCK = threading.RLock()
_NEXT_TOKEN = 0


def subscribe(name: str, fn: Callable[[str, dict], None]) -> int:
    """Register a subscriber for signal `name` (use `"*"` for wildcard).

    Returns a token suitable for ``unsubscribe(token)``.
    """
    global _NEXT_TOKEN
    with _LOCK:
        _NEXT_TOKEN += 1
        token = _NEXT_TOKEN
        _SUBS.setdefault(name, []).append((token, fn))
        return token


def unsubscribe(token: int) -> bool:
    """Remove a subscription by token. Returns True if a sub was removed."""
    with _LOCK:
        for name, subs in list(_SUBS.items()):
            kept = [(t, f) for (t, f) in subs if t != token]
            if len(kept) != len(subs):
                if kept:
                    _SUBS[name] = kept
                else:
                    del _SUBS[name]
                return True
        return False


def publish(name: str, payload: Optional[dict] = None) -> int:
    """Dispatch a signal to all matching subscribers (exact + wildcard).

    Returns the number of subscribers invoked. Exceptions in subscribers are
    caught and surfaced as warnings — one bad listener cannot break the bus.
    """
    payload = dict(payload) if payload else {}
    with _LOCK:
        targets = list(_SUBS.get(name, ())) + list(_SUBS.get("*", ()))
    n = 0
    for _, fn in targets:
        try:
            fn(name, payload)
        except Exception as e:  # noqa: BLE001 — bus must never raise
            _warnings.warn(f"glyph signal subscriber raised: {e!r}", RuntimeWarning)
        n += 1
    return n


def subscribers(name: Optional[str] = None) -> int:
    """Count subscribers (for diagnostics / `glyph doctor`)."""
    with _LOCK:
        if name is None:
            return sum(len(v) for v in _SUBS.values())
        return len(_SUBS.get(name, ()))


def _reset_for_tests() -> None:
    """Test helper — clear all subscriptions."""
    global _NEXT_TOKEN
    with _LOCK:
        _SUBS.clear()
        _NEXT_TOKEN = 0
