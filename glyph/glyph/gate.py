"""Emotional approval gate — pluggable hook for Seraphina.

v0.6: trust-history aware. The gate consults a per-package trust score (read
from the install location's ``.glyph-meta/trust.json`` if present) and the
manifest's ``emotion`` weights to dynamically widen or narrow the cost
threshold. An optional code verifier (set via ``set_code_verifier``) can be
invoked for non-low-risk packages.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .index import GlyphIndex
from .manifest import Manifest


@dataclass
class GateDecision:
    approved: bool
    reason: str

    def __bool__(self) -> bool:
        return self.approved


CodeVerifier = Callable[[Manifest, Path], bool]
_verifier: Optional[CodeVerifier] = None


def set_code_verifier(fn: Optional[CodeVerifier]) -> None:
    """Register an optional verifier called for non-low-risk packages.

    Signature: ``(manifest, install_location) -> bool``. None disables it.
    """
    global _verifier
    _verifier = fn


def get_code_verifier() -> Optional[CodeVerifier]:
    return _verifier


def _load_trust(name: str, version: Optional[str] = None) -> float:
    """Return prior trust score in [0.0, 1.0] (0.5 if no record)."""
    try:
        idx = GlyphIndex()
        if not idx.store.exists():
            return 0.5
        base = idx.store / name
        if not base.exists():
            return 0.5
        if version is not None:
            paths = [base / version / ".glyph-meta" / "trust.json"]
        else:
            paths = sorted(
                (p / ".glyph-meta" / "trust.json")
                for p in base.iterdir() if p.is_dir()
            )
        scores = []
        for p in paths:
            if p.is_file():
                try:
                    scores.append(float(json.loads(p.read_text("utf-8")).get("score", 0.5)))
                except (json.JSONDecodeError, OSError, ValueError, TypeError):
                    continue
        if not scores:
            return 0.5
        return max(0.0, min(1.0, max(scores)))
    except Exception:  # noqa: BLE001 — gate must never throw on bookkeeping
        return 0.5


class EmotionalGate:
    """Callable: (manifest) -> GateDecision.

    v0.6 behavior:
      * Effective threshold = cost_threshold * (1 + trust - 0.5)  (trust-scaled)
      * High joy raises threshold by up to +20%; high fear lowers it by up to -50%.
      * If risk_level not in allow_risk and a verifier is registered, the
        verifier is consulted; only `risk == 'high'` is *always* denied.
    """

    def __init__(self, *, cost_threshold: float = 5.0,
                 allow_risk: tuple[str, ...] = ("low",)):
        self.cost_threshold = cost_threshold
        self.allow_risk = allow_risk

    def _effective_threshold(self, manifest: Manifest, trust: float) -> float:
        joy = float(manifest.emotion.get("joy", 0.0))
        fear = float(manifest.emotion.get("fear", 0.0))
        scale = 1.0 + (trust - 0.5)         # ±50%
        scale *= 1.0 + 0.2 * joy            # +up to 20%
        scale *= 1.0 - 0.5 * fear           # −up to 50%
        return max(0.0, self.cost_threshold * scale)

    def __call__(self, manifest: Manifest) -> GateDecision:
        trust = _load_trust(manifest.name)
        threshold = self._effective_threshold(manifest, trust)

        if manifest.risk_level == "high":
            return GateDecision(False,
                f"risk_level='high' is never auto-approved (trust={trust:.2f})")

        if manifest.risk_level not in self.allow_risk:
            v = _verifier
            if v is None:
                return GateDecision(False,
                    f"risk_level={manifest.risk_level!r} requires a verifier (none registered)")
            try:
                ok = bool(v(manifest, Path(".")))
            except Exception as e:  # noqa: BLE001
                return GateDecision(False, f"verifier raised: {e!r}")
            if not ok:
                return GateDecision(False,
                    f"verifier rejected risk_level={manifest.risk_level!r}")

        if manifest.cost_estimate > threshold:
            return GateDecision(False,
                f"cost_estimate={manifest.cost_estimate} > effective_threshold={threshold:.2f} "
                f"(trust={trust:.2f})")

        return GateDecision(True,
            f"approved: risk={manifest.risk_level}, cost={manifest.cost_estimate}, "
            f"trust={trust:.2f}, threshold={threshold:.2f}")


GateFn = Callable[[Manifest], GateDecision]

_default = EmotionalGate()
_current: Optional[GateFn] = None


def default_gate() -> EmotionalGate:
    return _default


def set_gate(gate: Optional[GateFn]) -> None:
    """Register Seraphina's gate. Pass None to reset to default."""
    global _current
    _current = gate


def get_gate() -> GateFn:
    return _current or _default
