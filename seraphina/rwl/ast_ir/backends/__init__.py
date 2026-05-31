"""Backends: emit RWAST as target language source code."""
from .python_be import emit_python
from .js_be import emit_js
from .ts_be import emit_ts

SUPPORTED = {"python", "py", "javascript", "js", "typescript", "ts"}


def emit(root: "Node", language: str) -> str:
    lang = language.lower().strip(".")
    if lang in ("python", "py"):
        return emit_python(root)
    if lang in ("javascript", "js"):
        return emit_js(root)
    if lang in ("typescript", "ts"):
        return emit_ts(root)
    raise ValueError(f"no backend for language: {language!r}  (supported: {sorted(SUPPORTED)})")
