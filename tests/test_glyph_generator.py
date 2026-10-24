import hashlib
import unittest

from seraphina.glyph_generator import (
    GEOMETRY_RANGES, ID_HEX_LEN, OctaLangGlyphGenerator, geometry, geometry_seed,
    glyph_id, ids_from_codescript, intrinsic_value, legacy_gematria_id,
    matches_id, parse_glyph_id,
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
        g = geometry(d)
        iv = intrinsic_value(88, **g)
        self.assertEqual(iv, 88 + 8 * g["spirals"] + 33 * g["triangles"] + g["dots"]
                         + g["facets"] + g["intersections"])
        self.assertIn(f"INTRINSIC_VALUE: {iv}", out)
        self.assertIn(f"= {iv}", out)
        self.assertIn(f"Golden spiral ({g['spirals']} turns)", out)
        self.assertIn(f"expanding in {g['spirals']} precise turns", out)
        self.assertIn(f"Facets: {g['facets']} crystalline facets", out)
        self.assertIn(f"exactly {g['intersections']} line crossings", out)
        self.assertIn(geometry_seed(d).hex(), out)
        self.assertNotIn("29 rules", out)


class GeometryFromSeedTest(unittest.TestCase):
    def test_same_seed_reproduces(self):
        for d in ("Seraphina AGI core", "mercy", "x" * 500, ""):
            with self.subTest(d=d[:20]):
                self.assertEqual(geometry(d), geometry(d))
                self.assertEqual(geometry(d), geometry("  " + d.upper() + " "))
                self.assertEqual(OctaLangGlyphGenerator().generate(d),
                                 OctaLangGlyphGenerator().generate(d))

    def test_different_seeds_give_different_geometry(self):
        descs = [f"glyph description {i}" for i in range(300)]
        geoms = {tuple(sorted(geometry(d).items())) for d in descs}
        # 1.1M possible geometries; 300 fixed descriptions all land apart.
        self.assertEqual(len(geoms), len(descs))
        a, b = "Seraphina AGI core", "Seraphina AGI cord"
        self.assertNotEqual(geometry(a), geometry(b))
        gen = OctaLangGlyphGenerator()
        self.assertNotEqual(gen.generate(a).split("RENDERING")[1],
                            gen.generate(b).split("RENDERING")[1])

    def test_not_one_fixed_template(self):
        # The old generator gave every description intrinsic 178.
        values = {intrinsic_value(88, **geometry(f"d{i}")) for i in range(200)}
        self.assertGreater(len(values), 50)

    def test_counts_stay_in_range_and_come_from_the_digest(self):
        for i in range(500):
            g = geometry(f"range check {i}")
            for name, (lo, hi) in GEOMETRY_RANGES.items():
                self.assertTrue(lo <= g[name] <= hi, (name, g[name]))
        d = "derivation"
        digest = geometry_seed(d)
        self.assertEqual(digest, hashlib.sha256(b"derivation").digest())
        lo, hi = GEOMETRY_RANGES["spirals"]
        self.assertEqual(geometry(d)["spirals"],
                         lo + int.from_bytes(digest[0:4], "big") % (hi - lo + 1))

    def test_reads_legacy_codescript(self):
        old = '// Gematria ID: 412\n\nPROGRAM "Generated_Glyph_412"\n'
        self.assertEqual(ids_from_codescript(old), 412)
        self.assertTrue(matches_id("test", ids_from_codescript(old)))
        with self.assertRaises(ValueError):
            ids_from_codescript("no program line")


if __name__ == "__main__":
    unittest.main()
