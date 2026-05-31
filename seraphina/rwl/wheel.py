"""Deterministic byte <-> Roman Wheel symbol mapping.

Every byte 0x00..0xFF maps to a unique 5-tuple drawn from the Roman Wheel
geometry primitives the rest of the system already speaks (see rule24.py
in glyph/, and the Triad consensus axes):

    (sides, points, dots, intersections, spirals)

The mapping is a deterministic factorization of the byte value across
five bounded axes so that:

    symbol_to_byte(byte_to_symbol(b)) == b   for all b in 0..255

It is NOT a compression scheme - it is a *view*. Two bytes never map to
the same symbol, and the inverse is total.

Axis ranges (bounded by the wheel primitives we already render):
    sides         in 0..3    (2 bits)
    points        in 0..3    (2 bits)
    dots          in 0..1    (1 bit)
    intersections in 0..3    (2 bits)
    spirals       in 0..0    (1 bit)  - reserved; always 0 in v1

Total: 8 bits, packed (sides<<6) | (points<<4) | (dots<<3) | (intersections<<1) | spirals
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class WheelSymbol:
    sides: int
    points: int
    dots: int
    intersections: int
    spirals: int

    def as_tuple(self) -> tuple:
        return (self.sides, self.points, self.dots, self.intersections, self.spirals)

    def as_glyph(self) -> str:
        """Compact 5-char glyph used for human-readable wheel dumps."""
        # one char per axis; bounded ranges make this safe and unique within a row
        return f"{self.sides}{self.points}{self.dots}{self.intersections}{self.spirals}"


def byte_to_symbol(b: int) -> WheelSymbol:
    if not 0 <= b <= 0xFF:
        raise ValueError(f"byte out of range: {b}")
    sides = (b >> 6) & 0b11
    points = (b >> 4) & 0b11
    dots = (b >> 3) & 0b1
    intersections = (b >> 1) & 0b11
    spirals = b & 0b1
    return WheelSymbol(sides, points, dots, intersections, spirals)


def symbol_to_byte(sym: WheelSymbol) -> int:
    if not (0 <= sym.sides <= 3 and 0 <= sym.points <= 3 and 0 <= sym.dots <= 1
            and 0 <= sym.intersections <= 3 and 0 <= sym.spirals <= 1):
        raise ValueError(f"wheel symbol out of bounds: {sym}")
    return (sym.sides << 6) | (sym.points << 4) | (sym.dots << 3) \
        | (sym.intersections << 1) | sym.spirals


def render_wheel_stream(data: bytes, *, width: int = 16) -> str:
    """Render a byte stream as a grid of Roman-Wheel symbols (one per byte)."""
    out: List[str] = []
    row: List[str] = []
    for i, b in enumerate(data):
        row.append(byte_to_symbol(b).as_glyph())
        if (i + 1) % width == 0:
            out.append(" ".join(row))
            row = []
    if row:
        out.append(" ".join(row))
    return "\n".join(out)


def stream_to_bytes(glyphs: Iterable[str]) -> bytes:
    """Inverse of `render_wheel_stream` - takes the 5-char glyph tokens back."""
    buf = bytearray()
    for g in glyphs:
        g = g.strip()
        if not g:
            continue
        if len(g) != 5 or not g.isdigit():
            raise ValueError(f"invalid wheel glyph token: {g!r}")
        sym = WheelSymbol(int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]))
        buf.append(symbol_to_byte(sym))
    return bytes(buf)
