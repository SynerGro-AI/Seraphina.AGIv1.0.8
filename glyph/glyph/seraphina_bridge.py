"""Opt-in Seraphina integration shim.

Seraphina (or any host process) can call ``attach(seraphina_obj)`` at startup
to expose the installed-glyph registry and wire emit_signal events into a
handler of its choice. Activation is gated by the ``SERAPHINA_AUTOLOAD_GLYPHS``
environment variable to keep startup side effects out of every Python import.

Typical usage in seraphina_core.py::

    from glyph.seraphina_bridge import attach
    attach(self)                # populates self.glyphs and self._glyph_sub_token

Nothing here imports any glyph code; only manifests are read.
"""
from __future__ import annotations
import os
from typing import Any, Callable, Optional

from . import registry as _registry
from . import signals as _signals

ENV_FLAG = "SERAPHINA_AUTOLOAD_GLYPHS"


def is_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").lower() in {"1", "true", "yes", "on"}


def attach(host: Any, *,
           on_signal: Optional[Callable[[str, dict], None]] = None,
           force: bool = False) -> dict:
    """Populate ``host.glyphs`` (registry) and optionally subscribe to signals.

    Returns a small summary dict. No-op (returns summary with enabled=False)
    when ``SERAPHINA_AUTOLOAD_GLYPHS`` is not truthy, unless ``force=True``.
    """
    if not force and not is_enabled():
        return {"enabled": False, "glyphs": 0, "subscribed": False}

    glyphs = _registry.discover()
    try:
        setattr(host, "glyphs", glyphs)
    except (AttributeError, TypeError):
        pass

    token = None
    if on_signal is not None:
        token = _signals.subscribe("*", on_signal)
        try:
            setattr(host, "_glyph_sub_token", token)
        except (AttributeError, TypeError):
            pass

    return {
        "enabled": True,
        "glyphs": len(glyphs),
        "subscribed": token is not None,
        "names": sorted(glyphs.keys()),
    }


def detach(host: Any) -> bool:
    """Remove the signal subscription previously created by ``attach``."""
    token = getattr(host, "_glyph_sub_token", None)
    if token is None:
        return False
    ok = _signals.unsubscribe(token)
    try:
        delattr(host, "_glyph_sub_token")
    except AttributeError:
        pass
    return ok
