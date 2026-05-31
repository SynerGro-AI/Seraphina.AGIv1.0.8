"""Frontends: parse source code into RWAST."""
from .python_fe import parse_python

SUPPORTED = {"python", "py"}


def parse(source: str, language: str) -> "Node":
    lang = language.lower().strip(".")
    if lang in SUPPORTED:
        return parse_python(source)
    raise ValueError(f"no frontend for language: {language!r}  (supported: {sorted(SUPPORTED)})")
