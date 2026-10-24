"""Finding 4: Python -> JS output must be valid JS. Verified by running it
under node and comparing with CPython's output."""
import shutil
import subprocess
import sys
import re
import textwrap
import unittest

from seraphina.rwl.ast_ir import translate
from tests._util import TempDirMixin

NODE = shutil.which("node")
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
                          text=True, timeout=30)


@unittest.skipUnless(NODE, "node not installed")
class NodeRunsEmittedJSTest(TempDirMixin, unittest.TestCase):
    def _node(self, js):
        path = self.tmp / "out.js"
        path.write_text(js, encoding="utf-8")
        return subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=30)

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
        r = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TypeScriptEmitTest(unittest.TestCase):
    def test_ts_range_has_typed_params(self):
        ts = translate("for i in range(1, 4):\n    print(i)\n", "python", "ts")
        self.assertNotRegex(_code_only(ts), _RANGE_CALL)
        self.assertIn("Array.from", ts)
        self.assertIn("(s: any, e: any, st: any)", ts)


if __name__ == "__main__":
    unittest.main()
