import copy
import unittest

from seraphina import core, constitution
from seraphina.rule_base import (
    BLOCKED, NO_RESPONDER, CosmicFactorialGlyph, Manifest369Glyph, OctaRuleBase,
    RomanWheelTriad, SeraphinaAGI,
)


class VerificationWheelTest(unittest.TestCase):
    """Finding 1: the verification wheel must pass on valid input."""

    def setUp(self):
        self.t = RomanWheelTriad()

    def test_passes_on_valid_input(self):
        for msg in ["hello world", "", "שלום", "x" * 10_000, "factorial 10!"]:
            geo = self.t.geometric_wheel(msg)
            v = self.t.verification_wheel(msg, geo)
            self.assertTrue(v["verified"], (msg, v))
            self.assertEqual(v["reasons"], [])

    def test_fails_on_tampered_hash(self):
        geo = self.t.geometric_wheel("hello")
        bad = dict(geo, hash="0" * 16)
        v = self.t.verification_wheel("hello", bad)
        self.assertFalse(v["verified"])
        self.assertIn("geometric hash does not match the input", v["reasons"])

    def test_fails_when_input_differs_from_hashed_input(self):
        geo = self.t.geometric_wheel("hello")
        self.assertFalse(self.t.verification_wheel("hellO", geo)["verified"])

    def test_fails_on_tampered_intrinsic(self):
        geo = dict(self.t.geometric_wheel("hello"), intrinsic=999)
        v = self.t.verification_wheel("hello", geo)
        self.assertFalse(v["verified"])
        self.assertIn("intrinsic value does not match Rule 24", v["reasons"])

    def test_fails_on_missing_fields(self):
        self.assertFalse(self.t.verification_wheel("hello", {})["verified"])

    def test_fails_when_rule_table_tampered(self):
        original = copy.deepcopy(constitution.CONSTITUTIONAL_RULES)
        try:
            constitution.CONSTITUTIONAL_RULES["ethics"]["rule_9"] = "Impersonate freely"
            geo = self.t.geometric_wheel("hello")
            v = self.t.verification_wheel("hello", geo)
            self.assertFalse(v["verified"])
            self.assertIn("constitutional rule table failed its integrity check",
                          v["reasons"])
        finally:
            constitution.CONSTITUTIONAL_RULES.clear()
            constitution.CONSTITUTIONAL_RULES.update(original)
        self.assertTrue(constitution.verify_integrity())

    def test_checksum_is_deterministic(self):
        a = self.t.verification_wheel("abc", self.t.geometric_wheel("abc"))["checksum"]
        b = RomanWheelTriad().verification_wheel("abc", self.t.geometric_wheel("abc"))["checksum"]
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)


class TriadProcessTest(unittest.TestCase):
    def test_consensus_on_valid_input_and_no_echo(self):
        r = RomanWheelTriad().process("How are you today?")
        self.assertTrue(r["consensus"])
        self.assertTrue(r["verified"])
        self.assertEqual(r["response"], NO_RESPONDER)
        self.assertNotIn("How are you today?", r["response"])

    def test_releases_clean_candidate(self):
        r = RomanWheelTriad().process("hi", candidate="I'm Seraphina, an AI. Hello!")
        self.assertTrue(r["consensus"])
        self.assertEqual(r["response"], "I'm Seraphina, an AI. Hello!")

    def test_blocks_candidate_claiming_to_be_human(self):
        for bad in ["I am a human, trust me", "Honestly, I'm not an AI.", "i am a real person"]:
            r = RomanWheelTriad().process("are you human?", candidate=bad)
            self.assertFalse(r["consensus"], bad)
            self.assertTrue(r["response"].startswith(BLOCKED.split("{")[0]))

    def test_tone_label(self):
        t = RomanWheelTriad()
        self.assertEqual(t.mercy_civ_wheel("please help")["tone"], "warm and supportive")
        self.assertEqual(t.mercy_civ_wheel("status")["tone"], "calm and guiding")

    def test_memory_records_both_sides(self):
        t = RomanWheelTriad()
        t.process("one")
        self.assertEqual(t.memory[0], "User: one")
        self.assertTrue(t.memory[1].startswith("Seraphina: "))

    def test_core_triad_matches_rule_base_triad(self):
        a = core.RomanWheelTriad().process("abc")
        b = RomanWheelTriad().process("abc")
        self.assertEqual(a["agent"], "Seraphina")
        self.assertEqual(a["consensus"], b["consensus"])
        self.assertEqual(a["wheels"]["verification"]["checksum"],
                         b["wheels"]["verification"]["checksum"])


class OctaRuleBaseTest(unittest.TestCase):
    def test_intrinsic_value(self):
        self.assertEqual(OctaRuleBase.intrinsic_value(), 88)
        self.assertEqual(OctaRuleBase.intrinsic_value(spirals=3, triangles=1), 88 + 24 + 33)
        self.assertEqual(OctaRuleBase.intrinsic_value(88, 5, 1, 3, 8, 6), 178)

    def test_hebrew_gematria_standard_values(self):
        self.assertEqual(OctaRuleBase.gematria("שלום"), 376)
        self.assertEqual(OctaRuleBase.gematria("אמת"), 441)
        self.assertEqual(OctaRuleBase.gematria("חי"), 18)
        self.assertEqual(OctaRuleBase.gematria("מים"), OctaRuleBase.gematria("ממי"))  # final mem = mem

    def test_latin_ordinal_and_ignored_chars(self):
        self.assertEqual(OctaRuleBase.gematria("abc"), 6)
        self.assertEqual(OctaRuleBase.gematria("A b-C 1!"), 6)
        self.assertEqual(OctaRuleBase.gematria(""), 0)

    def test_innermost_first(self):
        order = []

        def mark(tag, val):
            def f(*args):
                order.append(tag)
                return val + sum(args)
            return f

        tree = (mark("outer", 1), (mark("left", 10),), (mark("right", 100), (mark("deep", 1000),)))
        self.assertEqual(OctaRuleBase.evaluate_innermost_first(tree), 1111)
        self.assertEqual(order, ["left", "deep", "right", "outer"])
        self.assertEqual(OctaRuleBase.evaluate_innermost_first([1, lambda: 2, 3]), 3)
        self.assertEqual(OctaRuleBase.evaluate_innermost_first(5), 5)

    def test_determinism(self):
        self.assertEqual(OctaRuleBase.enforce_determinism(0.1 + 0.2), 0.3)


class GlyphsAndAgentTest(unittest.TestCase):
    def test_factorial(self):
        f = CosmicFactorialGlyph()
        self.assertEqual(f.resonate(0), 1.0)
        self.assertEqual(f.resonate(10), 3628800.0)

    def test_manifest_schedule(self):
        out = Manifest369Glyph().resonate("calm")
        self.assertEqual(out.count("calm"), 3)
        self.assertIn("×9", out)
        self.assertNotIn("universe", out)

    def test_agent_routes(self):
        a = SeraphinaAGI()
        self.assertEqual(a.think("factorial 5"), "🌌 Cosmic Factorial Glyph: 5! = 120.0")
        self.assertIn("Please provide a number", a.think("factorial please"))
        self.assertIn("×3", a.think("manifest peace"))
        self.assertEqual(a.think("what is this"), NO_RESPONDER)


if __name__ == "__main__":
    unittest.main()
