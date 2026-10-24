"""CLI end-to-end tests: real subprocesses, real files, isolated SERAPHINA_HOME."""
import json
import unittest

from seraphina import __version__
from seraphina.cli import _rwl_parse_named
from seraphina.rwl import decode
from tests._util import TempDirMixin, run_cli


class ModuleEntryPointTest(TempDirMixin, unittest.TestCase):
    """Finding 6: `python -m seraphina.cli` must run main()."""

    def test_python_m_cli_version(self):
        r = run_cli(["--version"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"seraphina {__version__}")

    def test_python_m_cli_runs_command(self):
        r = run_cli(["-c", "help"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rwl encode", r.stdout)

    def test_python_m_seraphina_also_works(self):
        r = run_cli(["--version"], home=self.tmp, module="seraphina")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(__version__, r.stdout)


class OutputFlagTest(TempDirMixin, unittest.TestCase):
    """Finding 5: `-o out` must write to `out`, never to a file named '-o'."""

    def setUp(self):
        super().setUp()
        self.src = self.tmp / "hello.py"
        self.src.write_text("print('hi')\n", encoding="utf-8")

    def _assert_no_dash_o(self):
        self.assertFalse((self.tmp / "-o").exists(), "a file literally named '-o' was created")
        self.assertEqual([p.name for p in self.tmp.rglob("-*")], [])

    def test_encode_decode_with_dash_o(self):
        for style in (["-c", "rwl encode hello.py -o out/hello.rwg"],
                      ["rwl", "encode", "hello.py", "-o", "out/hello.rwg"]):
            with self.subTest(style=style[0]):
                r = run_cli(style, home=self.tmp)
                self.assertEqual(r.returncode, 0, r.stderr)
                rwg = self.tmp / "out" / "hello.rwg"
                self.assertTrue(rwg.is_file(), r.stdout)
                container, src = decode(rwg.read_bytes())
                self.assertEqual(src, self.src.read_bytes())
                self.assertEqual(container.language, "python")
                self._assert_no_dash_o()
                rwg.unlink()

        run_cli(["-c", "rwl encode hello.py -o hello.rwg"], home=self.tmp)
        r = run_cli(["-c", "rwl decode hello.rwg -o back/restored.py"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.tmp / "back" / "restored.py").read_bytes(), self.src.read_bytes())
        self.assertIn("sha256 verified", r.stdout)
        self._assert_no_dash_o()

    def test_other_out_spellings(self):
        for i, flag in enumerate(["--out x{}.rwg", "--out=x{}.rwg", "-o=x{}.rwg", "-ox{}.rwg", "out=x{}.rwg"]):
            arg = flag.format(i)
            with self.subTest(flag=arg):
                r = run_cli(["-c", f"rwl encode hello.py {arg}"], home=self.tmp)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue((self.tmp / f"x{i}.rwg").is_file(), r.stdout)
        self._assert_no_dash_o()

    def test_translate_with_dash_o(self):
        r = run_cli(["-c", "rwl translate hello.py --to js -o build/hello.js"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.tmp / "build" / "hello.js"
        self.assertTrue(out.is_file(), r.stdout)
        self.assertIn("console.log", out.read_text(encoding="utf-8"))
        self._assert_no_dash_o()


class ParseNamedTest(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(_rwl_parse_named(["a.py", "-o", "b"]), (["a.py"], {"out": "b"}))
        self.assertEqual(_rwl_parse_named(["a.py", "-ob"]), (["a.py"], {"out": "b"}))
        self.assertEqual(_rwl_parse_named(["a.py", "-o=b"]), (["a.py"], {"out": "b"}))
        self.assertEqual(_rwl_parse_named(["--from", "python", "--to=js", "f"]),
                         (["f"], {"from": "python", "to": "js"}))
        self.assertEqual(_rwl_parse_named(["f", "compress=off"]), (["f"], {"compress": "off"}))

    def test_paths_with_equals_stay_positional(self):
        pos, kw = _rwl_parse_named(["./a=b.py", "/tmp/x=y"])
        self.assertEqual(pos, ["./a=b.py", "/tmp/x=y"])
        self.assertEqual(kw, {})


class RulesAndAuditCliTest(TempDirMixin, unittest.TestCase):
    def test_verify_rules_ok_then_tampered_log(self):
        r = run_cli(["-c", "triad hello world"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("consensus: True", r.stdout)
        run_cli(["-c", "triad second message"], home=self.tmp)

        r = run_cli(["--verify-rules"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("rule table   : OK", r.stdout)
        self.assertIn("audit log    : OK (2 records", r.stdout)
        self.assertIn("enforced     : 13/20", r.stdout)

        log = self.tmp / "audit.jsonl"
        lines = log.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["body"]["consensus"] = False
        lines[0] = json.dumps(rec)
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        r = run_cli(["--verify-rules"], home=self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BROKEN CHAIN", r.stdout)
        r = run_cli(["--export-audit", str(self.tmp / "x.jsonl")], home=self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.tmp / "x.jsonl").exists())

    def test_export_audit(self):
        run_cli(["-c", "triad hello"], home=self.tmp)
        dest = self.tmp / "my_audit.jsonl"
        r = run_cli(["--export-audit", str(dest)], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = [json.loads(l) for l in dest.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["body"]["event"], "triad")
        r = run_cli(["--export-audit"], home=self.tmp)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, dest.read_text(encoding="utf-8"))

    def test_rules_command(self):
        r = run_cli(["-c", "rules"], home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rule_1", r.stdout)
        self.assertIn("planned", r.stdout)
        self.assertIn("enforced", r.stdout)
        r = run_cli(["-c", "rules rule_8"], home=self.tmp)
        self.assertIn("eval", r.stdout)
        self.assertIn("enforced", r.stdout)
        r = run_cli(["-c", "rules rule_99"], home=self.tmp)
        self.assertIn("unknown", r.stdout.lower())

    def test_no_api_key_needed_and_none_printed(self):
        r = run_cli(["-c", "plan-grok hello"], home=self.tmp)
        self.assertIn("no API key found", r.stdout)
        self.assertNotIn("xai-", r.stdout.replace("'xai-...'", "").replace("=xai-...", ""))


if __name__ == "__main__":
    unittest.main()
