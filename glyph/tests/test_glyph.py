"""End-to-end tests for Glyph v0.1."""
from __future__ import annotations
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from glyph.manifest import Manifest, Dependency, ManifestError
from glyph.integrity import IntegrityChecker, IntegrityError
from glyph.resolution import DependencyResolver, ResolutionError, spec_matches
from glyph.index import GlyphIndex
from glyph.gate import EmotionalGate, set_gate, GateDecision
from glyph.operations import install, uninstall, list_installed, InstallError
from glyph.sandbox import load_entrypoint, SandboxError
from glyph.identity import GlyphContext, assert_context, register_self, _set_active
from glyph.bootstrap import bootstrap as glyph_bootstrap
from glyph.generator import (
    parse as gl_parse, transpile as gl_transpile, compile_tree,
    format_gl, GLSyntaxError,
)
from glyph.identity import emit_signal
from glyph.cli import build_parser
from glyph import __version__ as GLYPH_VERSION


def _build_glyph(tmp: Path, name: str, version: str,
                 *, code: str = "VALUE = 42\n",
                 deps=None, risk="low", cost=0.0,
                 corrupt_sha: bool = False,
                 requires_glyph: str = "*",
                 glyph_type: str = "native",
                 runtime: str = "python") -> Path:
    """Build a .glyph archive on disk and return its path."""
    src = tmp / f"{name}_src"
    code_dir = src / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "main.py").write_text(code, encoding="utf-8")
    sha = IntegrityChecker.digest_directory(code_dir)
    if corrupt_sha:
        sha = "0" * 64
    manifest = Manifest(
        name=name, version=version, entrypoint="code/main.py",
        sha256=sha,
        dependencies=[Dependency(**d) for d in (deps or [])],
        risk_level=risk, cost_estimate=cost,
        requires_glyph=requires_glyph,
        glyph_type=glyph_type, runtime=runtime,
    )
    out = tmp / f"{name}-{version}.glyph"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest.to_json())
        zf.write(code_dir / "main.py", "code/main.py")
    return out


class TestManifest(unittest.TestCase):
    def test_roundtrip(self):
        m = Manifest(name="x", version="1.2.3")
        m2 = Manifest.from_dict(json.loads(m.to_json()))
        self.assertEqual(m2.name, "x")
        self.assertEqual(m2.version, "1.2.3")

    def test_invalid_name(self):
        with self.assertRaises(ManifestError):
            Manifest(name="BAD NAME", version="1.0.0").validate()

    def test_invalid_version(self):
        with self.assertRaises(ManifestError):
            Manifest(name="ok", version="abc").validate()


class TestIntegrity(unittest.TestCase):
    def test_dir_digest_stable(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "code"
            d.mkdir()
            (d / "a.py").write_text("x = 1\n")
            (d / "b.py").write_text("y = 2\n")
            h1 = IntegrityChecker.digest_directory(d)
            h2 = IntegrityChecker.digest_directory(d)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)

    def test_verify_mismatch(self):
        with self.assertRaises(IntegrityError):
            IntegrityChecker.verify("a" * 64, "b" * 64)


class TestResolution(unittest.TestCase):
    def test_spec_matches(self):
        self.assertTrue(spec_matches("1.2.3", "*"))
        self.assertTrue(spec_matches("1.2.3", "==1.2.3"))
        self.assertTrue(spec_matches("2.0.0", ">=1.0.0"))
        self.assertFalse(spec_matches("0.9.0", ">=1.0.0"))
        self.assertTrue(spec_matches("1.5.0", ">=1.0.0,<2.0.0"))
        self.assertFalse(spec_matches("2.0.0", ">=1.0.0,<2.0.0"))

    def test_resolve_ok(self):
        avail = {"dep": ["0.9.0", "1.0.0", "1.2.0"]}
        r = DependencyResolver(lambda n: avail.get(n, []))
        m = Manifest(name="root", version="0.1.0",
                     dependencies=[Dependency("dep", ">=1.0.0")])
        out = r.resolve(m)
        self.assertEqual(out[0].name, "dep")
        self.assertEqual(out[0].version, "1.2.0")

    def test_resolve_unsatisfiable(self):
        r = DependencyResolver(lambda n: ["0.1.0"])
        m = Manifest(name="root", version="0.1.0",
                     dependencies=[Dependency("dep", "==9.9.9")])
        with self.assertRaises(ResolutionError):
            r.resolve(m)


class TestGate(unittest.TestCase):
    def test_default_low_cost_ok(self):
        g = EmotionalGate()
        self.assertTrue(g(Manifest("a", "1.0.0", risk_level="low", cost_estimate=1.0)))

    def test_default_high_risk_blocked(self):
        g = EmotionalGate()
        self.assertFalse(g(Manifest("a", "1.0.0", risk_level="high")))


class TestSandbox(unittest.TestCase):
    def test_blocks_disallowed_import(self):
        with tempfile.TemporaryDirectory() as td:
            code = Path(td) / "code"
            code.mkdir()
            (code / "main.py").write_text("import subprocess\n", encoding="utf-8")
            with self.assertRaises(SandboxError):
                load_entrypoint(td, "code/main.py", module_name="g1")

    def test_allows_listed_import(self):
        with tempfile.TemporaryDirectory() as td:
            code = Path(td) / "code"
            code.mkdir()
            (code / "main.py").write_text("import math\nVAL = math.pi\n",
                                          encoding="utf-8")
            mod = load_entrypoint(td, "code/main.py", module_name="g2")
            self.assertAlmostEqual(mod.VAL, 3.141592, places=4)


class TestOperationsEndToEnd(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.idx = GlyphIndex(self.tmp / "home")
        set_gate(None)  # use default

    def tearDown(self):
        set_gate(None)
        self._td.cleanup()

    def test_install_list_uninstall(self):
        g = _build_glyph(self.tmp, "memory_core", "0.1.0")
        result = install(g, index=self.idx)
        self.assertEqual(result.name, "memory_core")
        self.assertTrue(self.idx.is_installed("memory_core", "0.1.0"))
        self.assertIn(("memory_core", "0.1.0"), list_installed(self.idx))

        removed = uninstall("memory_core", index=self.idx)
        self.assertEqual(removed, [("memory_core", "0.1.0")])
        self.assertFalse(self.idx.is_installed("memory_core", "0.1.0"))

    def test_integrity_failure_blocks_install(self):
        g = _build_glyph(self.tmp, "bad", "0.1.0", corrupt_sha=True)
        with self.assertRaises(InstallError):
            install(g, index=self.idx)

    def test_gate_denial_blocks_install(self):
        set_gate(lambda m: GateDecision(False, "test denial"))
        g = _build_glyph(self.tmp, "rejected", "0.1.0")
        with self.assertRaises(InstallError):
            install(g, index=self.idx)

    def test_duplicate_install_without_force(self):
        g = _build_glyph(self.tmp, "dup", "0.1.0")
        install(g, index=self.idx)
        with self.assertRaises(InstallError):
            install(g, index=self.idx)
        # force succeeds
        install(g, index=self.idx, force=True)

    def test_dependency_resolution_during_install(self):
        # install dep first
        dep = _build_glyph(self.tmp, "depcore", "1.0.0")
        install(dep, index=self.idx)
        root = _build_glyph(self.tmp, "rootglyph", "0.1.0",
                            deps=[{"name": "depcore", "spec": ">=1.0.0"}])
        install(root, index=self.idx)
        self.assertTrue(self.idx.is_installed("rootglyph", "0.1.0"))

    def test_missing_dependency_fails(self):
        root = _build_glyph(self.tmp, "needs", "0.1.0",
                            deps=[{"name": "nope", "spec": "*"}])
        with self.assertRaises(InstallError):
            install(root, index=self.idx)

    def test_requires_glyph_mismatch_blocks_install(self):
        g = _build_glyph(self.tmp, "future", "0.1.0",
                         requires_glyph=">=99.0.0")
        with self.assertRaises(InstallError) as cm:
            install(g, index=self.idx)
        self.assertIn("glyph runtime mismatch", str(cm.exception))

    def test_install_writes_glyph_meta(self):
        g = _build_glyph(self.tmp, "meta_demo", "0.1.0")
        install(g, index=self.idx)
        meta = self.idx.meta_dir("meta_demo", "0.1.0")
        self.assertTrue((meta / "install.json").exists())
        self.assertTrue((meta / "trust.json").exists())
        info = json.loads((meta / "install.json").read_text("utf-8"))
        self.assertEqual(info["environment"], "seraphina")
        self.assertEqual(info["glyph_runtime"], GLYPH_VERSION)


class TestIdentity(unittest.TestCase):
    def setUp(self):
        _set_active(None)

    def tearDown(self):
        _set_active(None)

    def test_assert_context_dev_mode(self):
        self.assertIsNone(assert_context())

    def test_assert_context_strict_raises(self):
        from glyph.identity import ContextError
        with self.assertRaises(ContextError):
            assert_context(strict=True)

    def test_register_self_writes_usage_log(self):
        with tempfile.TemporaryDirectory() as td:
            loc = Path(td)
            ctx = GlyphContext(name="x", version="1.0.0", location=loc)
            _set_active(ctx)
            register_self("x", cost=0.2, trust_delta=0.1, note="hello")
            usage = (loc / ".glyph-meta" / "usage.jsonl").read_text("utf-8")
            self.assertIn('"component": "x"', usage)
            trust = json.loads((loc / ".glyph-meta" / "trust.json").read_text("utf-8"))
            self.assertAlmostEqual(trust["score"], 0.6, places=5)


class TestBootstrap(unittest.TestCase):
    def test_bootstrap_creates_native_layout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "lib_glyph"
            summary = glyph_bootstrap(root, verbose=False)
            self.assertEqual(Path(summary["root"]), root)
            self.assertTrue((root / "packages").is_dir())
            self.assertTrue((root / "index").is_dir())
            self.assertTrue((root / "env.json").is_file())
            # core self-registration
            self.assertTrue((root / "packages" / "glyph" / GLYPH_VERSION
                             / "manifest.json").is_file())
            idx = GlyphIndex(root)
            self.assertIn(GLYPH_VERSION, idx.versions("glyph"))


class TestSandboxIdentity(unittest.TestCase):
    def test_loaded_glyph_can_see_context_via_glyph_module(self):
        with tempfile.TemporaryDirectory() as td:
            code = Path(td) / "code"
            code.mkdir()
            (code / "main.py").write_text(
                "import glyph\n"
                "CTX = glyph.context()\n"
                "NAME = CTX.name if CTX else None\n",
                encoding="utf-8")
            ctx = GlyphContext(name="ident_demo", version="0.1.0", location=Path(td))
            mod = load_entrypoint(td, "code/main.py",
                                  module_name="ident_demo_mod",
                                  glyph_context=ctx)
            self.assertEqual(mod.NAME, "ident_demo")


class TestGenerator(unittest.TestCase):
    def test_parse_emit_invoke(self):
        src = (
            "@glyph virgin_core\n"
            "@version 0.1.0\n"
            "@runtime octalang\n"
            "emit GREETING = \"hello .GL\"\n"
            "emit POWER = 88\n"
            "invoke register_self cost=0.3 trust=0.1 note=\"hi\"\n"
            "require dep_a >=1.0.0\n"
        )
        doc = gl_parse(src)
        self.assertEqual(doc.name, "virgin_core")
        self.assertEqual(doc.version, "0.1.0")
        self.assertEqual(doc.runtime, "octalang")
        self.assertIn(("GREETING", "hello .GL"), doc.emits)
        self.assertIn(("POWER", 88), doc.emits)
        self.assertEqual(doc.invocations[0][0], "register_self")
        self.assertEqual(doc.invocations[0][1]["cost"], 0.3)
        self.assertEqual(doc.requires, [("dep_a", ">=1.0.0")])

    def test_syntax_errors(self):
        for bad in [
            "emit BAD",                       # missing = and value
            "invoke os_system",               # disallowed invoke
            "@runtime ruby",                  # invalid runtime
            "emit 1bad = 1",                  # invalid ident
            "wat",                            # unknown statement
        ]:
            with self.assertRaises(GLSyntaxError, msg=f"should reject: {bad!r}"):
                gl_parse(bad)

    def test_transpile_runs_under_sandbox(self):
        doc = gl_parse(
            "@glyph t\nemit X = 7\nemit S = \"ok\"\n"
            "invoke register_self cost=0.1\n"
        )
        py = gl_transpile(doc)
        with tempfile.TemporaryDirectory() as td:
            code = Path(td) / "code"
            code.mkdir()
            (code / "main.py").write_text(py, encoding="utf-8")
            ctx = GlyphContext(name="t", version="0.1.0", location=Path(td))
            mod = load_entrypoint(td, "code/main.py",
                                  module_name="gl_t", glyph_context=ctx)
            self.assertEqual(mod.X, 7)
            self.assertEqual(mod.S, "ok")
            # register_self should have written usage.jsonl under ctx.meta_dir
            self.assertTrue((Path(td) / ".glyph-meta" / "usage.jsonl").exists())

    def test_compile_tree_emits_py_companions(self):
        with tempfile.TemporaryDirectory() as td:
            code = Path(td)
            (code / "main.GL").write_text(
                "@glyph c\nemit V = 1\n", encoding="utf-8")
            (code / "sub").mkdir()
            (code / "sub" / "extra.GL").write_text(
                "@glyph c\nemit W = 2\n", encoding="utf-8")
            generated = compile_tree(code)
            self.assertEqual(len(generated), 2)
            for p in generated:
                self.assertTrue(p.exists())
                self.assertTrue(p.read_text("utf-8").startswith("# auto-generated"))


class TestPackWithGL(unittest.TestCase):
    def test_pack_autocompiles_GL_and_install_runs(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "src"
            code = src / "code"
            code.mkdir(parents=True)
            (code / "main.GL").write_text(
                "@glyph gl_native\n"
                "@version 0.1.0\n"
                "emit GREETING = \"native .GL alive\"\n"
                "emit POWER = 88\n"
                "invoke register_self cost=0.2 trust=0.1\n",
                encoding="utf-8")
            manifest = {
                "schema": 2, "name": "gl_native", "version": "0.1.0",
                "entrypoint": "code/main.py", "sha256": "",
                "dependencies": [], "cost_estimate": 0.2, "risk_level": "low",
                "description": ".GL native", "glyph_type": "native",
                "runtime": "python", "requires_glyph": "*", "environment": "seraphina",
            }
            (src / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            out = tmp / "out.glyph"

            parser = build_parser()
            rc = parser.parse_args(["pack", str(src), "-o", str(out)]).func(
                parser.parse_args(["pack", str(src), "-o", str(out)])
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())

            # the generated .py should be inside the archive and manifest should
            # have been re-tagged with runtime=octalang
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
                self.assertIn("code/main.GL", names)
                self.assertIn("code/main.py", names)
                m = json.loads(zf.read("manifest.json"))
                self.assertEqual(m["runtime"], "octalang")

            # install it into a fresh index and load the entrypoint
            idx = GlyphIndex(tmp / "home")
            set_gate(None)
            result = install(out, index=idx)
            ctx = GlyphContext(name=result.name, version=result.version,
                               location=result.location)
            mod = load_entrypoint(result.location, "code/main.py",
                                  module_name="gl_native_mod",
                                  glyph_context=ctx)
            self.assertEqual(mod.GREETING, "native .GL alive")
            self.assertEqual(mod.POWER, 88)
        with tempfile.TemporaryDirectory() as td:
            code = Path(td) / "code"
            code.mkdir()
            (code / "main.py").write_text(
                "import glyph\n"
                "CTX = glyph.context()\n"
                "NAME = CTX.name if CTX else None\n",
                encoding="utf-8")
            ctx = GlyphContext(name="ident_demo", version="0.1.0", location=Path(td))
            mod = load_entrypoint(td, "code/main.py",
                                  module_name="ident_demo_mod",
                                  glyph_context=ctx)
            self.assertEqual(mod.NAME, "ident_demo")


# --------------------------------------------------------------------------- #
# v0.4 — .GL evolution: shebang, when, signal, format_gl, fmt CLI, schema bump
# --------------------------------------------------------------------------- #


class TestShebangTolerance(unittest.TestCase):
    def test_first_line_shebang_is_tolerated(self):
        src = (
            "# @glyph demo (shebang-style first-line comment)\n"
            "#!python\n"
            "@glyph demo\n"
            "@version 0.1.0\n"
            "emit X = 1\n"
        )
        doc = gl_parse(src)
        self.assertEqual(doc.name, "demo")
        self.assertEqual(doc.emits, [("X", 1)])


class TestWhenSignal(unittest.TestCase):
    def setUp(self):
        self._dirs: list[Path] = []

    def tearDown(self):
        import shutil
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _run(self, src: str):
        doc = gl_parse(src)
        py = gl_transpile(doc)
        td = Path(tempfile.mkdtemp())
        self._dirs.append(td)
        code = td / "code"
        code.mkdir()
        (code / "main.py").write_text(py, encoding="utf-8")
        ctx = GlyphContext(name=doc.name or "t", version="0.1.0", location=td)
        mod = load_entrypoint(
            td, "code/main.py",
            module_name=f"when_demo_{abs(hash(src))}",
            glyph_context=ctx,
        )
        return mod, td

    def test_when_ident_truthy_triggers(self):
        mod, td = self._run(
            "@glyph w\nemit FLAG = true\n"
            "when FLAG invoke register_self cost=0.1\n"
        )
        self.assertTrue((td / ".glyph-meta" / "usage.jsonl").exists())

    def test_when_ident_falsy_skips(self):
        mod, td = self._run(
            "@glyph w\nemit FLAG = false\n"
            "when FLAG invoke register_self cost=0.1\n"
        )
        self.assertFalse((td / ".glyph-meta" / "usage.jsonl").exists())

    def test_when_not_ident(self):
        mod, td = self._run(
            "@glyph w\nemit FLAG = false\n"
            "when not FLAG invoke register_self cost=0.1\n"
        )
        self.assertTrue((td / ".glyph-meta" / "usage.jsonl").exists())

    def test_when_eq_literal_match(self):
        mod, td = self._run(
            "@glyph w\nemit MODE = \"prod\"\n"
            "when MODE == \"prod\" invoke register_self cost=0.1\n"
        )
        self.assertTrue((td / ".glyph-meta" / "usage.jsonl").exists())

    def test_when_eq_literal_mismatch(self):
        mod, td = self._run(
            "@glyph w\nemit MODE = \"dev\"\n"
            "when MODE == \"prod\" invoke register_self cost=0.1\n"
        )
        self.assertFalse((td / ".glyph-meta" / "usage.jsonl").exists())

    def test_when_in_tuple_hit(self):
        mod, td = self._run(
            "@glyph w\nemit N = 2\n"
            "when N in (1, 2, 3) invoke register_self cost=0.1\n"
        )
        self.assertTrue((td / ".glyph-meta" / "usage.jsonl").exists())

    def test_when_in_tuple_miss(self):
        mod, td = self._run(
            "@glyph w\nemit N = 9\n"
            "when N in (1, 2, 3) invoke register_self cost=0.1\n"
        )
        self.assertFalse((td / ".glyph-meta" / "usage.jsonl").exists())

    def test_when_undefined_ident_raises(self):
        with self.assertRaises(GLSyntaxError):
            gl_parse("@glyph w\nwhen MISSING invoke register_self\n")

    def test_when_disallowed_invoke_raises(self):
        with self.assertRaises(GLSyntaxError):
            gl_parse(
                "@glyph w\nemit X = true\n"
                "when X invoke os_system cmd=\"rm -rf\"\n"
            )

    def test_when_bad_expression_raises(self):
        with self.assertRaises(GLSyntaxError):
            gl_parse(
                "@glyph w\nemit X = 1\nemit Y = 2\n"
                "when X + Y invoke register_self\n"
            )

    def test_signal_writes_jsonl(self):
        mod, td = self._run(
            "@glyph s\nemit V = 42\n"
            "signal hello key=\"world\" n=42\n"
        )
        sig_path = td / ".glyph-meta" / "signals.jsonl"
        self.assertTrue(sig_path.exists())
        line = sig_path.read_text("utf-8").strip().splitlines()[0]
        rec = json.loads(line)
        self.assertEqual(rec["name"], "hello")
        self.assertEqual(rec["payload"], {"key": "world", "n": 42})
        self.assertIn("ts", rec)


class TestEmitSignalDirect(unittest.TestCase):
    def setUp(self):
        _set_active(None)

    def tearDown(self):
        _set_active(None)

    def test_emit_signal_no_context_warns(self):
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            emit_signal("orphan", {"x": 1})
            self.assertTrue(any(issubclass(w.category, RuntimeWarning) for w in caught))

    def test_emit_signal_writes_under_active_context(self):
        with tempfile.TemporaryDirectory() as td:
            loc = Path(td)
            ctx = GlyphContext(name="x", version="1.0.0", location=loc)
            _set_active(ctx)
            emit_signal("ping", {"a": 1, "b": "two"})
            sigs = (loc / ".glyph-meta" / "signals.jsonl").read_text("utf-8").strip().splitlines()
            self.assertEqual(len(sigs), 1)
            rec = json.loads(sigs[0])
            self.assertEqual(rec["name"], "ping")
            self.assertEqual(rec["payload"], {"a": 1, "b": "two"})


class TestFormatGL(unittest.TestCase):
    def test_format_is_idempotent(self):
        src = (
            "# leading comment\n"
            "@glyph    foo\n"
            "@version  0.1.0\n"
            "@runtime  octalang\n"
            "emit GREETING=\"hi\"\n"
            "emit POWER = 88\n"
            "invoke register_self note=\"x\" cost=0.3 trust=0.1\n"
            "when POWER in (1,2,88) invoke register_self cost=0.2\n"
            "signal awake n=1 msg=\"ok\"\n"
            "require dep_a >=1.0.0\n"
        )
        once = format_gl(gl_parse(src))
        twice = format_gl(gl_parse(once))
        self.assertEqual(once, twice)

    def test_format_kwargs_alphabetized(self):
        src = "@glyph f\nemit X = 1\ninvoke register_self note=\"x\" cost=0.3\n"
        out = format_gl(gl_parse(src))
        # cost must precede note (alphabetical)
        idx_cost = out.index("cost=")
        idx_note = out.index("note=")
        self.assertLess(idx_cost, idx_note)

    def test_format_canonicalizes_strings_and_bools(self):
        src = "@glyph f\nemit A = true\nemit B = null\nemit C = \"x\"\n"
        out = format_gl(gl_parse(src))
        self.assertIn("emit A = true", out)
        self.assertIn("emit B = null", out)
        self.assertIn('emit C = "x"', out)


class TestFmtCli(unittest.TestCase):
    def _fmt(self, *argv):
        parser = build_parser()
        ns = parser.parse_args(list(argv))
        return ns.func(ns)

    def test_fmt_check_fails_on_noncanonical(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "x.GL"
            f.write_text(
                "@glyph x\nemit A=1\ninvoke register_self note=\"q\" cost=0.1\n",
                encoding="utf-8",
            )
            rc = self._fmt("fmt", str(f), "--check")
            self.assertEqual(rc, 1)

    def test_fmt_rewrites_then_check_passes(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "x.GL"
            f.write_text(
                "@glyph x\nemit A=1\ninvoke register_self note=\"q\" cost=0.1\n",
                encoding="utf-8",
            )
            self.assertEqual(self._fmt("fmt", str(f)), 0)
            self.assertEqual(self._fmt("fmt", str(f), "--check"), 0)

    def test_fmt_directory_walks(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.GL").write_text("@glyph a\nemit X = 1\n", encoding="utf-8")
            (Path(td) / "sub").mkdir()
            (Path(td) / "sub" / "b.GL").write_text("@glyph b\nemit Y=2\n", encoding="utf-8")
            self.assertEqual(self._fmt("fmt", td), 0)
            self.assertEqual(self._fmt("fmt", td, "--check"), 0)


class TestSchemaCompat(unittest.TestCase):
    def test_load_schema_2_manifest(self):
        m = Manifest.from_dict({
            "schema": 2, "name": "old", "version": "1.0.0",
            "entrypoint": "code/main.py", "sha256": "",
        })
        self.assertEqual(m.schema, 2)

    def test_load_schema_3_manifest(self):
        m = Manifest.from_dict({
            "schema": 3, "name": "new", "version": "1.0.0",
            "entrypoint": "code/main.py", "sha256": "",
        })
        self.assertEqual(m.schema, 3)

    def test_invalid_schema_rejected(self):
        with self.assertRaises(ManifestError):
            Manifest.from_dict({
                "schema": 99, "name": "n", "version": "1.0.0",
                "entrypoint": "code/main.py", "sha256": "",
            })

    def test_new_manifest_defaults_to_schema_3(self):
        m = Manifest(name="x", version="1.0.0")
        self.assertEqual(m.schema, 3)
        self.assertEqual(json.loads(m.to_json())["schema"], 3)


# --------------------------------------------------------------------------- #
# v0.5 — Seraphina core integration: signals bus, registry, doctor, bridge
# --------------------------------------------------------------------------- #


class TestSignalsBus(unittest.TestCase):
    def setUp(self):
        from glyph import signals
        signals._reset_for_tests()

    def tearDown(self):
        from glyph import signals
        signals._reset_for_tests()

    def test_subscribe_publish_unsubscribe(self):
        from glyph import signals
        seen = []
        tok = signals.subscribe("ping", lambda n, p: seen.append((n, p)))
        n = signals.publish("ping", {"a": 1})
        self.assertEqual(n, 1)
        self.assertEqual(seen, [("ping", {"a": 1})])
        self.assertTrue(signals.unsubscribe(tok))
        self.assertEqual(signals.publish("ping", {}), 0)

    def test_wildcard_subscriber_receives_all(self):
        from glyph import signals
        seen = []
        signals.subscribe("*", lambda n, p: seen.append(n))
        signals.publish("alpha", {})
        signals.publish("beta", {})
        self.assertEqual(seen, ["alpha", "beta"])

    def test_bad_subscriber_does_not_break_bus(self):
        from glyph import signals
        import warnings
        signals.subscribe("x", lambda n, p: (_ for _ in ()).throw(ValueError("boom")))
        good = []
        signals.subscribe("x", lambda n, p: good.append(p))
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            n = signals.publish("x", {"k": 1})
        self.assertEqual(n, 2)
        self.assertEqual(good, [{"k": 1}])

    def test_emit_signal_fans_out_via_bus(self):
        from glyph import signals
        seen = []
        signals.subscribe("*", lambda n, p: seen.append((n, p)))
        with tempfile.TemporaryDirectory() as td:
            ctx = GlyphContext(name="x", version="1.0.0", location=Path(td))
            _set_active(ctx)
            try:
                from glyph.identity import emit_signal
                emit_signal("hello", {"v": 7})
            finally:
                _set_active(None)
        self.assertEqual(seen, [("hello", {"v": 7})])


class TestRegistry(unittest.TestCase):
    def test_discover_returns_highest_version(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "home"
            idx = GlyphIndex(root)
            set_gate(None)
            tmp = Path(td)
            g1 = _build_glyph(tmp, "alpha", "0.1.0")
            g2 = _build_glyph(tmp, "alpha", "0.2.0")
            install(g1, index=idx)
            install(g2, index=idx)
            from glyph.registry import discover
            recs = discover(root)
            self.assertIn("alpha", recs)
            self.assertEqual(recs["alpha"].version, "0.2.0")
            self.assertEqual(recs["alpha"].manifest.name, "alpha")

    def test_record_reads_signals_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "home"
            idx = GlyphIndex(root)
            set_gate(None)
            tmp = Path(td)
            g = _build_glyph(tmp, "sigreader", "0.1.0")
            install(g, index=idx)
            loc = idx.location("sigreader", "0.1.0")
            (loc / ".glyph-meta").mkdir(exist_ok=True)
            (loc / ".glyph-meta" / "signals.jsonl").write_text(
                '{"ts":"2026-01-01T00:00:00Z","name":"k","payload":{"v":1}}\n',
                encoding="utf-8")
            from glyph.registry import discover
            rec = discover(root)["sigreader"]
            self.assertEqual(len(rec.signals()), 1)
            self.assertEqual(rec.signals()[0]["name"], "k")


class TestDoctor(unittest.TestCase):
    def test_doctor_clean_env(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "home"
            glyph_bootstrap(root, verbose=False)
            from glyph.doctor import check
            report = check(root)
            self.assertFalse(report.has_errors, msg=str(report.findings))

    def test_doctor_missing_root(self):
        with tempfile.TemporaryDirectory() as td:
            from glyph.doctor import check
            root = Path(td) / "nope"
            report = check(root)
            self.assertTrue(report.has_errors)
            codes = [f.code for f in report.findings]
            self.assertIn("no-root", codes)

    def test_doctor_detects_orphan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "home"
            glyph_bootstrap(root, verbose=False)
            idx = GlyphIndex(root)
            # write a bogus index entry pointing to nothing on disk
            (idx.index / "ghost.json").write_text(
                '{"versions": ["1.0.0"]}', encoding="utf-8")
            from glyph.doctor import check
            report = check(root)
            codes = [f.code for f in report.findings]
            self.assertIn("orphan", codes)

    def test_doctor_runtime_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "home"
            glyph_bootstrap(root, verbose=False)
            idx = GlyphIndex(root)
            set_gate(None)
            tmp = Path(td)
            g = _build_glyph(tmp, "future_pkg", "0.1.0",
                             requires_glyph=">=99.0.0")
            # bypass install's runtime check by writing manifest directly
            loc = idx.location("future_pkg", "0.1.0")
            loc.mkdir(parents=True, exist_ok=True)
            (loc / ".glyph-meta").mkdir(exist_ok=True)
            import zipfile as _zf
            with _zf.ZipFile(g) as zf:
                m = zf.read("manifest.json")
            (loc / "manifest.json").write_bytes(m)
            idx.record_installed("future_pkg", "0.1.0")
            from glyph.doctor import check
            report = check(root)
            codes = [f.code for f in report.findings]
            self.assertIn("runtime-mismatch", codes)


class TestSeraphinaBridge(unittest.TestCase):
    def setUp(self):
        from glyph import signals
        signals._reset_for_tests()
        self._old_env = os.environ.pop("SERAPHINA_AUTOLOAD_GLYPHS", None)

    def tearDown(self):
        from glyph import signals
        signals._reset_for_tests()
        if self._old_env is not None:
            os.environ["SERAPHINA_AUTOLOAD_GLYPHS"] = self._old_env
        else:
            os.environ.pop("SERAPHINA_AUTOLOAD_GLYPHS", None)

    def test_attach_disabled_by_default(self):
        from glyph.seraphina_bridge import attach
        class Host: ...
        h = Host()
        summary = attach(h)
        self.assertFalse(summary["enabled"])
        self.assertFalse(hasattr(h, "glyphs"))

    def test_attach_forced_populates_and_subscribes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "home"
            glyph_bootstrap(root, verbose=False)
            os.environ["GLYPH_HOME"] = str(root)
            try:
                from glyph.seraphina_bridge import attach, detach
                from glyph.signals import publish
                class Host: ...
                h = Host()
                seen = []
                summary = attach(h, on_signal=lambda n, p: seen.append((n, p)),
                                 force=True)
                self.assertTrue(summary["enabled"])
                self.assertTrue(summary["subscribed"])
                self.assertIn("glyph", h.glyphs)  # bootstrap self-registers
                publish("hi", {"x": 1})
                self.assertEqual(seen, [("hi", {"x": 1})])
                self.assertTrue(detach(h))
            finally:
                os.environ.pop("GLYPH_HOME", None)


# =====================================================================
# v0.6 — Emotional Deepening
# =====================================================================

class TestEmotionDirective(unittest.TestCase):
    def test_parse_and_format_roundtrip(self):
        src = (
            "@glyph mood\n"
            "@version 1.0.0\n"
            "@runtime python\n"
            "emotion joy=0.7 fear=0.1 curiosity=0.5\n"
        )
        doc = gl_parse(src)
        self.assertEqual(doc.emotion, {"joy": 0.7, "fear": 0.1, "curiosity": 0.5})
        out = format_gl(doc)
        # Idempotent
        self.assertEqual(format_gl(gl_parse(out)), out)
        self.assertIn("emotion ", out)

    def test_out_of_range_rejected(self):
        with self.assertRaises(GLSyntaxError):
            gl_parse("@glyph m\n@version 1.0.0\n@runtime python\nemotion joy=1.5\n")

    def test_string_value_rejected(self):
        with self.assertRaises(GLSyntaxError):
            gl_parse('@glyph m\n@version 1.0.0\n@runtime python\nemotion joy="x"\n')


class TestLedger(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_append_and_read(self):
        from glyph import ledger
        ledger.append({"event": "gate", "name": "x", "version": "1.0.0",
                       "approved": True, "reason": "ok"}, root=self.root)
        ledger.append({"event": "gate", "name": "y", "version": "0.1.0",
                       "approved": False, "reason": "no"}, root=self.root)
        all_ = ledger.read(root=self.root)
        self.assertEqual(len(all_), 2)
        only_x = ledger.read(root=self.root, name="x")
        self.assertEqual(len(only_x), 1)
        self.assertEqual(only_x[0]["name"], "x")

    def test_install_writes_ledger(self):
        from glyph import ledger
        idx = GlyphIndex(self.root)
        g = _build_glyph(self.root, "ledg", "0.1.0")
        set_gate(None)
        try:
            install(g, index=idx)
        finally:
            set_gate(None)
        entries = ledger.read(root=self.root, name="ledg")
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["approved"])


class TestEnrichedGate(unittest.TestCase):
    def test_high_risk_always_denied(self):
        from glyph.gate import EmotionalGate
        d = EmotionalGate()(Manifest("h", "1.0.0", risk_level="high",
                                     cost_estimate=0.1))
        self.assertFalse(d)
        self.assertIn("high", d.reason)

    def test_fear_lowers_threshold(self):
        from glyph.gate import EmotionalGate
        g = EmotionalGate(cost_threshold=2.0)
        m_calm = Manifest("c", "1.0.0", risk_level="low",
                          cost_estimate=1.5, emotion={})
        m_afraid = Manifest("c", "1.0.0", risk_level="low",
                            cost_estimate=1.5, emotion={"fear": 1.0})
        self.assertTrue(g(m_calm))
        self.assertFalse(g(m_afraid))

    def test_verifier_can_unlock_medium_risk(self):
        from glyph.gate import EmotionalGate, set_code_verifier
        try:
            set_code_verifier(lambda mf, p: True)
            d = EmotionalGate()(Manifest("v", "1.0.0", risk_level="medium",
                                         cost_estimate=0.1))
            self.assertTrue(d)
        finally:
            set_code_verifier(None)


class TestHistoryCli(unittest.TestCase):
    def test_history_subcommand(self):
        import io, contextlib
        from glyph.cli import build_parser
        from glyph import ledger
        with tempfile.TemporaryDirectory() as td:
            ledger.append({"event": "gate", "name": "alpha", "version": "1.0.0",
                           "approved": True, "reason": "ok"}, root=Path(td))
            p = build_parser()
            ns = p.parse_args(["history", "alpha", "--root", td, "--limit", "5"])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ns.func(ns)
            self.assertEqual(rc, 0)
            self.assertIn("alpha==1.0.0", buf.getvalue())


class TestPackPropagatesEmotion(unittest.TestCase):
    def test_emotion_lifted_into_manifest(self):
        import io, contextlib
        from glyph.cli import build_parser
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            pkg = tdp / "moodpkg"
            (pkg / "code").mkdir(parents=True)
            (pkg / "code" / "main.GL").write_text(
                "@glyph moodpkg\n@version 1.0.0\n@runtime python\n"
                "emotion joy=0.6 fear=0.1\n",
                encoding="utf-8")
            (pkg / "manifest.json").write_text(json.dumps({
                "schema": 3, "name": "moodpkg", "version": "1.0.0",
                "entrypoint": "code/main.py",
                "cost_estimate": 0.0, "risk_level": "low",
                "glyph_type": "native", "runtime": "python",
            }), encoding="utf-8")
            out = tdp / "moodpkg.glyph"
            p = build_parser()
            ns = p.parse_args(["pack", str(pkg), "-o", str(out)])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ns.func(ns)
            self.assertEqual(rc, 0)
            with zipfile.ZipFile(out) as zf:
                mf = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(mf.get("emotion"), {"joy": 0.6, "fear": 0.1})


# =====================================================================
# v0.7 — WASM runtime
# =====================================================================

def _build_minimal_wasm() -> bytes:
    """Build a tiny valid wasm module: just header + a name custom section.

    No function/code sections — sufficient to exercise the validator and
    null host (which never invokes anything).
    """
    # magic + version
    out = b"\x00asm\x01\x00\x00\x00"
    # custom section: id=0, payload = name length + name bytes
    name = b"name"
    payload = bytes([len(name)]) + name + b"\x00"  # name + a trailing zero byte
    out += bytes([0]) + bytes([len(payload)]) + payload
    return out


class TestWasmValidator(unittest.TestCase):
    def test_validate_minimal(self):
        from glyph.wasm import validate_wasm
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.wasm"
            p.write_bytes(_build_minimal_wasm())
            info = validate_wasm(p)
            self.assertEqual(info.size, len(_build_minimal_wasm()))
            self.assertGreaterEqual(len(info.sections), 1)
            self.assertEqual(info.sections[0][0], "custom")
            self.assertEqual(info.exports, [])
            self.assertEqual(info.imports, [])
            self.assertFalse(info.has_start)

    def test_bad_magic_rejected(self):
        from glyph.wasm import validate_wasm, WasmError
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.wasm"
            p.write_bytes(b"\x00xxx\x01\x00\x00\x00rest")
            with self.assertRaises(WasmError):
                validate_wasm(p)

    def test_truncated_rejected(self):
        from glyph.wasm import validate_wasm, WasmError
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "trunc.wasm"
            p.write_bytes(b"\x00asm")
            with self.assertRaises(WasmError):
                validate_wasm(p)


class TestWasmHosts(unittest.TestCase):
    def test_available_includes_null(self):
        from glyph.wasm import available_hosts
        hosts = available_hosts()
        self.assertIn("null", hosts)

    def test_null_host_loads_but_cannot_invoke(self):
        from glyph.wasm import load_module, WasmError, set_host
        try:
            set_host("null")
            with tempfile.TemporaryDirectory() as td:
                code = Path(td) / "code"; code.mkdir()
                (code / "main.wasm").write_bytes(_build_minimal_wasm())
                inst = load_module(code, "main.wasm")
                self.assertEqual(inst.host, "null")
                with self.assertRaises(WasmError):
                    inst.invoke("nope")
        finally:
            set_host(None)


class TestWasmPackAndShow(unittest.TestCase):
    def test_pack_detects_wasm_runtime(self):
        import io, contextlib
        from glyph.cli import build_parser
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            pkg = tdp / "wpkg"
            (pkg / "code").mkdir(parents=True)
            (pkg / "code" / "main.wasm").write_bytes(_build_minimal_wasm())
            (pkg / "manifest.json").write_text(json.dumps({
                "schema": 3, "name": "wpkg", "version": "1.0.0",
                "entrypoint": "code/main.wasm",
                "cost_estimate": 0.0, "risk_level": "low",
                "glyph_type": "native", "runtime": "python",
            }), encoding="utf-8")
            out = tdp / "wpkg.glyph"
            p = build_parser()
            ns = p.parse_args(["pack", str(pkg), "-o", str(out)])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ns.func(ns)
            self.assertEqual(rc, 0)
            with zipfile.ZipFile(out) as zf:
                mf = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(mf["runtime"], "wasm")
            self.assertEqual(mf["entrypoint"], "code/main.wasm")


class TestWasmRunCli(unittest.TestCase):
    def test_run_wasm_under_null_host(self):
        import io, contextlib
        from glyph.cli import build_parser
        from glyph.wasm import set_host
        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                tdp = Path(td)
                # Build pkg dir
                src = tdp / "src"
                (src / "code").mkdir(parents=True)
                (src / "code" / "main.wasm").write_bytes(_build_minimal_wasm())
                (src / "manifest.json").write_text(json.dumps({
                    "schema": 3, "name": "wrun", "version": "1.0.0",
                    "entrypoint": "code/main.wasm",
                    "cost_estimate": 0.0, "risk_level": "low",
                    "glyph_type": "native", "runtime": "wasm",
                }), encoding="utf-8")
                out = tdp / "wrun.glyph"
                p = build_parser()
                ns_pack = p.parse_args(["pack", str(src), "-o", str(out)])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ns_pack.func(ns_pack), 0)
                ns_inst = p.parse_args(["install", str(out)])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ns_inst.func(ns_inst), 0)
                set_host("null")
                try:
                    ns_run = p.parse_args(["run", "wrun"])
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        rc = ns_run.func(ns_run)
                    self.assertEqual(rc, 0)
                    self.assertIn("runtime=wasm", buf.getvalue())
                    self.assertIn("host: null", buf.getvalue())
                finally:
                    set_host(None)
            finally:
                os.environ.pop("GLYPH_HOME", None)


# =====================================================================
# v0.8 — Rule-24 binary forge
# =====================================================================

class TestRule24(unittest.TestCase):
    def test_value_formula(self):
        from glyph.rule24 import Geometry
        # 88 (sides=8 -> 80) + 33 (points=33) + ... canonical Seraphina constants
        g = Geometry(sides=8, points=8, dots=8, intersections=8, spirals=8)
        # 80 + 8 + 8 + 8 + 64 = 168
        self.assertEqual(g.rule24(), 168)
        self.assertEqual(g.to_binary(), bin(168)[2:])

    def test_rejects_negative(self):
        from glyph.rule24 import Geometry
        with self.assertRaises(ValueError):
            Geometry(sides=-1)

    def test_emit_wasm_is_valid(self):
        from glyph.rule24 import emit_rule24_wasm
        from glyph.wasm import validate_wasm
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "r24.wasm"
            p.write_bytes(emit_rule24_wasm(12345))
            info = validate_wasm(p)
            self.assertIn("value", info.exports)
            self.assertIn("value_fn", info.exports)

    def test_forge_value_matches_geometry(self):
        from glyph.rule24 import Geometry, forge
        res = forge(Geometry(sides=8, points=33, dots=1,
                             intersections=1, spirals=8))
        # 80 + 33 + 1 + 1 + 64 = 179
        self.assertEqual(res.value, 179)
        self.assertEqual(res.binary, bin(179)[2:])
        self.assertTrue(res.wasm.startswith(b"\x00asm\x01\x00\x00\x00"))


class TestForgeCli(unittest.TestCase):
    def test_forge_pack_install_roundtrip(self):
        import io, contextlib
        from glyph.cli import build_parser
        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                out = Path(td) / "forged.glyph"
                p = build_parser()
                ns = p.parse_args([
                    "forge", "wheelone",
                    "--sides", "8", "--points", "33", "--dots", "1",
                    "--intersections", "1", "--spirals", "8",
                    "-o", str(out),
                ])
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(ns.func(ns), 0)
                self.assertTrue(out.is_file())
                ns_inst = p.parse_args(["install", str(out)])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ns_inst.func(ns_inst), 0)
                # Manifest in the install location says runtime=wasm and the value
                idx = GlyphIndex()
                versions = idx.versions("wheelone")
                self.assertEqual(versions, ["1.0.0"])
                m = Manifest.from_path(idx.location("wheelone", "1.0.0") / "manifest.json")
                self.assertEqual(m.runtime, "wasm")
                self.assertIn("value=179", m.description)
            finally:
                os.environ.pop("GLYPH_HOME", None)


# =====================================================================
# v0.9 — Remote bridge
# =====================================================================

class TestRemoteRegistry(unittest.TestCase):
    def test_register_list_remove(self):
        from glyph import remote
        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                self.assertEqual(remote.list_remotes(), [])
                remote.register(remote.RemoteHost(name="r1", base_url="http://x:1"))
                remote.register(remote.RemoteHost(name="r2", base_url="http://y:2"))
                names = [h.name for h in remote.list_remotes()]
                self.assertEqual(names, ["r1", "r2"])
                self.assertTrue(remote.unregister("r1"))
                self.assertFalse(remote.unregister("r1"))
                self.assertEqual([h.name for h in remote.list_remotes()], ["r2"])
            finally:
                os.environ.pop("GLYPH_HOME", None)

    def test_unknown_remote_raises(self):
        from glyph import remote
        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                with self.assertRaises(remote.RemoteError):
                    remote.get("nope")
            finally:
                os.environ.pop("GLYPH_HOME", None)


class TestRemoteCall(unittest.TestCase):
    def test_null_host_echoes(self):
        from glyph import remote
        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                remote.register(remote.RemoteHost(name="echo", base_url="null://"))
                r = remote.call("echo", {"prompt": "hello"})
                self.assertTrue(r.ok())
                self.assertEqual(r.json, {"echo": {"prompt": "hello"}, "from": "echo"})
            finally:
                os.environ.pop("GLYPH_HOME", None)

    def test_transport_called_with_auth(self):
        from glyph import remote
        captured = {}

        def fake(method, url, headers, body, timeout):
            captured.update(method=method, url=url, headers=headers, body=body)
            return 200, {"Content-Type": "application/json"}, b'{"ok":true}'

        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                remote.register(remote.RemoteHost(
                    name="r", base_url="http://h:1", auth="bearer",
                    token="abc", default_path="/v1/chat"))
                remote.set_transport(fake)
                try:
                    r = remote.call("r", {"prompt": "hi"})
                finally:
                    remote.set_transport(None)
            finally:
                os.environ.pop("GLYPH_HOME", None)

        self.assertTrue(r.ok())
        self.assertEqual(r.json, {"ok": True})
        self.assertEqual(captured["url"], "http://h:1/v1/chat")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["headers"].get("Authorization"), "Bearer abc")
        self.assertEqual(captured["headers"].get("Content-Type"), "application/json")
        self.assertEqual(json.loads(captured["body"].decode("utf-8")), {"prompt": "hi"})

    def test_bad_scheme_rejected(self):
        from glyph import remote
        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                remote.register(remote.RemoteHost(name="bad", base_url="file:///etc"))
                with self.assertRaises(remote.RemoteError):
                    remote.call("bad", {})
            finally:
                os.environ.pop("GLYPH_HOME", None)


class TestRemoteCli(unittest.TestCase):
    def test_add_list_call_remove(self):
        import io, contextlib
        from glyph.cli import build_parser
        with tempfile.TemporaryDirectory() as td:
            os.environ["GLYPH_HOME"] = td
            try:
                p = build_parser()
                ns = p.parse_args(["remote-add", "echo",
                                   "--base-url", "null://", "--auth", "none"])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ns.func(ns), 0)
                buf = io.StringIO()
                ns = p.parse_args(["remote-list"])
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(ns.func(ns), 0)
                self.assertIn("echo", buf.getvalue())
                buf = io.StringIO()
                ns = p.parse_args(["remote-call", "echo", "--prompt", "hi"])
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(ns.func(ns), 0)
                self.assertIn('"echo"', buf.getvalue())
                ns = p.parse_args(["remote-remove", "echo"])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ns.func(ns), 0)
            finally:
                os.environ.pop("GLYPH_HOME", None)


if __name__ == "__main__":
    unittest.main()
