"""Glyph — Seraphina's package manager (v0.10).

Native, self-bootstrapping alternative to pip for the Seraphina ecosystem.
v0.10 adds remote install: `glyph install <url>` and `glyph install <name>`
resolved against a JSON index.
"""
__version__ = "0.10.0"

from .manifest import Manifest, ManifestError
from .index import GlyphIndex
from .integrity import IntegrityChecker, IntegrityError
from .resolution import DependencyResolver, ResolutionError
from .gate import (
    EmotionalGate, default_gate, set_gate, get_gate,
    set_code_verifier, get_code_verifier,
)
from .operations import install, uninstall, list_installed, freeze
from .identity import (
    assert_context, register_self, emit_signal, context,
    GlyphContext, ContextError,
)
from .bootstrap import bootstrap
from .generator import (
    parse as gl_parse, transpile as gl_transpile,
    compile_file as gl_compile_file, compile_tree as gl_compile_tree,
    format_gl, GLDocument, GLSyntaxError,
)
from .signals import subscribe, unsubscribe, publish, subscribers
from .registry import discover, GlyphRecord
from .doctor import check as doctor_check, DoctorReport, Finding
from . import seraphina_bridge, ledger
from . import wasm
from . import rule24
from .rule24 import Geometry, ForgeResult, forge, emit_rule24_wasm
from . import remote
from .remote import RemoteHost, RemoteResponse, RemoteError

__all__ = [
    "Manifest", "ManifestError",
    "GlyphIndex",
    "IntegrityChecker", "IntegrityError",
    "DependencyResolver", "ResolutionError",
    "EmotionalGate", "default_gate", "set_gate", "get_gate",
    "set_code_verifier", "get_code_verifier",
    "install", "uninstall", "list_installed", "freeze",
    "assert_context", "register_self", "emit_signal", "context",
    "GlyphContext", "ContextError",
    "bootstrap",
    "gl_parse", "gl_transpile", "gl_compile_file", "gl_compile_tree",
    "format_gl", "GLDocument", "GLSyntaxError",
    "subscribe", "unsubscribe", "publish", "subscribers",
    "discover", "GlyphRecord",
    "doctor_check", "DoctorReport", "Finding",
    "seraphina_bridge", "ledger",
    "wasm",
    "rule24", "Geometry", "ForgeResult", "forge", "emit_rule24_wasm",
    "remote", "RemoteHost", "RemoteResponse", "RemoteError",
    "__version__",
]
