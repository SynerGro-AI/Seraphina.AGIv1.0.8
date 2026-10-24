# core.py - Seraphina (local Roman Wheel Triad)
# The Triad implementation lives in rule_base.py; this module keeps the
# historical `seraphina.core.RomanWheelTriad` import path.
from typing import Any, Dict, Optional

from .rule_base import RomanWheelTriad as _Triad


class RomanWheelTriad(_Triad):
    def process(self, message: str, candidate: Optional[str] = None) -> Dict[str, Any]:
        out = super().process(message, candidate)
        out["agent"] = "Seraphina"
        return out
