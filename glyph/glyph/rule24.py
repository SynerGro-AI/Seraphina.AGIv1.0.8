"""Rule-24 binary-native glyph forge (v0.8).

Per the Seraphina rule sheet, every glyph's geometry produces an exact
numeric value via **Rule 24**::

    value = sides*10 + points + dots + intersections + spirals*8

That integer **is** the binary form of the glyph. This module:

  1. Computes Rule-24 values from geometry parameters.
  2. Emits a *real* binary ``.wasm`` module that exports the value as
     both a global constant ``value`` (i64) and a niladic function
     ``value_fn`` returning the same i64.

The result is a glyph whose runtime form is literally the binary it
encodes; ``glyph run --export value_fn`` returns the exact number, no
text parsing, no simulation.

Stdlib-only — no external assembler required.
"""
from __future__ import annotations
from dataclasses import dataclass


# --------------------------------------------------------------------------
# Rule 24
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Geometry:
    sides: int = 0           # base polygon edge count   (×10)
    points: int = 0          # vertex/triangle points    (×1)
    dots: int = 0            # dot markers               (×1)
    intersections: int = 0   # crossings                 (×1)
    spirals: int = 0         # Fibonacci spiral turns    (×8)

    def __post_init__(self) -> None:
        for name, v in self.__dict__.items():
            if not isinstance(v, int) or v < 0:
                raise ValueError(f"geometry.{name} must be a non-negative int, got {v!r}")

    def rule24(self) -> int:
        """Compute the Rule-24 sum — the canonical binary value of the glyph."""
        return (self.sides * 10
                + self.points
                + self.dots
                + self.intersections
                + self.spirals * 8)

    def to_binary(self) -> str:
        """Human-readable binary string — optical scan only, not used at runtime."""
        return bin(self.rule24())[2:]


# --------------------------------------------------------------------------
# WASM bytecode emitter (stdlib only)
# --------------------------------------------------------------------------

def _uleb128(n: int) -> bytes:
    if n < 0:
        raise ValueError("uleb128 is unsigned")
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _sleb128(n: int) -> bytes:
    out = bytearray()
    more = True
    while more:
        byte = n & 0x7F
        n >>= 7
        sign = byte & 0x40
        if (n == 0 and not sign) or (n == -1 and sign):
            more = False
        else:
            byte |= 0x80
        out.append(byte)
    return bytes(out)


def _vec(items: list[bytes]) -> bytes:
    return _uleb128(len(items)) + b"".join(items)


def _section(sid: int, payload: bytes) -> bytes:
    return bytes([sid]) + _uleb128(len(payload)) + payload


# WASM opcodes
_OP_END = 0x0B
_OP_I64_CONST = 0x42
_OP_GLOBAL_GET = 0x23

# Valtypes
_VT_I64 = 0x7E


def emit_rule24_wasm(value: int) -> bytes:
    """Emit a valid `.wasm` module exporting the given integer as both
    ``value`` (global i64 const) and ``value_fn`` (() -> i64 function).
    """
    if not isinstance(value, int):
        raise TypeError("value must be int")

    # --- type section: one type ()->i64 ---
    type_sig = bytes([0x60, 0x00, 0x01, _VT_I64])
    type_sec = _section(1, _vec([type_sig]))

    # --- function section: one function of type 0 ---
    func_sec = _section(3, _vec([_uleb128(0)]))

    # --- global section: one global i64 const value ---
    global_entry = bytes([_VT_I64, 0x00]) + bytes([_OP_I64_CONST]) + _sleb128(value) + bytes([_OP_END])
    global_sec = _section(6, _vec([global_entry]))

    # --- export section: "value" global #0, "value_fn" func #0 ---
    def _export(name: str, kind: int, idx: int) -> bytes:
        nb = name.encode("utf-8")
        return _uleb128(len(nb)) + nb + bytes([kind]) + _uleb128(idx)

    export_sec = _section(7, _vec([
        _export("value",    0x03, 0),  # 0x03 = global
        _export("value_fn", 0x00, 0),  # 0x00 = func
    ]))

    # --- code section: i64.const value; end ---
    body = bytes([0x00]) + bytes([_OP_I64_CONST]) + _sleb128(value) + bytes([_OP_END])
    code_entry = _uleb128(len(body)) + body
    code_sec = _section(10, _vec([code_entry]))

    # Assemble
    return (b"\x00asm\x01\x00\x00\x00"
            + type_sec + func_sec + global_sec + export_sec + code_sec)


# --------------------------------------------------------------------------
# Public forge API
# --------------------------------------------------------------------------

@dataclass
class ForgeResult:
    geometry: Geometry
    value: int
    binary: str
    wasm: bytes


def forge(geometry: Geometry) -> ForgeResult:
    """Compute Rule-24, then emit the matching .wasm module."""
    v = geometry.rule24()
    return ForgeResult(
        geometry=geometry,
        value=v,
        binary=bin(v)[2:],
        wasm=emit_rule24_wasm(v),
    )
