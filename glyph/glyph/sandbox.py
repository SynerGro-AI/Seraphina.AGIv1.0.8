"""Best-effort sandboxed loader.

⚠️ v0.1 sandbox is NOT a real security boundary. Filtered `__builtins__`
+ restricted `sys.modules` view only blocks accidental misuse. Treat all
.glyph code as semi-trusted and gate execution behind the emotional gate.
"""
from __future__ import annotations
import builtins
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Optional

from . import identity as _identity

# Modules a glyph may freely import (extend as needed).
# `glyph` is always allowed so packages can call identity APIs.
DEFAULT_ALLOWED_MODULES = frozenset({
    "math", "json", "re", "hashlib", "dataclasses", "typing",
    "collections", "itertools", "functools", "pathlib",
    "glyph",
})

# Builtins removed from the restricted environment.
_DENY_BUILTINS = frozenset({
    "open", "exec", "eval", "compile", "input",
    "__import__",  # replaced below
    "breakpoint", "help",
})


class SandboxError(Exception):
    pass


def _make_restricted_builtins(allowed: frozenset[str]) -> dict[str, Any]:
    safe = {k: v for k, v in vars(builtins).items() if k not in _DENY_BUILTINS}

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root not in allowed:
            raise SandboxError(f"import blocked by sandbox: {name!r}")
        return __import__(name, globals, locals, fromlist, level)

    safe["__import__"] = _guarded_import
    return safe


def load_entrypoint(code_dir: str | Path, entrypoint: str,
                    *, module_name: str = "glyph_loaded",
                    allowed_modules: frozenset[str] = DEFAULT_ALLOWED_MODULES,
                    glyph_context: Optional[_identity.GlyphContext] = None,
                    ) -> types.ModuleType:
    """Load a glyph entrypoint under a restricted builtins dict.

    If `glyph_context` is provided, it is set as the active identity context
    for the duration of execution so the loaded code can call
    `glyph.assert_context()` / `glyph.register_self()`.

    Returns the loaded module. Raises SandboxError on policy violations.
    """
    pkg_root = Path(code_dir).resolve()
    # entrypoint is package-relative (e.g. "code/main.py")
    target = (pkg_root / entrypoint).resolve()
    try:
        target.relative_to(pkg_root)
    except ValueError:
        raise SandboxError(f"entrypoint escapes package root: {entrypoint!r}")
    if not target.is_file():
        raise SandboxError(f"entrypoint not found: {target}")

    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        raise SandboxError(f"cannot create import spec for {target}")
    module = importlib.util.module_from_spec(spec)
    module.__builtins__ = _make_restricted_builtins(allowed_modules)  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    _prev_ctx = _identity.context()
    if glyph_context is not None:
        _identity._set_active(glyph_context)
    try:
        spec.loader.exec_module(module)
    except SandboxError:
        raise
    except Exception as e:
        raise SandboxError(f"glyph execution failed: {e!r}") from e
    finally:
        if glyph_context is not None:
            _identity._set_active(_prev_ctx)
    return module
