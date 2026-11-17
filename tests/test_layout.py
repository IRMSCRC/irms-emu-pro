"""La disposition memoire calculee doit etre identique a celle du compilateur."""
import json
import os
import unittest

from irms.evo_reader import GRAPHICS, MIN_SIZES, PHYSICS, STATIC
from irms.evo_structs import STRUCTS
from irms.layout import Layout

from .helpers import FIXTURES


class GoldenOffsets(unittest.TestCase):
    """``golden_offsets.json`` vient de ``offsetof``/``sizeof`` sur l'en-tete C++ du jeu."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIXTURES, "golden_offsets.json"), "r", encoding="utf-8") as handle:
            cls.golden = json.load(handle)

    def test_every_struct_matches_the_compiler(self):
        self.assertGreaterEqual(len(self.golden), 10)
        checked = 0
        for name, expected in self.golden.items():
            layout = Layout(STRUCTS, name)
            self.assertEqual(layout.size, expected["size"], "taille de %s" % name)
            members = layout.members()
            self.assertEqual(sorted(members), sorted(expected["fields"]), "champs de %s" % name)
            for field, (offset, size) in expected["fields"].items():
                self.assertEqual(tuple(members[field]), (offset, size), "%s.%s" % (name, field))
                checked += 1
        self.assertGreater(checked, 300)

    def test_page_sizes(self):
        self.assertEqual(PHYSICS.size, 800)
        self.assertEqual(GRAPHICS.size, 4900)
        self.assertEqual(STATIC.size, 208)
        self.assertLessEqual(MIN_SIZES["graphics"], 4096, "une zone arrondie a une page doit suffire")

    def test_no_field_overlaps_or_overflows(self):
        for layout in (PHYSICS, GRAPHICS, STATIC):
            for field in layout.fields.values():
                self.assertGreaterEqual(field.offset, 0)
                self.assertLessEqual(field.offset + field.size, layout.size, field.path)


class EncodeDecode(unittest.TestCase):
    def test_scalar_string_bool_and_array_round_trip(self):
        values = {"packetId": 77, "status": 2, "npos": 0.25, "car_model": "Voiture Été",
                  "is_valid_lap": True, "gas_percent": 0.5, "car_coordinates": [[1.0, 2.0, 3.0]] * 60}
        page = GRAPHICS.encode(values, 8192)
        self.assertEqual(len(page), 8192)
        self.assertEqual(GRAPHICS.get(page, "packetId"), 77)
        self.assertEqual(GRAPHICS.get(page, "car_model"), "Voiture Été")
        self.assertIs(GRAPHICS.get(page, "is_valid_lap"), True)
        self.assertAlmostEqual(GRAPHICS.get(page, "npos"), 0.25, places=6)
        self.assertEqual(GRAPHICS.get(page, "car_coordinates")[59], [1.0, 2.0, 3.0])

    def test_field_beyond_buffer_returns_default(self):
        page = GRAPHICS.encode({"packetId": 5}, 8192)[:100]
        self.assertEqual(GRAPHICS.get(page, "npos", "absent"), "absent")

    def test_truncated_2d_array_is_read_partially(self):
        field = GRAPHICS.fields["car_ids"]
        page = GRAPHICS.encode({"car_ids": [[i, i + 1] for i in range(60)]}, 8192)
        cut = page[:field.offset + 16 * 5 + 3]
        rows = GRAPHICS.get(cut, "car_ids")
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[4], [4, 5])


if __name__ == "__main__":
    unittest.main()
