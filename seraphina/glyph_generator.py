# octalang_glyph_generator.py
# OctaLang Glyph Code Generator v1.4
# Generates a glyph CodeScript + rendering description from a text description.
# Deterministic: same description -> same output. No pseudo-random.
# v1.4: the glyph geometry is derived from SHA-256 of the description
# (it was one fixed template, intrinsic 178, for every description).

import hashlib
import re
from typing import Union

from .rule_base import OctaRuleBase

# Glyph IDs are the first ID_HEX_LEN hex chars of SHA-256(normalized text).
# 16 hex = 64 bits: ~4e9 descriptions before a 50% chance of one collision
# (the old 1..999 IDs collided at ~38 descriptions).
ID_HEX_LEN = 16
_ID_RE = re.compile(r"^[0-9a-f]{%d}$" % ID_HEX_LEN)

# v1.2 hand-assigned IDs (not real gematria). Kept ONLY so legacy IDs found
# in old generated CodeScript can be recognised; never used for new IDs.
_LEGACY_ID_MAP = {
    "seraphina": 1013, "agi": 14, "mercy": 270, "growth": 308,
    "guidance": 142, "empathy": 431, "memory": 351, "quantum": 149,
    "core": 231, "generator": 137, "integration": 512, "test": 412,
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def glyph_id(description: str) -> str:
    """Deterministic SHA-256 glyph ID (16 lowercase hex chars)."""
    return hashlib.sha256(_normalize(description).encode("utf-8")).hexdigest()[:ID_HEX_LEN]


def legacy_gematria_id(description: str) -> int:
    """The v1.2 ID (1..999, collision-prone). For reading old output only."""
    t = _normalize(description)
    if t in _LEGACY_ID_MAP:
        return _LEGACY_ID_MAP[t]
    return int(hashlib.sha256(t.encode()).hexdigest(), 16) % 999 + 1


def parse_glyph_id(value: Union[str, int]) -> Union[str, int]:
    """Read an ID from generated CodeScript: returns the hex str for v1.3+
    IDs or an int for legacy v1.2 IDs. Raises ValueError otherwise."""
    v = str(value).strip().lower()
    if _ID_RE.match(v):
        return v
    if v.isdigit() and 1 <= int(v) <= 1013:
        return int(v)
    raise ValueError(f"not a glyph id: {value!r}")


def matches_id(description: str, value: Union[str, int]) -> bool:
    """True if *value* (new or legacy ID) was generated from *description*."""
    pid = parse_glyph_id(value)
    if isinstance(pid, int):
        return legacy_gematria_id(description) == pid
    return glyph_id(description) == pid


def ids_from_codescript(codescript: str) -> Union[str, int]:
    """Extract the glyph ID from a generated CodeScript (v1.2 or v1.3)."""
    m = re.search(r'PROGRAM "Generated_Glyph_([0-9a-fA-F]+)"', codescript)
    if not m:
        raise ValueError("no Generated_Glyph_<id> program line")
    return parse_glyph_id(m.group(1))


# Geometry ranges (inclusive). Each count is read from its own 4-byte slice of
# SHA-256(normalized description), so the geometry is a pure function of the
# description: same text -> same glyph, different text -> (almost always) a
# different glyph. 12*7*16*25*33 = 1,108,800 distinct geometries.
GEOMETRY_RANGES = {
    "spirals": (1, 12),        # golden-spiral turns
    "triangles": (0, 6),       # inscribed triangles
    "dots": (1, 16),           # central dot + satellite dots
    "facets": (0, 24),         # crystalline facets
    "intersections": (0, 32),  # line crossings
}


def geometry_seed(description: str) -> bytes:
    """The 32-byte SHA-256 digest every geometry count is derived from."""
    return hashlib.sha256(_normalize(description).encode("utf-8")).digest()


def geometry(description: str) -> dict:
    """Rule-24 geometry for *description*, derived only from its seed."""
    digest = geometry_seed(description)
    out = {}
    for i, (name, (lo, hi)) in enumerate(GEOMETRY_RANGES.items()):
        word = int.from_bytes(digest[4 * i:4 * i + 4], "big")
        out[name] = lo + word % (hi - lo + 1)
    return out


def intrinsic_value(base: int = 88, spirals: int = 0, triangles: int = 0,
                    dots: int = 0, facets: int = 0, intersections: int = 0) -> int:
    """Rule 24: every glyph is an octagon (88) + its internal geometry."""
    return base + (spirals * 8) + (triangles * 33) + dots + facets + intersections


class OctaLangGlyphGenerator:
    def __init__(self):
        self.version = "1.4"

    @staticmethod
    def glyph_id(description: str) -> str:
        return glyph_id(description)

    def generate(self, description: str) -> str:
        """Main entry point: any description → full glyph CodeScript + rendering.

        Every count in the CodeScript and the rendering text comes from
        geometry(description); nothing is a fixed template value."""
        desc_id = glyph_id(description)
        seed = OctaRuleBase.gematria(description)
        g = geometry(description)
        sp, tr, dt, fc, ix = (g["spirals"], g["triangles"], g["dots"],
                              g["facets"], g["intersections"])
        intrinsic = intrinsic_value(88, **g)
        tri_line = ("Triangle: none" if tr == 0 else
                    f"Triangle{'s' if tr > 1 else ''}: {tr} clean inscribed equilateral "
                    f"triangle{'s' if tr > 1 else ''}, rotated evenly, vertices on the octagon sides")

        codescript = f"""// Auto-Generated by OctaLang Glyph Code Generator v{self.version}
// Input description: "{description}"
// Glyph ID (sha256/64): {desc_id}

PROGRAM "Generated_Glyph_{desc_id}"

HEADER
  VERSION: {self.version}
  EXECUTOR: RomanWheel
  NUMERACY: IntrinsicGeometry; seed = gematria (Hebrew standard / Latin ordinal)
  GEOMETRY_SEED: sha256(normalized description) = {geometry_seed(description).hex()}
  MODE: DeterministicConvergence
  RANDOM: FORBIDDEN

GLYPH GeneratedCore
  TYPE: Module
  CONTAINER: Regular octagon (base 88)
  INTERNAL_GEOMETRY:
    - Golden spiral ({sp} turns) = growth / learning
    - Inscribed triangles ({tr}) = stability
    - Dots ({dt}) + crystalline facets ({fc}) = parallel processing
    - Intersections ({ix}) = branching decision logic
  INTRINSIC_VALUE: {intrinsic}
  INPUT_0: {seed} (gematria seed)
  45°: Recursion / self-nesting
  90°: Multiplication / composition
  180°: Branching tree (deterministic convergence)
  EVALUATION: Innermost-first (Rule 20)
  OUTPUT: Fully formed glyph program

// Rendering Description (Rule 29 - Automatic)
RENDERING
  Container: Large regular octagon, thin metallic gold border
  Central: Luminous gold dot (seed) with faint halo; {dt - 1} smaller satellite dots evenly spaced around it
  Spiral: Golden ratio spiral starting at center, expanding in {sp} precise turns, lines thickening outward
  {tri_line}
  Facets: {fc} crystalline facets symmetrically placed around the spiral
  Intersections: exactly {ix} line crossings between spiral, triangles and rays
  Shading: Smooth dark-to-light gradient inside the octagon (darker near center, lighter toward edges)
  Output Rays: 8 equal-length golden rays extending outward from the central dot through the midpoints of each octagon side
  Central Output Circle: Slightly larger than the seed dot, diameter proportional to the resolved numeric result
  Aesthetic: Sacred geometry style — clean, harmonious, balanced, and alive. No text, no random elements. Every line, dot, and intersection contributes exactly to the intrinsic value.
  Intrinsic Value Breakdown: Base octagon (88) + spiral ({sp * 8}) + triangles ({tr * 33}) + dots ({dt}) + facets ({fc}) + intersections ({ix}) = {intrinsic}

// End of Auto-Generated CodeScript
// Note: no CodeScript interpreter ships in this repo yet (planned).
"""
        return codescript.strip()

# ===================================================================
# Example usage:  python -m seraphina.glyph_generator
# ===================================================================

if __name__ == "__main__":
    generator = OctaLangGlyphGenerator()
    user_input = input("Enter description for glyph generation: ").strip()
    if not user_input:
        user_input = "Seraphina AGI core with Mercy growth"
    
    result = generator.generate(user_input)
    print("\n" + "="*80)
    print("✅ OCTALANG GLYPH CODE GENERATED")
    print("="*80)
    print(result)
    print("\nRendering description included (Rule 29). Deterministic output.")