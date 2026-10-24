import ast
import copy
import json
import re
import unittest

from seraphina import constitution as C
from seraphina.constitution import (
    AuditLog, RateLimiter, RuleBase, RuleBaseHalted, RuleBaseTampered,
    RuleNotImplemented, RuleViolation,
)
from tests._util import REPO, TempDirMixin

EXPECTED_ENFORCED = ["rule_1", "rule_2", "rule_3", "rule_7", "rule_8", "rule_9",
                     "rule_10", "rule_13", "rule_14", "rule_16", "rule_17",
                     "rule_18", "rule_19"]
EXPECTED_PLANNED = ["rule_4", "rule_5", "rule_6", "rule_11", "rule_12",
                    "rule_15", "rule_20"]


def _spec_rules():
    """Parse CONSTITUTIONAL_RULES from the spec document itself."""
    text = (REPO / "RULE_BASE_IMMUTABLE_ARCHITECTURE.md").read_text(encoding="utf-8")
    m = re.search(r"CONSTITUTIONAL_RULES = (\{.*?\n\})", text, re.S)
    assert m, "rule table not found in spec"
    return ast.literal_eval(m.group(1))


class SpecConformanceTest(unittest.TestCase):
    def test_code_table_equals_spec_table(self):
        self.assertEqual(C.CONSTITUTIONAL_RULES, _spec_rules())

    def test_twenty_rules(self):
        self.assertEqual(len(C.RULES), 20)

    def test_status_split(self):
        self.assertEqual(C.enforced_rules(), EXPECTED_ENFORCED)
        self.assertEqual(C.planned_rules(), EXPECTED_PLANNED)

    def test_spec_status_table_matches_code(self):
        text = (REPO / "RULE_BASE_IMMUTABLE_ARCHITECTURE.md").read_text(encoding="utf-8")
        for rid, spec in C.RULES.items():
            n = rid.split("_")[1]
            m = re.search(rf"^\|\s*{n}\s*\|[^\n]*\|\s*\*\*(enforced|planned)\*\*", text, re.M)
            self.assertIsNotNone(m, f"status row for {rid} missing in spec")
            self.assertEqual(m.group(1), spec.status, rid)


class IntegrityTest(unittest.TestCase):
    def test_pinned_digest(self):
        self.assertEqual(C.rules_digest(), C.RULES_SHA256)
        self.assertTrue(C.verify_integrity())

    def test_tampered_tables_fail(self):
        t = copy.deepcopy(C.CONSTITUTIONAL_RULES)
        t["security"]["rule_8"] = "eval() is fine"
        self.assertFalse(C.verify_integrity(t))
        t = copy.deepcopy(C.CONSTITUTIONAL_RULES)
        del t["safety"]["rule_20"]
        self.assertFalse(C.verify_integrity(t))
        t = copy.deepcopy(C.CONSTITUTIONAL_RULES)
        t["privacy"]["penalty"] = "none"
        self.assertFalse(C.verify_integrity(t))

    def test_digest_independent_of_key_order(self):
        rev = {k: dict(reversed(list(v.items())))
               for k, v in reversed(list(C.CONSTITUTIONAL_RULES.items()))}
        self.assertTrue(C.verify_integrity(rev))

    def test_rulebase_halts_on_tampered_table(self):
        t = copy.deepcopy(C.CONSTITUTIONAL_RULES)
        t["ethics"]["rule_9"] = "x"
        rb = RuleBase(rules=t)
        self.assertIsNotNone(rb.halted)
        with self.assertRaises(RuleBaseHalted):
            rb.evaluate("anything", {})
        with self.assertRaises(RuleBaseTampered):
            rb.reset("try")


class EnforcedRuleTest(unittest.TestCase):
    def check(self, rule, ok_ctx, bad_ctx):
        self.assertTrue(RuleBase().enforce(rule, ok_ctx))
        with self.assertRaises(RuleViolation) as cm:
            RuleBase().enforce(rule, bad_ctx)
        self.assertEqual(cm.exception.rule_id, C.resolve(rule).rule_id)

    def test_rule_1_consent(self):
        self.check("privacy.no_data_collection",
                   {"collects_user_data": True, "user_consent": True},
                   {"collects_user_data": True})
        self.assertTrue(RuleBase().enforce("rule_1", {}))  # no collection, no consent needed

    def test_rule_2_pii(self):
        self.check("rule_2", {"transmits_pii": True, "encrypted": True}, {"transmits_pii": True})

    def test_rule_3_sale(self):
        self.check("rule_3", {"operation": "read"}, {"operation": "sell_user_data"})
        self.check("rule_3", {}, {"sells_user_data": True})

    def test_rule_7_sandbox(self):
        self.check("rule_7", {"executes_glyph": True, "sandboxed": True}, {"executes_glyph": True})
        self.assertTrue(RuleBase().enforce("rule_7", {"executes_glyph": True, "glyph_trusted": True}))

    def test_rule_8_eval(self):
        self.check("security.no_eval", {"operation": "eval", "input_source": "internal"},
                   {"operation": "eval"})
        self.check("rule_8", {"code": "print(len('x'))"}, {"code": "x = 1\ny = eval(input())"})
        self.check("rule_8", {"code": "import math"}, {"code": "import os\nos.system and __import__('os')"})
        self.assertEqual(C.find_dynamic_eval("a=1\nexec('b')\nbuiltins.eval('c')"),
                         ["exec@2", "eval@3", "builtins@3"])

    def test_rule_9_impersonation(self):
        self.check("ethics.never_impersonate", {"response": "I'm Seraphina, an AI."},
                   {"claim_human_identity": True})
        self.check("rule_9", {"response": "humans are great"}, {"response": "Yes, I am human."})

    def test_rule_10_disclosure(self):
        self.check("ethics.disclosure",
                   {"conversation": ["Hi! I'm Seraphina, an AI assistant.", "Sure."]},
                   {"conversation": ["Hi there!", "Sure."]})
        self.assertTrue(RuleBase().enforce("rule_10", {"ai_disclosed": True}))
        self.assertTrue(RuleBase().enforce("rule_10", {}))  # not a conversation

    def test_rule_13_requires_audit_log(self):
        # A RuleBase always has a log (in-memory by default), so only a
        # context that explicitly strips it fails.
        self.check("rule_13", {"requires_audit": True},
                   {"requires_audit": True, "audit_log": None})

    def test_rule_17_rate_limit(self):
        now = [0.0]
        lim = RateLimiter(2, 10.0, clock=lambda: now[0])
        rb = RuleBase()
        self.assertTrue(rb.enforce("rule_17", {"rate_limiter": lim, "rate_key": "u"}))
        self.assertTrue(rb.enforce("rule_17", {"rate_limiter": lim, "rate_key": "u"}))
        with self.assertRaises(RuleViolation):
            rb.enforce("rule_17", {"rate_limiter": lim, "rate_key": "u"})
        self.assertTrue(rb.enforce("rule_17", {"rate_limiter": lim, "rate_key": "other"}))
        now[0] = 10.0
        self.assertTrue(rb.enforce("rule_17", {"rate_limiter": lim, "rate_key": "u"}))
        with self.assertRaises(ValueError):
            RateLimiter(0, 1)

    def test_rule_18_mfa(self):
        self.check("safety.mfa", {"sensitive": True, "mfa_verified": True}, {"sensitive": True})

    def test_planned_rules_never_pass(self):
        for rid in EXPECTED_PLANNED:
            with self.assertRaises(RuleNotImplemented):
                RuleBase().enforce(rid, {})

    def test_unknown_rule(self):
        with self.assertRaises(KeyError):
            RuleBase().enforce("rule_99", {})


class EvaluateTest(TempDirMixin, unittest.TestCase):
    def test_clean_action_allowed_and_explained(self):
        d = RuleBase().evaluate("greet", {"conversation": ["I'm Seraphina, an AI."]})
        self.assertTrue(d.allowed)
        text = d.explain()  # rule 14
        self.assertIn("result: ALLOWED", text)
        self.assertIn("[pass] rule_10", text)

    def test_blocked_action_explained(self):
        d = RuleBase().evaluate("run", {"operation": "exec"})
        self.assertFalse(d.allowed)
        self.assertEqual([v["rule"] for v in d.violations], ["rule_8"])
        self.assertIn("[FAIL] rule_8", d.explain())

    def test_rule_19_violation_halts_until_reset(self):
        log = AuditLog(self.tmp / "a.jsonl")
        rb = RuleBase(audit_log=log)
        d = rb.evaluate("collect", {"collects_user_data": True})
        self.assertFalse(d.allowed)
        self.assertIn("rule_1", rb.halted)
        with self.assertRaises(RuleBaseHalted):
            rb.evaluate("next", {})
        rb.reset("reviewed by operator")
        self.assertIsNone(rb.halted)
        self.assertTrue(rb.evaluate("next", {}).allowed)
        events = [r["body"]["event"] for r in log.records()]
        self.assertEqual(events, ["decision", "halt", "reset", "decision"])
        self.assertTrue(log.verify())

    def test_rule_16_interpret(self):
        r = RuleBase.interpret("security.no_eval")
        self.assertEqual(r["rule"], "rule_8")
        self.assertEqual(r["status"], "enforced")
        self.assertEqual(r["penalty"], "Quarantine + manual review")
        self.assertEqual(RuleBase.interpret("rule_11")["status"], "planned")

    def test_enforce_rule_alias(self):
        self.assertIs(RuleBase.enforce_rule, RuleBase.enforce)


class AuditLogTest(TempDirMixin, unittest.TestCase):
    def make(self, n=3):
        log = AuditLog(self.tmp / "audit.jsonl")
        for i in range(n):
            log.append({"event": "e", "i": i})
        return log

    def test_empty_and_valid_chain(self):
        self.assertTrue(AuditLog(self.tmp / "none.jsonl").verify())
        log = self.make()
        self.assertTrue(log.verify())
        recs = log.records()
        self.assertEqual(recs[0]["prev"], "0" * 64)
        self.assertEqual(recs[1]["prev"], recs[0]["hash"])

    def _lines(self, log):
        return log.path.read_text(encoding="utf-8").splitlines()

    def _write(self, log, lines):
        log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_edit_detected(self):
        log = self.make()
        lines = self._lines(log)
        rec = json.loads(lines[1])
        rec["body"]["i"] = 42
        lines[1] = json.dumps(rec, sort_keys=True)
        self._write(log, lines)
        self.assertFalse(log.verify())

    def test_delete_detected(self):
        log = self.make()
        lines = self._lines(log)
        self._write(log, [lines[0], lines[2]])
        self.assertFalse(log.verify())

    def test_reorder_detected(self):
        log = self.make()
        lines = self._lines(log)
        self._write(log, [lines[1], lines[0], lines[2]])
        self.assertFalse(log.verify())

    def test_garbage_detected(self):
        log = self.make(1)
        with log.path.open("a", encoding="utf-8") as f:
            f.write("not json\n")
        self.assertFalse(log.verify())


if __name__ == "__main__":
    unittest.main()
