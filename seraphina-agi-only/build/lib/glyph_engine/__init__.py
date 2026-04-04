"""
Glyph Language Engine v8.7
Justice & Mercy Anchor + 16D Binary/Float Hyper-Wheel

A sophisticated language engine that fuses Hebrew Gematria, binary processing,
and geometric transformations for deterministic, resonant code generation.
"""

from .version import __version__, __version_info__, VERSION, AUTHOR, DESCRIPTION, RELEASE_DATE

__author__ = AUTHOR
__description__ = DESCRIPTION

from .language_engine_bridge import (
    call_glyph_cipher,
    call_glyph_cipher_wasm,
    call_glyph_cipher_legacy,
)

__all__ = [
    "call_glyph_cipher",
    "call_glyph_cipher_wasm",
    "call_glyph_cipher_legacy",
]