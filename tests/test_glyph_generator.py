import hashlib
import re
import unittest

from seraphina.glyph_generator import (
    ID_HEX_LEN, OctaLangGlyphGenerator, glyph_id, ids_from_codescript,
    legacy_gematria_id, matches_id, parse_glyph_id,
)
from seraphina.rule_base import OctaRuleBase


class GlyphIdTest(unittest.TestCase):
    def test_sha256_prefix(self):
        d = "Seraphina AGI core"
        self.assertEqual(glyph_id(d), hashlib.sha256(d.lower().encode()).hexdigest()[:16])
        self.assertEqual(len(glyph_id(d)), ID_HEX_LEN)
        self.assertRegex(glyph_id(d), r"^[0-9a-f]{16}$")

    def test_deterministic_and_normalised(self):
        self.assertEqual(glyph_id("Mercy Growth"), glyph_id("  mercy growth "))
        self.assertEqual(glyph_id("x"), OctaLangGlyphGenerator().glyph_id("x"))

    def test_no_collisions_where_legacy_ids_collide(self):
        descs = [f"glyph description {i}" for i in range(20000)]
        new_ids = {glyph_id(d) for d in descs}
        self.assertEqual(len(new_ids), len(descs))
        legacy = {legacy_gematria_id(d) for d in descs}
        self.assertLessEqual(len(legacy), 999)  # pigeonhole: the old bug

    def test_legacy_ids_still_readable(self):
        self.assertEqual(legacy_gematria_id("Seraphina"), 1013)
        self.assertEqual(legacy_gematria_id("test"), 412)
        h = legacy_gematria_id("anything else")
        self.assertTrue(1 <= h <= 999)
        self.assertEqual(parse_glyph_id("412"), 412)
        self.assertEqual(parse_glyph_id(412), 412)
        self.assertTrue(matches_id("test", 412))
        self.assertFalse(matches_id("other", 412))

    def test_parse_new_ids(self):
        gid = glyph_id("abc")
        self.assertEqual(parse_glyph_id(gid.upper()), gid)
        self.assertTrue(matches_id("abc", gid))
        self.assertFalse(matches_id("abd", gid))
        for bad in ["", "xyz", "0", "12345", "abc123", "f" * 15, "f" * 17]:
            with self.assertRaises(ValueError):
                parse_glyph_id(bad)

    def test_all_digit_hex_id_is_new_style(self):
        self.assertEqual(parse_glyph_id("1234567890123456"), "1234567890123456")


class GenerateTest(unittest.TestCase):
    def test_codescript_contains_id_and_real_values(self):
        d = "Seraphina AGI core with Mercy growth"
        out = OctaLangGlyphGenerator().generate(d)
        self.assertEqual(out, OctaLangGlyphGenerator().generate(d))
        self.assertIn(f'PROGRAM "Generated_Glyph_{glyph_id(d)}"', out)
        self.assertEqual(ids_from_codescript(out), glyph_id(d))
        self.assertIn(f"INPUT_0: {OctaRuleBase.gematria(d)} (gematria seed)", out)
        self.assertIn("INTRINSIC_VALUE: 178", out)
        self.assertIn("= 178", out)
        self.assertNotIn("29 rules", out)

    def test_reads_legacy_codescript(self):
        old = '// Gematria ID: 412\n\nPROGRAM "Generated_Glyph_412"\n'
        self.assertEqual(ids_from_codescript(old), 412)
        self.assertTrue(matches_id("test", ids_from_codescript(old)))
        with self.assertRaises(ValueError):
            ids_from_codescript("no program line")


if __name__ == "__main__":
    unittest.main()
