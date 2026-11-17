"""Decodage des pages memoire d'Assetto Corsa EVO."""
import sys
import unittest

from irms import doctor
from irms.evo_reader import GRAPHICS, MIN_SIZES, STATIC, EvoSource, decode_frame, player_position
from irms.frame import STATUS_LIVE
from irms.simulator import DemoSource, encode_pages

from .helpers import fixture_bytes


class RealCapture(unittest.TestCase):
    """Capture reelle d'EVO 0.6.2 (projet acevo-sdk, licence MIT)."""

    @classmethod
    def setUpClass(cls):
        cls.graphics = fixture_bytes("evo_0_6_2_graphics.hex")
        cls.static = fixture_bytes("evo_0_6_2_static.hex")
        cls.frame, cls.problems, cls.details = decode_frame(None, cls.graphics, cls.static, 1.0)

    def test_fixture_sizes_are_page_rounded(self):
        self.assertEqual(len(self.graphics), 4096)
        self.assertEqual(len(self.static), 2048)

    def test_no_sanity_problem(self):
        self.assertEqual(self.problems, [])

    def test_session(self):
        frame = self.frame
        self.assertEqual(frame.track, "Brands Hatch")
        self.assertEqual(frame.config, "Indy")
        self.assertAlmostEqual(frame.track_length, 1944.0, places=1)
        self.assertEqual(frame.car, "Dallara EXP")
        self.assertEqual(frame.status, STATUS_LIVE)
        self.assertRegex(frame.game_version, r"^0\.6")

    def test_driving_values(self):
        frame = self.frame
        self.assertAlmostEqual(frame.npos, 0.03607, places=4)
        self.assertEqual(round(frame.speed), 154)
        self.assertEqual(frame.gear, 4)
        self.assertAlmostEqual(frame.gas, 1.0, places=3)
        self.assertEqual(frame.brake, 0.0)
        self.assertTrue(0 < frame.rpm < 20000)
        self.assertEqual(self.details["inputs"], "graphics")

    def test_player_position_comes_from_car_coordinates(self):
        self.assertTrue(self.frame.has_pos)
        self.assertEqual(self.details["position"], "car_coordinates")
        self.assertNotEqual((self.frame.x, self.frame.z), (0.0, 0.0))

    def test_combo_is_car_track_config(self):
        self.assertEqual(self.frame.combo(), ("Dallara EXP", "Brands Hatch", "Indy"))


class RoundTrip(unittest.TestCase):
    def setUp(self):
        source = DemoSource("Démo GT3", seed=3)
        for _ in range(400):
            self.sent = source.advance(0.02)
        self.pages = encode_pages(self.sent, player_index=2)

    def test_values_survive_encode_then_decode(self):
        frame, problems, details = decode_frame(*self.pages, t=5.0)
        self.assertEqual(problems, [])
        sent = self.sent
        self.assertEqual(frame.combo(), sent.combo())
        self.assertEqual(frame.gear, sent.gear)
        self.assertEqual(frame.packet, sent.packet)
        self.assertEqual(frame.lap_time_ms, sent.lap_time_ms)
        for name, places in (("npos", 5), ("speed", 2), ("gas", 5), ("brake", 5), ("steer", 5), ("x", 2), ("z", 2),
                             ("track_length", 1)):
            self.assertAlmostEqual(getattr(frame, name), getattr(sent, name), places=places, msg=name)
        self.assertEqual(details["inputs"], "physics")
        self.assertEqual(details["position"], "car_coordinates")

    def test_reverse_and_neutral_gears(self):
        for gear in (-1, 0, 1, 6):
            self.sent.gear = gear
            frame, _, _ = decode_frame(*encode_pages(self.sent), t=0.0)
            self.assertEqual(frame.gear, gear)

    def test_player_is_found_whatever_its_slot(self):
        for index in (0, 3, 5):
            _, graphics, _ = encode_pages(self.sent, player_index=index)
            x, z, origin = player_position(graphics, None)
            self.assertEqual(origin, "car_coordinates")
            self.assertAlmostEqual(x, self.sent.x, places=2)
            self.assertAlmostEqual(z, self.sent.z, places=2)

    def test_position_falls_back_to_tyre_contact_points(self):
        physics, graphics, static = self.pages
        data = bytearray(graphics)
        field = GRAPHICS.fields["player_car_id_a"]
        data[field.offset:field.offset + field.size] = b"\xff" * field.size  # identifiant introuvable
        frame, problems, details = decode_frame(physics, bytes(data), static, 0.0)
        self.assertEqual(problems, [])
        self.assertTrue(frame.has_pos)
        self.assertNotEqual(details["position"], "car_coordinates")
        self.assertAlmostEqual(frame.x, self.sent.x, places=1)
        self.assertAlmostEqual(frame.z, self.sent.z, places=1)

    def test_dead_physics_page_is_ignored(self):
        _, graphics, static = self.pages
        frame, problems, details = decode_frame(b"\x00" * 4096, graphics, static, 0.0)
        self.assertEqual(problems, [])
        self.assertEqual(details["inputs"], "graphics")
        self.assertAlmostEqual(frame.gas, self.sent.gas, places=5)
        self.assertEqual(round(frame.speed), round(self.sent.speed))

    def test_inconsistent_physics_speed_is_rejected(self):
        self.sent.speed = 150.0
        physics, graphics, static = encode_pages(self.sent)
        bad = bytearray(physics)
        from irms.evo_reader import PHYSICS
        PHYSICS.fields["speedKmh"].write(bad, 20.0)
        frame, _, details = decode_frame(bytes(bad), graphics, static, 0.0)
        self.assertEqual(details["inputs"], "graphics")
        self.assertEqual(frame.speed, 150.0)

    def test_pit_lane_is_reported(self):
        self.sent.in_pit = True
        frame, _, _ = decode_frame(*encode_pages(self.sent), t=0.0)
        self.assertTrue(frame.in_pit)


class Sanity(unittest.TestCase):
    def setUp(self):
        source = DemoSource()
        for _ in range(250):
            self.frame = source.advance(0.02)
        self.physics, self.graphics, self.static = encode_pages(self.frame)

    def test_missing_or_short_pages(self):
        for graphics, static in ((None, self.static), (b"", self.static), (self.graphics[:MIN_SIZES["graphics"] - 1],
                                                                             self.static),
                                 (self.graphics, None), (self.graphics, self.static[:100])):
            frame, problems, _ = decode_frame(self.physics, graphics, static, 0.0)
            self.assertTrue(problems)
            self.assertEqual(frame.car, "")

    def test_inserted_field_is_detected(self):
        """Une mise a jour du jeu qui ajoute un champ decale tout ce qui suit."""
        car_model = GRAPHICS.fields["car_model"].offset
        for at in (8, 44, 100, 1000, 2500, car_model - 4):
            for pad in (1, 2, 4, 8, 16):
                shifted = (self.graphics[:at] + b"\x00" * pad + self.graphics[at:])[:len(self.graphics)]
                _, problems, _ = decode_frame(self.physics, shifted, self.static, 0.0)
                self.assertTrue(problems, "ajout de %d octets a %d non detecte" % (pad, at))

    def test_zeroed_head_never_looks_like_driving(self):
        for pad in (1, 2, 4, 8, 16):
            shifted = (b"\x00" * pad + self.graphics)[:len(self.graphics)]
            frame, problems, _ = decode_frame(self.physics, shifted, self.static, 0.0)
            self.assertTrue(problems or frame.status != 2)

    def test_out_of_range_values_are_flagged_as_suspect_when_not_live(self):
        data = bytearray(self.graphics)
        GRAPHICS.fields["status"].write(data, 0)
        GRAPHICS.fields["npos"].write(data, 37.0)
        _, problems, details = decode_frame(self.physics, bytes(data), self.static, 0.0)
        self.assertEqual(problems, [])
        self.assertTrue(details["suspect"])

    def test_shifted_static_page_is_detected(self):
        for pad in (1, 4, 16):
            shifted = (b"\x00" * pad + self.static)[:len(self.static)]
            _, problems, _ = decode_frame(self.physics, self.graphics, shifted, 0.0)
            self.assertTrue(problems, "decalage de %d octets non detecte" % pad)

    def test_pause_keeps_names_checked(self):
        self.frame.status = 3
        physics, graphics, static = encode_pages(self.frame)
        frame, problems, _ = decode_frame(physics, graphics, static, 0.0)
        self.assertEqual(problems, [])
        self.assertEqual(frame.status, 3)

    def test_random_bytes_are_detected(self):
        import random
        rng = random.Random(7)
        for _ in range(20):
            noise = bytes(rng.getrandbits(8) for _ in range(8192))
            _, problems, _ = decode_frame(None, noise, self.static, 0.0)
            self.assertTrue(problems)

    def test_empty_names_are_detected_when_live(self):
        blank = bytearray(self.graphics)
        field = GRAPHICS.fields["car_model"]
        blank[field.offset:field.offset + field.size] = b"\x00" * field.size
        _, problems, _ = decode_frame(self.physics, bytes(blank), self.static, 0.0)
        self.assertTrue(any("voiture" in p for p in problems))

    def test_menu_page_full_of_zeros_is_not_a_problem(self):
        """Dans les menus le jeu publie une page vide : statut arrete, sans alerte."""
        frame, problems, _ = decode_frame(None, b"\x00" * 8192, b"\x00" * 4096, 0.0)
        frame, problems, details = decode_frame(None, b"\x00" * 8192, b"\x00" * 4096, 0.0)
        self.assertEqual(problems, [])
        self.assertEqual(details["suspect"], [])
        self.assertEqual(frame.status, 0)


class Strings(unittest.TestCase):
    def test_windows_1252_names_are_readable(self):
        frame = DemoSource().advance(1.0)
        _, _, static = encode_pages(frame)
        data = bytearray(static)
        field = STATIC.fields["track"]
        raw = "Nürburgring".encode("cp1252")
        data[field.offset:field.offset + field.size] = raw + b"\x00" * (field.size - len(raw))
        self.assertEqual(STATIC.get(bytes(data), "track"), "Nürburgring")

    def test_utf8_names_are_readable(self):
        frame = DemoSource().advance(1.0)
        frame.track = "Nürburgring"
        _, _, static = encode_pages(frame)
        self.assertEqual(STATIC.get(static, "track"), "Nürburgring")


class Privacy(unittest.TestCase):
    def test_scrub_erases_driver_name_only(self):
        frame = DemoSource().advance(1.0)
        _, graphics, static = encode_pages(frame)
        data = bytearray(graphics)
        for name, value in (("driver_name", b"Jean"), ("driver_surname", b"Dupont")):
            field = GRAPHICS.fields[name]
            data[field.offset:field.offset + len(value)] = value
        clean = doctor.scrub(bytes(data))
        self.assertEqual(len(clean), len(graphics))
        self.assertNotIn(b"Jean", clean)
        self.assertNotIn(b"Dupont", clean)
        decoded, problems, _ = decode_frame(None, clean, static, 0.0)
        self.assertEqual(problems, [])
        self.assertEqual(decoded.car, frame.car)

    def test_frame_has_no_driver_field(self):
        names = set(frame_name.lower() for frame_name in DemoSource().advance(0.1).as_dict())
        self.assertFalse([n for n in names if "driver" in n or "pilote" in n or "name" in n])

    def test_report_contains_no_personal_data(self):
        info = doctor.report(source=EvoSource())
        text = repr(info).lower()
        self.assertNotIn("driver", text)
        self.assertEqual(info["structures"], {"physics": 800, "graphics": 4900, "static": 208})


class AccessRights(unittest.TestCase):
    """Jeu lance en administrateur : le refus de Windows doit etre explique."""

    def _source(self, error):
        from irms import evo_reader

        def refuse(name):
            raise OSError(error, "refus simule: %s" % name)

        original = evo_reader.MappedView
        evo_reader.MappedView = refuse
        self.addCleanup(setattr, evo_reader, "MappedView", original)
        source = EvoSource()
        source.state["platform_ok"] = True
        return source

    def test_access_denied_is_explained(self):
        source = self._source(5)
        self.assertIsNone(source.poll())
        self.assertFalse(source.state["connected"])
        self.assertIn("administrateur", source.state["message"])

    def test_missing_game_is_not_confused_with_a_refusal(self):
        source = self._source(2)
        self.assertIsNone(source.poll())
        self.assertIn("non détecté", source.state["message"])
        self.assertNotIn("administrateur", source.state["message"])


class NonWindows(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "comportement hors Windows")
    def test_source_explains_itself_and_never_crashes(self):
        source = EvoSource()
        self.assertIsNone(source.poll())
        self.assertFalse(source.state["platform_ok"])
        self.assertIn("Windows", source.state["message"])
        source.close()


if __name__ == "__main__":
    unittest.main()
