"""RWL codec, wheel view and RWAST round-trips (no mocks)."""
import subprocess
import sys
import unittest
import zlib

from seraphina.rwl import RWLError, decode, encode, info
from seraphina.rwl.ast_ir import (
    decode_ast, emit, encode_ast, parse, score, translate,
)
from seraphina.rwl.wheel import (
    byte_to_symbol, render_wheel_stream, stream_to_bytes, symbol_to_byte,
)

SAMPLE_PY = """\
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

class Box:
    def __init__(self, v):
        self.v = v

print(fib(10), Box(3).v)
"""


class CodecTest(unittest.TestCase):
    def test_round_trip_languages_and_compression(self):
        cases = {
            "python": SAMPLE_PY.encode(),
            "javascript": b"console.log('hi');\n",
            "text": "unicode \u2603 \u00e9\n".encode(),
            "json": b'{"a": [1, 2, 3]}',
            "gl": bytes(range(256)) * 3,
        }
        for lang, src in cases.items():
            for compress in (True, False):
                with self.subTest(lang=lang, compress=compress):
                    blob = encode(src, language=lang, compress=compress)
                    self.assertEqual(blob, encode(src, language=lang, compress=compress))
                    c, out = decode(blob)
                    self.assertEqual(out, src)
                    self.assertEqual(c.language, lang)
                    self.assertEqual(c.compressed, compress)
                    self.assertEqual(info(blob).sha256_hex, c.sha256_hex)

    def test_empty_source(self):
        c, out = decode(encode(b"", language="text"))
        self.assertEqual(out, b"")
        self.assertEqual(c.original_size, 0)

    def test_tamper_detected(self):
        blob = bytearray(encode(b"hello world" * 20, language="text", compress=False))
        blob[-1] ^= 0x01
        with self.assertRaisesRegex(RWLError, "SHA256 mismatch"):
            decode(bytes(blob))

    def test_compressed_tamper_and_truncation(self):
        blob = encode(b"abc" * 100, language="text", compress=True)
        with self.assertRaises(RWLError):
            decode(blob[:-3])
        header, payload = blob[:64], blob[64:]
        other = zlib.compress(b"abd" * 100, 9)
        if len(other) == len(payload):
            with self.assertRaises(RWLError):
                decode(header + other)

    def test_bad_inputs(self):
        with self.assertRaises(RWLError):
            decode(b"short")
        with self.assertRaises(RWLError):
            decode(b"XXXX" + encode(b"x")[4:])
        with self.assertRaises(RWLError):
            encode(b"x", language="cobol")


class WheelTest(unittest.TestCase):
    def test_bijective_over_all_bytes(self):
        syms = [byte_to_symbol(b) for b in range(256)]
        self.assertEqual(len({s.as_tuple() for s in syms}), 256)
        for b, s in enumerate(syms):
            self.assertEqual(symbol_to_byte(s), b)

    def test_stream_round_trip(self):
        data = bytes(range(256))
        text = render_wheel_stream(data, width=16)
        self.assertEqual(len(text.splitlines()), 16)
        self.assertEqual(stream_to_bytes(text.split()), data)
        with self.assertRaises(ValueError):
            byte_to_symbol(256)
        with self.assertRaises(ValueError):
            stream_to_bytes(["99999"])


class RwastTest(unittest.TestCase):
    def test_ast_binary_round_trip(self):
        root = parse(SAMPLE_PY, "python")
        blob = encode_ast(root)
        self.assertEqual(blob, encode_ast(root))
        back = decode_ast(blob)
        self.assertEqual(emit(back, "python"), emit(root, "python"))
        s = score(root, back)
        self.assertEqual((s.geometric, s.verification, s.mercy_civ), (1.0, 1.0, 1.0))
        self.assertEqual(s.consensus, 1.0)

    def test_python_round_trip_is_stable_and_equivalent(self):
        once = translate(SAMPLE_PY, "python", "python")
        twice = translate(once, "python", "python")
        self.assertEqual(once, twice)
        def run(src):
            return subprocess.run([sys.executable, "-c", src], capture_output=True,
                                  text=True, timeout=30, check=False)
        a, b = run(SAMPLE_PY), run(once)
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual((b.returncode, b.stdout), (0, a.stdout), b.stderr)

    def test_score_detects_structural_difference(self):
        a = parse(SAMPLE_PY, "python")
        b = parse("x = 1\n", "python")
        s = score(a, b)
        self.assertLess(s.geometric, 1.0)
        self.assertLess(s.consensus, 1.0)
        self.assertGreater(s.consensus, 0.0)

    def test_unsupported_frontend_is_an_error(self):
        with self.assertRaises(ValueError):
            parse("console.log(1)", "js")


if __name__ == "__main__":
    unittest.main()
