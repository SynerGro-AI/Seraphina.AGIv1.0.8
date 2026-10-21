"""Seraphina.AGI - lean Python core.

A deterministic, geometry-native AGI core built on the Roman Wheel Triad
(Geometric / Verification / Mercy-Civ) and OctaLang Rule Base.

Public API:
    RomanWheelTriad - simple consensus engine (core.py)
    OctaRuleBase    - Rule 24 intrinsic-value math (rule_base.py)
    ClaimGate       - Roman Wheel Node claim gate (claim_gate.py, vendored roman_wheel_node.py)
"""
from .core import RomanWheelTriad
from .rule_base import OctaRuleBase
from .claim_gate import ClaimGate, GateDecision, gate_translation

__version__ = "1.0.12"
__all__ = ["RomanWheelTriad", "OctaRuleBase", "ClaimGate", "GateDecision", "gate_translation", "__version__"]
