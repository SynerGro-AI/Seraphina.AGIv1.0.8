"""Roman Wheel Language (RWL) - universal binary carrier for source code.

RWL gives every supported language a single deterministic binary skin so
code can travel, be signed, sandboxed, and stored uniformly across the
Glyph ecosystem regardless of its source language.

What v1 IS:
  * Lossless per-language round-trip: source -> .rwg -> identical source
    (verified by SHA256 of the reconstructed bytes)
  * Roman-Wheel symbolic view of any byte stream (every byte renders as
    a deterministic geometry tuple: sides, points, dots, intersections,
    spirals - see seraphina.rwl.wheel)
  * Stdlib only. Container is a 64-byte header + optional zlib payload.

What v1 IS NOT:
  * A semantic translator. Python -> .rwg -> JavaScript is NOT supported
    by the byte-IR layer; it carries the source, it does not rewrite it.
    Cross-language semantic translation is the AST-IR tier (future work).

CLI:
    seraphina rwl encode <src>  -o out.rwg [--lang auto|python|js|text]
    seraphina rwl decode <rwg>  -o restored.<ext>
    seraphina rwl info <rwg>
    seraphina rwl wheel <rwg>            # render byte stream as wheel symbols
"""
from .codec import (
    encode,
    decode,
    info,
    RWLError,
    RWLContainer,
    SUPPORTED_LANGUAGES,
)
from .wheel import byte_to_symbol, symbol_to_byte, render_wheel_stream
from . import ast_ir
from .ast_ir import translate, parse, emit

__all__ = [
    "encode",
    "decode",
    "info",
    "RWLError",
    "RWLContainer",
    "SUPPORTED_LANGUAGES",
    "byte_to_symbol",
    "symbol_to_byte",
    "render_wheel_stream",
    "ast_ir",
    "translate",
    "parse",
    "emit",
]
