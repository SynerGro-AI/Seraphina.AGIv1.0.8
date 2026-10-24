# rule_base.py
# Octa v2.1 rule base + Seraphina's Roman Wheel Triad (deterministic).
#
# Spec: RULE_BASE_IMMUTABLE_ARCHITECTURE.md. The 20 constitutional rules and
# their enforcement live in seraphina/constitution.py and are re-exported here.

import hashlib
import hmac
import re
import time
from typing import Any, Dict, List, Optional

from .constitution import (  # noqa: F401  (re-exported public API)
    CONSTITUTIONAL_RULES, RULES_SHA256, AuditLog, Decision, RateLimiter,
    RuleBase, RuleBaseHalted, RuleNotImplemented, RuleViolation,
    claims_human, enforced_rules, planned_rules, rules_digest,
    verify_integrity,
)

# Standard Hebrew gematria (mispar hechrechi). Final forms take the value of
# the regular letter.
HEBREW_GEMATRIA = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
    "י": 10, "כ": 20, "ך": 20, "ל": 30, "מ": 40, "ם": 40, "נ": 50, "ן": 50,
    "ס": 60, "ע": 70, "פ": 80, "ף": 80, "צ": 90, "ץ": 90,
    "ק": 100, "ר": 200, "ש": 300, "ת": 400,
}


# ====================== OCTA v2.1 RULE BASE ======================
class OctaRuleBase:
    VERSION = "2.1"

    # Rule 24 (Octa v2.1 variant): an octagon glyph has base 88
    # (8 sides x 10 + 8 points) plus its internal geometry. glyph/rule24.py
    # holds the general Glyph form: sides*10 + points + dots + intersections
    # + spirals*8.
    @staticmethod
    def intrinsic_value(base: int = 88, spirals: int = 0, triangles: int = 0,
                        dots: int = 0, facets: int = 0, intersections: int = 0) -> int:
        """Every glyph is an octagon (base 88) + internal geometry"""
        return base + (spirals * 8) + (triangles * 33) + dots + facets + intersections

    # Rule 19 + 22: Hebrew gematria
    @staticmethod
    def gematria(text: str) -> int:
        """Standard Hebrew gematria: the sum of letter values. Latin letters
        use simple English ordinal values (a=1 .. z=26). Any other character
        (spaces, digits, punctuation, niqqud) counts 0."""
        total = 0
        for ch in text.strip().lower():
            if ch in HEBREW_GEMATRIA:
                total += HEBREW_GEMATRIA[ch]
            elif "a" <= ch <= "z":
                total += ord(ch) - 96
        return total

    # Rule 20: Innermost-first evaluation principle
    @staticmethod
    def evaluate_innermost_first(components: Any) -> Any:
        """Evaluate an expression tree innermost-first.

        A node is either a plain value, a zero-arg callable, or a tuple
        ``(fn, arg1, arg2, ...)`` whose args are evaluated (recursively,
        innermost first) before ``fn`` is applied. A list is evaluated element
        by element and the last result is returned.
        """
        def ev(node):
            if isinstance(node, tuple) and node and callable(node[0]):
                args = [ev(a) for a in node[1:]]
                return node[0](*args)
            if callable(node):
                return node()
            return node

        if isinstance(components, list):
            result = None
            for c in components:
                result = ev(c)
            return result
        return ev(components)

    # Rule 27: Deterministic Convergence + No Pseudo-Random
    @staticmethod
    def enforce_determinism(value: float) -> float:
        """Force convergence to stable value"""
        return round(value, 8)  # deterministic precision


# ====================== ROMAN WHEEL TRIAD ======================
_POSITIVE_WORDS = ("help", "good", "peace", "joy", "love", "abundance", "grow")

# What Triad.process() says when no response generator is attached. The
# Triad is a release gate, it does not generate answers.
NO_RESPONDER = ("Triad consensus reached (geometric, verification and "
                "mercy-civ all pass). No response generator is attached to "
                "the local Triad; it only gates output.")
BLOCKED = "Triad blocked the output: {reasons}."


class RomanWheelTriad:
    """Seraphina's consensus triad. Output is released only if all three
    wheels pass:

    1. Geometric    - SHA-256 fingerprint + Octa intrinsic value of the input.
    2. Verification - independently recomputes wheel 1 from the input and
                      checks the result was not altered, and checks the
                      constitutional rule table against its pinned hash.
    3. Mercy-Civ    - constitutional ethics checks (rule 9: never claim to be
                      human) on the output that would be released, plus a
                      keyword tone label.
    """

    INTRINSIC_GEOMETRY = {"spirals": 3, "triangles": 1}

    def __init__(self):
        self.version = OctaRuleBase.VERSION
        self.memory: List[str] = []

    @staticmethod
    def fingerprint(input_text: str) -> str:
        return hashlib.sha256(input_text.encode("utf-8")).hexdigest()[:16]

    def geometric_wheel(self, input_text: str) -> Dict:
        """Wheel 1: Pure geometric / glyph processing"""
        return {
            "type": "Geometric",
            "hash": self.fingerprint(input_text),
            "intrinsic": OctaRuleBase.intrinsic_value(**self.INTRINSIC_GEOMETRY),
            "processed": True,
        }

    def verification_wheel(self, input_text: str, geo_result: Dict) -> Dict:
        """Wheel 2: recompute wheel 1 and compare (tamper check)."""
        expected_hash = self.fingerprint(input_text)
        expected_intrinsic = OctaRuleBase.intrinsic_value(**self.INTRINSIC_GEOMETRY)
        hash_ok = hmac.compare_digest(str(geo_result.get("hash", "")), expected_hash)
        intrinsic_ok = geo_result.get("intrinsic") == expected_intrinsic
        rules_ok = verify_integrity()
        checksum = hashlib.sha256(
            (input_text + expected_hash).encode("utf-8")).hexdigest()[:16]
        reasons = []
        if not hash_ok:
            reasons.append("geometric hash does not match the input")
        if not intrinsic_ok:
            reasons.append("intrinsic value does not match Rule 24")
        if not rules_ok:
            reasons.append("constitutional rule table failed its integrity check")
        return {
            "type": "Verification",
            "verified": hash_ok and intrinsic_ok and rules_ok,
            "checksum": checksum,
            "reasons": reasons,
        }

    def mercy_civ_wheel(self, input_text: str, output_text: Optional[str] = None) -> Dict:
        """Wheel 3: Mercy / Virtual Civ alignment of the output to release."""
        is_positive = any(w in input_text.lower() for w in _POSITIVE_WORDS)
        reasons = []
        if output_text is not None and claims_human(output_text):
            reasons.append("output claims to be human (constitutional rule 9)")
        return {
            "type": "MercyCiv",
            "score": 0.0 if reasons else 1.0,
            "aligned": not reasons,
            "tone": "warm and supportive" if is_positive else "calm and guiding",
            "reasons": reasons,
        }

    def process(self, message: str, candidate: Optional[str] = None) -> Dict[str, Any]:
        """Run the three wheels. *candidate* is the output to gate; when it
        is None the Triad reports its verdict instead of inventing an answer."""
        start = time.perf_counter()
        geo = self.geometric_wheel(message)
        verify = self.verification_wheel(message, geo)
        mercy = self.mercy_civ_wheel(message, candidate)
        consensus = geo["processed"] and verify["verified"] and mercy["aligned"]
        if consensus:
            response = candidate if candidate is not None else NO_RESPONDER
        else:
            response = BLOCKED.format(
                reasons="; ".join(verify["reasons"] + mercy["reasons"]))
        self.memory.append(f"User: {message}")
        self.memory.append(f"Seraphina: {response}")
        return {
            "response": response,
            "consensus": consensus,
            "wheels": {"geometric": geo, "verification": verify, "mercy_civ": mercy},
            "processing_time": round(time.perf_counter() - start, 4),
            "verified": verify["verified"],
        }


# ====================== COSMIC FACTORIAL GLYPH ======================
class CosmicFactorialGlyph:
    """Cosmic Factorial - integer factorial (n is truncated to an int)."""
    def resonate(self, n: float) -> float:
        if n <= 1:
            return 1.0
        result = 1.0
        for i in range(2, int(n) + 1):
            result *= i
        return OctaRuleBase.enforce_determinism(result)


# ====================== 369 MANIFESTATION GLYPH ======================
class Manifest369Glyph:
    """Tesla 3-6-9 repetition schedule: a text formatter, nothing more."""
    def resonate(self, intention: str) -> str:
        if not intention:
            intention = "peace and abundance"
        return (f"🌟 {intention} ×3 (morning)\n"
                f"🌟 {intention} ×6 (afternoon)\n"
                f"🌟 {intention} ×9 (evening)")


# ====================== SERAPHINA AGENT ======================
class SeraphinaAGI:
    def __init__(self):
        self.triad = RomanWheelTriad()
        self.factorial = CosmicFactorialGlyph()
        self.manifest = Manifest369Glyph()

    def think(self, user_input: str) -> str:
        lower = user_input.lower()
        if "factorial" in lower or "!" in user_input:
            numbers = re.findall(r"\d+", user_input)
            if not numbers:
                return "🌌 Please provide a number for the Cosmic Factorial glyph."
            n = float(numbers[0])
            return f"🌌 Cosmic Factorial Glyph: {n:g}! = {self.factorial.resonate(n):,}"
        if any(w in lower for w in ["manifest", "369", "tesla", "wish", "intention"]):
            intention = user_input.split("manifest", 1)[-1].strip() or "peace and abundance"
            return self.manifest.resonate(intention)
        return self.triad.process(user_input)["response"]


if __name__ == "__main__":
    s = SeraphinaAGI()
    print(s.think("factorial 10"))
    print(s.think("manifest world peace and abundance"))
    print(s.think("How are you today?"))
