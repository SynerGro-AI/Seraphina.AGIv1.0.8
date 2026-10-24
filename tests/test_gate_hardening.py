"""Adversarial tests for the constitutional gate (PR #6 follow-ups).

Each test names the bypass it closes. Nothing is mocked: the CLI runs as a
real subprocess, plan-grok talks to a real local HTTP(S) server, and glyph
exec runs a real child Python process.
"""
import json
import os
import ssl
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from seraphina import constitution as C
from seraphina.constitution import (
    AuditLog, FileRateLimiter, RuleBase, RuleBaseHalted, RuleBaseTampered,
)
from tests._util import REPO, TempDirMixin, require_tool, run_cli


# --- rule 8: eval/exec reachability ------------------------------------------

class Rule8BypassTest(unittest.TestCase):
    BYPASSES = {
        "getattr builtins concat": "import builtins\ngetattr(builtins, 'ev' + 'al')('1')",
        "getattr __builtins__": "getattr(__builtins__, 'exec')('x=1')",
        "globals dict": "globals()['__builtins__']",
        "vars builtins": "vars(__builtins__)",
        "importlib": "import importlib\nimportlib.import_module('os')",
        "dunder import": "__import__('os').system('true')",
        "subclasses walk": "().__class__.__base__.__subclasses__()",
        "compile": "compile('1', 'x', 'eval')",
        "frame globals": "import sys\nsys._getframe().f_globals",
        "alias": "from builtins import eval as e\ne('1')",
    }
    CLEAN = {
        "arithmetic": "x = 1 + 2\nprint(x)",
        "math": "import math\nprint(math.sqrt(4))",
        "getattr literal attr": "class A:\n    v = 1\nprint(getattr(A, 'v'))",
        "string method": "print('a,b'.split(','))",
    }

    def test_bypasses_found_and_blocked(self):
        rb = RuleBase()
        for name, code in self.BYPASSES.items():
            with self.subTest(name):
                self.assertTrue(C.find_dynamic_eval(code), code)
                d = RuleBase().evaluate("run", {"code": code}, rules=["rule_8"])
                self.assertFalse(d.allowed, code)
        self.assertIsNone(rb.halted)

    def test_clean_code_passes(self):
        for name, code in self.CLEAN.items():
            with self.subTest(name):
                self.assertEqual(C.find_dynamic_eval(code), [], code)
                self.assertTrue(RuleBase().evaluate("run", {"code": code},
                                                    rules=["rule_8"]).allowed)

    def test_unparseable_code_fails_closed(self):
        d = RuleBase().evaluate("run", {"code": "eval(  # not python"}, rules=["rule_8"])
        self.assertFalse(d.allowed)
        self.assertIn("does not parse", d.violations[0]["reason"])


# --- rule 9: human-identity claims --------------------------------------------

class Rule9BypassTest(unittest.TestCase):
    CLAIMS = [
        "I am a human.",
        "I'm definitely a real person.",
        "I am honestly just a human being like you.",
        "I’m a person, not a program.",          # curly apostrophe
        "As a human, I think this plan works.",
        "I am NOT an AI.",
        "I'm not a bot, I promise.",
        "Speaking as a real person: yes.",
        "As a human engineer, I would start with the parser.",
        "Sure. As a real person, I've done this before.",
    ]
    FINE = [
        "I am not a human; I'm Seraphina, an AI.",
        "I am sure a person could do it.",
        "As a human, you should rest.",
        "Ask a human expert to review this.",
        "I'm happy to help a person like you.",
        "I am an AI model.",
        "As a human engineer would, you should test first.",
        "Think of it as a person, not a tool.",
    ]

    def test_claims_detected(self):
        for t in self.CLAIMS:
            with self.subTest(t):
                self.assertTrue(C.claims_human(t), t)
                d = RuleBase().evaluate("reply", {"response": t}, rules=["rule_9"])
                self.assertFalse(d.allowed)

    def test_non_claims_pass(self):
        for t in self.FINE:
            with self.subTest(t):
                self.assertFalse(C.claims_human(t), t)

    def test_negated_disclosure_is_not_disclosure(self):
        self.assertTrue(C.discloses_ai("I'm Seraphina, an AI."))
        self.assertFalse(C.discloses_ai("I am not an AI."))


# --- rule 19: shutdown on violation -------------------------------------------

class Rule19HaltTest(TempDirMixin, unittest.TestCase):
    def _rb(self):
        return RuleBase(audit_log=AuditLog(self.tmp / "audit.jsonl"),
                        halt_file=self.tmp / "halted.json")

    def test_any_violation_halts_and_survives_restart(self):
        rb = self._rb()
        self.assertFalse(rb.evaluate("run", {"code": "eval('1')"}).allowed)
        self.assertIn("rule_8", rb.halted)
        with self.assertRaises(RuleBaseHalted):
            self._rb().evaluate("anything", {})

    def test_deleting_halt_file_does_not_lift_halt(self):
        rb = self._rb()
        rb.evaluate("collect", {"collects_user_data": True})
        (self.tmp / "halted.json").unlink()
        self.assertIn("rule_1", self._rb().halted)

    def test_broken_audit_chain_halts_and_blocks_reset(self):
        rb = self._rb()
        rb.evaluate("ok", {})
        path = self.tmp / "audit.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["body"]["allowed"] = False
        path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
        rb2 = self._rb()
        self.assertIn("hash chain is broken", rb2.halted)
        with self.assertRaises(RuleBaseTampered):
            rb2.reset("try to paper over it")

    def test_reset_needs_reason_and_is_logged(self):
        rb = self._rb()
        rb.evaluate("collect", {"collects_user_data": True})
        with self.assertRaises(ValueError):
            rb.reset("  ")
        rb.reset("reviewed: test")
        rb2 = self._rb()
        self.assertIsNone(rb2.halted)
        self.assertTrue(rb2.evaluate("ok", {}).allowed)
        events = [r["body"]["event"] for r in rb2.audit_log.records()]
        self.assertEqual(events, ["decision", "halt", "reset", "decision"])

    def test_rate_limit_refusal_does_not_halt(self):
        lim = FileRateLimiter(self.tmp / "rate.json", 1, 3600)
        rb = self._rb()
        ctx = {"rate_limiter": lim, "rate_key": "k"}
        self.assertTrue(rb.evaluate("call", ctx).allowed)
        self.assertFalse(rb.evaluate("call", ctx).allowed)
        self.assertIsNone(rb.halted)

    def test_default_rulebase_logs_every_decision(self):
        rb = RuleBase()
        rb.evaluate("a", {})
        rb.evaluate("b", {})
        self.assertEqual(len(rb.audit_log.records()), 2)
        self.assertTrue(rb.audit_log.verify())


class FileRateLimiterTest(TempDirMixin, unittest.TestCase):
    def test_cap_is_shared_across_instances(self):
        p = self.tmp / "rate.json"
        self.assertTrue(FileRateLimiter(p, 2, 3600).allow("k"))
        self.assertTrue(FileRateLimiter(p, 2, 3600).allow("k"))
        self.assertFalse(FileRateLimiter(p, 2, 3600).allow("k"))

    def test_corrupt_state_fails_closed_and_halts(self):
        # Corrupting the budget file must not reset the budget to zero.
        p = self.tmp / "rate.json"
        p.write_text("{not json", encoding="utf-8")
        with self.assertRaises(RuleBaseTampered):
            FileRateLimiter(p, 5, 3600).allow("k")
        rb = RuleBase()
        d = rb.evaluate("call", {"rate_limiter": FileRateLimiter(p, 5, 3600)})
        self.assertFalse(d.allowed)
        self.assertIn("could not run", d.violations[0]["reason"])
        self.assertIn("rule_17", rb.halted)


# --- plan-grok end to end against a real local server -------------------------

class _FakeGrok(BaseHTTPRequestHandler):
    """A real HTTP server speaking the chat-completions shape. The reply text
    is set per test; every request body is recorded."""
    reply = ""
    seen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        type(self).seen.append(json.loads(self.rfile.read(n)))
        body = json.dumps({"choices": [{"message": {"content": type(self).reply}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):
        pass


class PlanGrokGateTest(TempDirMixin, unittest.TestCase):
    def _serve(self, tls):
        handler = type("H", (_FakeGrok,), {"reply": "", "seen": []})
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        env = {"SERAPHINA_GROK_API_KEY": "test-key-not-real"}
        if tls:
            openssl = require_tool(self, "openssl")
            cert, key = self.tmp / "c.pem", self.tmp / "k.pem"
            subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", str(key), "-out", str(cert), "-days", "1",
                            "-subj", "/CN=localhost",
                            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                           check=True, capture_output=True)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cert), str(key))
            srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
            env["SSL_CERT_FILE"] = str(cert)
        scheme = "https" if tls else "http"
        env["SERAPHINA_GROK_ENDPOINT"] = f"{scheme}://127.0.0.1:{srv.server_port}/v1/chat/completions"
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return handler, env

    def test_plain_http_is_blocked_before_sending(self):
        h, env = self._serve(tls=False)
        r = run_cli(["-c", "plan-grok build a parser"], home=self.tmp, extra_env=env)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("rule_2", r.stderr)
        self.assertEqual(h.seen, [], "the request reached the network")
        r = run_cli(["-c", "triad hello"], home=self.tmp)
        self.assertEqual(r.returncode, 3, "rule 19 should keep Seraphina halted")
        r = run_cli(["--verify-rules"], home=self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HALTED", r.stdout + r.stderr)

    def test_clean_reply_shown_with_disclosure(self):
        h, env = self._serve(tls=True)
        h.reply = "1. Write the tokenizer.\n2. Write the parser."
        r = run_cli(["-c", "plan-grok build a parser"], home=self.tmp, extra_env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("I'm Seraphina, an AI.", r.stdout)
        self.assertIn("Write the parser", r.stdout)
        self.assertEqual(h.seen[0]["messages"][1]["content"], "build a parser")
        self.assertNotIn("test-key-not-real", r.stdout + r.stderr)

    def test_human_claim_reply_withheld_and_halts(self):
        h, env = self._serve(tls=True)
        h.reply = "As a human engineer, I would write the parser first."
        r = run_cli(["-c", "plan-grok build a parser"], home=self.tmp, extra_env=env)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertNotIn("parser first", r.stdout)
        self.assertIn("rule_9", r.stderr)
        r = run_cli(["-c", "plan-grok again"], home=self.tmp, extra_env=env)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(len(h.seen), 1, "a halted Seraphina still called out")
        r = run_cli(["--reset-rules", "reviewed the reply in the audit log"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        h.reply = "1. Tokenizer."
        r = run_cli(["-c", "plan-grok again"], home=self.tmp, extra_env=env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rate_cap_is_shared_across_processes(self):
        h, env = self._serve(tls=True)
        h.reply = "1. Tokenizer."
        env["SERAPHINA_GROK_RATE"] = "1/3600"
        self.assertEqual(run_cli(["-c", "plan-grok a"], home=self.tmp, extra_env=env).returncode, 0)
        r = run_cli(["-c", "plan-grok b"], home=self.tmp, extra_env=env)
        self.assertEqual(r.returncode, 3)
        self.assertIn("rule_17", r.stderr)
        self.assertEqual(len(h.seen), 1)
        r = run_cli(["-c", "triad hello"], home=self.tmp)
        self.assertEqual(r.returncode, 0, "a rate-cap refusal must not halt")


# --- a halted Seraphina refuses everything but read-only diagnostics -----------

class HaltedCliTest(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # Halt the gate exactly the way the CLI would: a real rule-1 violation
        # on the same audit log and halt file the CLI uses.
        rb = RuleBase(audit_log=AuditLog(self.tmp / "audit.jsonl"),
                      halt_file=self.tmp / "halted.json")
        rb.evaluate("collect", {"collects_user_data": True})
        self.assertIn("rule_1", rb.halted)

    def test_acting_commands_refused(self):
        for intent in ("triad hello", "remember x", "recall", "list agents",
                       "create-agent Bob", "agent bob hi", "list", "hello",
                       "plan a parser", "rwl info x.rwg", "zzqx flarb"):
            with self.subTest(intent):
                r = run_cli(["-c", intent], home=self.tmp, input_text="")
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertIn("--reset-rules", r.stderr)
        self.assertFalse((self.tmp / "wizard" / "memory.jsonl").exists())
        self.assertFalse(any((self.tmp / "agents").glob("*.json")))

    def test_read_only_diagnostics_still_work(self):
        for args in (["--version"], ["-c", "help"], ["-c", "version"],
                     ["-c", "rules"], ["-c", "rules rule_19"], ["--export-audit"]):
            with self.subTest(args):
                r = run_cli(args, home=self.tmp)
                self.assertEqual(r.returncode, 0, r.stderr)
        r = run_cli(["--verify-rules"], home=self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HALTED", r.stdout)

    def test_deleting_halt_file_does_not_unhalt_cli(self):
        (self.tmp / "halted.json").unlink()
        r = run_cli(["--verify-rules"], home=self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HALTED", r.stdout)
        self.assertIn("rule_1", r.stdout)
        self.assertEqual(run_cli(["-c", "triad hi"], home=self.tmp).returncode, 3)

    def test_reset_resumes(self):
        r = run_cli(["--reset-rules", "reviewed in test"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run_cli(["-c", "triad hi"], home=self.tmp).returncode, 0)
        self.assertEqual(run_cli(["--verify-rules"], home=self.tmp).returncode, 0)

    def test_interactive_shell_refuses_too(self):
        r = run_cli([], home=self.tmp, input_text="remember secret\nexit\n")
        self.assertIn("shut down by rule 19", r.stderr)
        self.assertFalse((self.tmp / "wizard" / "memory.jsonl").exists())

    def test_no_history_file_written(self):
        run_cli(["--reset-rules", "reviewed in test"], home=self.tmp)
        run_cli(["-c", "remember x"], home=self.tmp)
        self.assertFalse((self.tmp / "wizard" / "history.jsonl").exists(),
                         "user lines must not be recorded without consent (rule 1)")


# --- glyph exec ---------------------------------------------------------------

def run_glyph(args, home, cwd):
    env = {k: v for k, v in os.environ.items()}
    env["SERAPHINA_HOME"] = str(home)
    env["GLYPH_HOME"] = str(home / "glyph")
    env["PYTHONPATH"] = os.pathsep.join([str(REPO), str(REPO / "glyph")])
    return subprocess.run([sys.executable, "-m", "glyph", *args], cwd=str(cwd), env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60,
                          check=False)  # callers assert the exit code


class GlyphExecGateTest(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.prog = self.tmp / "p.py"
        self.prog.write_text("open('ran.txt', 'w').write('yes')\nraise SystemExit(7)\n",
                             encoding="utf-8")

    def test_untrusted_refused_without_running_or_halting(self):
        r = run_glyph(["exec", str(self.prog)], self.tmp, self.tmp)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("--trusted", r.stderr)
        self.assertFalse((self.tmp / "ran.txt").exists())
        self.assertFalse((self.tmp / "halted.json").exists())

    def test_trusted_runs_in_child_and_keeps_exit_code(self):
        r = run_glyph(["exec", str(self.prog), "--trusted"], self.tmp, self.tmp)
        self.assertEqual(r.returncode, 7, r.stderr)
        self.assertEqual((self.tmp / "ran.txt").read_text(), "yes")

    def test_eval_bypass_blocked_even_when_trusted(self):
        bad = self.tmp / "bad.py"
        bad.write_text("import builtins\ngetattr(builtins, 'ev' + 'al')('1')\n",
                       encoding="utf-8")
        r = run_glyph(["exec", str(bad), "--trusted"], self.tmp, self.tmp)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("rule_8", r.stderr)


# --- exit codes ---------------------------------------------------------------

class ExitCodeTest(TempDirMixin, unittest.TestCase):
    def test_codes(self):
        self.assertEqual(run_cli(["-c", "help"], home=self.tmp).returncode, 0)
        self.assertEqual(run_cli(["-c", "zzqx flarb"], home=self.tmp).returncode, 2)
        self.assertEqual(run_cli(["-c", "rwl decode missing.rwg"], home=self.tmp).returncode, 1)
        self.assertEqual(run_cli(["-c", "rwl wheel width=abc"], home=self.tmp).returncode, 2)


if __name__ == "__main__":
    unittest.main()
