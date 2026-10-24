"""Finding 4: Python -> JS output must be valid JS. Verified by running it
under node and comparing with CPython's output."""
import subprocess
import sys
import re
import textwrap
import unittest

from seraphina.rwl.ast_ir import translate
from tests._util import TempDirMixin, require_tool

_RANGE_CALL = re.compile(r"(?<![\w.])range\(")


def _code_only(js):
    """Drop string literals so the RangeError message is not a false hit."""
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', js)

PROGRAMS = {
    "range_forms": """
        total = 0
        for i in range(5):
            total += i
        print(total)
        print(len(range(2, 10, 3)))
        print(sum(range(2, 10, 3)))
        print(sum(range(10, 0, -2)))
        print(len(range(5, 1)))
        print(len(range(0)))
        print(len(range(-3)))
        for i in range(3, -3, -2):
            print(i)
    """,
    "comprehension_over_range": """
        sq = [x * x for x in range(4)]
        print(len(sq))
        print(sum(sq))
        evens = [x for x in range(10) if x % 2 == 0]
        print(sum(evens))
    """,
    "sorted_sum_max_min": """
        xs = [10, 9, 100, 1]
        ys = sorted(xs)
        print(ys[0], ys[1], ys[2], ys[3])
        print(xs[0])
        zs = sorted(xs, reverse=True)
        print(zs[0])
        print(sum(xs), max(xs), min(xs), max(3, 4))
        print(sum([1, 2], 10))
    """,
    "str_case_and_strip": r"""
        s = "  Hello, World  "
        print(s.upper(), s.lower())
        print("|" + s.strip() + "|", "|" + s.lstrip() + "|", "|" + s.rstrip() + "|")
        print("xxabcxx".strip("x"), "xyabc".lstrip("yx"), "abcyx".rstrip("xy"), "abc".strip(""))
        print(" \u3000x\u3000\x1c ".strip(), "|" + "\t\n".strip() + "|")
        print("hELLO wORLD".capitalize(), "hello world".title(), "they're bill's 1st".title())
        print("\u00dftra\u00dfe".capitalize(), "\u01c6emal".title(), "".capitalize(), "".title())
    """,
    "str_split_join_replace": r"""
        print(len("  a b  c ".split()), "-".join("  a b  c ".split()))
        print("-".join("  a b  c ".split(None, 1)), "-".join("  a b ".split(None, 0)))
        print(len("".split()), len("".split(",")), len("   ".split()))
        print("|".join("a,b,,c".split(",")), "|".join("a,b,,c".split(",", 1)))
        print("|".join("a,b,c".split(sep=",", maxsplit=1)), "|".join("a b c".split(maxsplit=1)))
        print("aaa".replace("a", "b"), "aaa".replace("a", "b", 2), "aaa".replace("a", "b", 0))
        print("ab".replace("", "-"), "abc".replace("", "-", 2), "".replace("", "x"))
        print(", ".join([]), ", ".join(["x"]), "".join(["a", "b"]))
        words = "the quick brown fox".split()
        print(" ".join(w.capitalize() for w in words))
    """,
    "str_search": r"""
        print("hello".startswith("he"), "hello".startswith(("x", "hel")))
        print("hello".endswith("lo"), "hello".endswith(("a", "b")))
        print("hello".startswith("l", 2), "hello".startswith("", 9), "hello".endswith("ll", 0, 4))
        print("hello".find("l"), "hello".find("z"), "hello".find("l", 3), "hello".find("", 9))
        print("hello".find("l", -2), "hello".find("", 5), "hello".find("l", 0, 2))
        print("hello".index("o"), "banana".count("a"), "aaa".count("aa"), "abc".count(""))
        print("banana".count("a", 2), "banana".count("an", 0, 4), [1, 2, 1].count(1), [5, 6].index(6))
        print("\U0001F600ab".find("b"), "\U0001F600ab".count(""), len("\U0001F600ab"), len("h\u00e9llo"))
        try:
            "abc".index("z")
        except ValueError:
            print("ValueError caught")
    """,
    "str_predicates": r"""
        print("123".isdigit(), "12a".isdigit(), "".isdigit(), "\u00b2".isdigit(), "\u0663".isdigit())
        print("123".isdecimal(), "\u00b2".isdecimal())
        print("abc".isalpha(), "ab1".isalpha(), "".isalpha(), "\u00e9".isalpha())
        print(" \t".isspace(), "".isspace(), " a".isspace())
    """,
    "str_format_and_str": r"""
        print("{} + {} = {}".format(1, 2, 3), "{1}{0}".format("a", "b"), "{name}!".format(name="Bo"))
        print("{{x}} {}".format(True), "{}".format(None), "{}".format(0.5), "{}".format(1e-05))
        print(str(True), str(None), str(2.5), str(10), repr("it's"), repr('a"b'), repr("x\ny"))
        print([1, "a", None, True], {"k": [1.5]}, str([]))
        name = "Ada"
        print(f"hi {name}, {True} {None} {[1, 2]}", "a", "b", sep="-")
        print(f"tick`back\\slash ${name}")
        xs = ["p", 1, False]
        print(*xs)
        print(*xs, sep=", ")
        print("no newline", end="")
        print("", end="\n")
        print()
    """,
    "enumerate_and_functions": """
        def add(a, b):
            return a + b
        for i, v in enumerate([7, 8]):
            print(i, add(i, v))
        for i, v in enumerate([7, 8], 1):
            print(i, v)
        n = 0
        while n < 3:
            n += 1
        print(n)
    """,
}


def _run_py(src):
    return subprocess.run([sys.executable, "-c", src], capture_output=True,
                          text=True, timeout=30, check=False)  # callers assert returncode


class NodeRunsEmittedJSTest(TempDirMixin, unittest.TestCase):
    """Runs the emitted JS under node. Without node these tests are skipped
    with the reason (a visible skip, never a pass); with
    SERAPHINA_REQUIRE_ALL_TESTS=1 a missing node fails the suite."""

    def setUp(self):
        super().setUp()
        self.node = require_tool(self, "node")

    def _node(self, js):
        path = self.tmp / "out.js"
        path.write_text(js, encoding="utf-8")
        return subprocess.run([self.node, str(path)], capture_output=True, text=True,
                              timeout=30, check=False)  # callers assert returncode

    def test_programs_match_cpython(self):
        for name, body in PROGRAMS.items():
            with self.subTest(program=name):
                src = textwrap.dedent(body).strip() + "\n"
                js = translate(src, "python", "js")
                self.assertNotRegex(_code_only(js), _RANGE_CALL)
                py = _run_py(src)
                self.assertEqual(py.returncode, 0, py.stderr)
                nd = self._node(js)
                self.assertEqual(nd.returncode, 0, f"{nd.stderr}\n--- js ---\n{js}")
                self.assertEqual(nd.stdout, py.stdout, js)

    def test_range_zero_step_raises(self):
        js = translate("x = range(0, 5, 0)\n", "python", "js")
        nd = self._node(js)
        self.assertNotEqual(nd.returncode, 0)
        self.assertIn("RangeError", nd.stderr)

    def test_node_syntax_check_on_ts_free_js(self):
        js = translate("for i in range(2):\n    print(i)\n", "python", "js")
        path = self.tmp / "c.js"
        path.write_text(js, encoding="utf-8")
        r = subprocess.run([self.node, "--check", str(path)], capture_output=True, text=True,
                           timeout=30, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)


    def test_str_errors_raise_like_python(self):
        cases = {
            "'a'.split('')": "ValueError: empty separator",
            "'abc'.index('z')": "ValueError: substring not found",
            "'-'.join(['a', 1])": "TypeError: sequence item 1: expected str instance, int found",
            "'{} {}'.format(1)": "IndexError: Replacement index 1 out of range",
            "'{x}'.format()": "KeyError: 'x'",
            "len(5)": "TypeError: object of type 'int' has no len()",
        }
        for expr, err in cases.items():
            with self.subTest(expr):
                py = _run_py(f"print({expr})")
                self.assertNotEqual(py.returncode, 0)
                nd = self._node(translate(f"print({expr})\n", "python", "js"))
                self.assertNotEqual(nd.returncode, 0, nd.stdout)
                self.assertIn(err, nd.stderr)
                self.assertIn(err.split(":")[0], py.stderr)

    def test_unsupported_format_spec_fails_loudly(self):
        # Python accepts "{:>4}"; the JS translation does not implement format
        # specs, so it must stop with an error rather than print something else.
        nd = self._node(translate("print('{:>4}'.format(1))\n", "python", "js"))
        self.assertNotEqual(nd.returncode, 0, nd.stdout)
        self.assertIn("NotImplementedError", nd.stderr)
        self.assertEqual(nd.stdout, "")

    def test_non_str_receivers_forward_to_their_own_method(self):
        # A receiver that is not a JS string keeps its own method. (Python
        # classes do not translate to runnable JS classes yet, so the receiver
        # is a plain JS object defined ahead of the translated code.)
        js = translate("print(b.upper(), b.split(','), b.count(1))\n", "python", "js")
        js = ('const b = {upper: () => "box-upper", split: (s) => "split on " + s, '
              'count: (x) => x + 41};\n' + js)
        nd = self._node(js)
        self.assertEqual(nd.returncode, 0, nd.stderr + js)
        self.assertEqual(nd.stdout, "box-upper split on , 42\n")

    def test_helpers_emitted_once_and_only_when_used(self):
        js = translate("print(1)\n", "python", "js")
        self.assertNotIn("__py_split", js)
        js = translate("a = 'x y'.split()\nb = 'z'.split()\n", "python", "js")
        self.assertEqual(js.count("function __py_split("), 1)
        self.assertEqual(self._node(js).returncode, 0)


class StrMethodTranslateErrorsTest(unittest.TestCase):
    def test_unknown_keyword_refused_at_translate_time(self):
        with self.assertRaises(ValueError):
            translate("'a b'.split(bogus=1)\n", "python", "js")
        with self.assertRaises(ValueError):
            translate("print('x', file=f)\n", "python", "js")


class TypeScriptEmitTest(unittest.TestCase):
    def test_ts_range_has_typed_params(self):
        ts = translate("for i in range(1, 4):\n    print(i)\n", "python", "ts")
        self.assertNotRegex(_code_only(ts), _RANGE_CALL)
        self.assertIn("Array.from", ts)
        self.assertIn("(s: any, e: any, st: any)", ts)

    def test_ts_str_helpers_are_typed(self):
        ts = translate("x = ' a '.split()\nprint(x)\n", "python", "ts")
        self.assertIn("function __py_split(s: any, ...a: any)", ts)
        self.assertIn("function __py_repr(v: any): string", ts)


if __name__ == "__main__":
    unittest.main()
