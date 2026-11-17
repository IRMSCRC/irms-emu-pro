"""Lecture de vraies zones memoire partagees Windows (ignore ailleurs).

Le test cree les trois zones nommees comme le fait Assetto Corsa EVO, y
ecrit des pages fabriquees par le simulateur, puis verifie que ``EvoSource``
les ouvre, les decode, detecte l'arret du jeu et s'y reconnecte.
"""
import sys
import unittest

from irms.engine import Engine
from irms.simulator import DemoSource, encode_pages
from irms.storage import Storage

from .helpers import temp_db


class FakeClock(object):
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@unittest.skipUnless(sys.platform == "win32", "memoire partagee Windows uniquement")
class SharedMemory(unittest.TestCase):
    def setUp(self):
        from irms.evo_fake import FakeMaps
        from irms.evo_reader import EvoSource
        self.FakeMaps = FakeMaps
        self.clock = FakeClock()
        self.source = EvoSource(clock=self.clock)
        self.demo = DemoSource("Démo GT3", seed=4)

    def tearDown(self):
        self.source.close()

    def publish(self, maps, dt=0.02, mutate=None):
        frame = self.demo.advance(dt)
        if mutate:
            mutate(frame)
        for key, page in zip(("physics", "graphics", "static"), encode_pages(frame)):
            maps.write(key, page)
        self.clock.now += dt
        return frame

    def test_game_not_running(self):
        self.assertIsNone(self.source.poll())
        self.assertFalse(self.source.state["connected"])
        self.assertIn("non détecté", self.source.state["message"])

    def test_reads_what_the_game_publishes(self):
        with self.FakeMaps() as maps:
            sent = self.publish(maps)
            frame = self.source.poll()
            self.assertIsNotNone(frame)
            self.assertTrue(self.source.state["connected"])
            self.assertEqual(self.source.state["problems"], [])
            self.assertEqual(frame.combo(), sent.combo())
            self.assertEqual(frame.gear, sent.gear)
            self.assertAlmostEqual(frame.npos, sent.npos, places=5)
            self.assertAlmostEqual(frame.speed, sent.speed, places=2)
            self.assertTrue(frame.has_pos)
            sizes = dict((k, v["size"]) for k, v in self.source.state["maps"].items())
            self.assertGreaterEqual(sizes["graphics"], 4900)
            self.assertTrue(self.source.state["maps"]["graphics"]["name"].startswith("Local\\acevo_pmf_"))
            for _ in range(20):
                sent = self.publish(maps)
                frame = self.source.poll()
                self.assertEqual(frame.packet, sent.packet)

    def test_legacy_zone_names_are_found_too(self):
        with self.FakeMaps(legacy_names=True) as maps:
            self.publish(maps)
            self.assertIsNotNone(self.source.poll())
            self.assertTrue(self.source.state["maps"]["graphics"]["name"].startswith("Local\\acpmf_"))

    def test_closed_game_is_detected_then_reconnected(self):
        maps = self.FakeMaps()
        self.publish(maps)
        self.assertIsNotNone(self.source.poll())
        self.clock.now += 5.0  # plus aucune nouvelle image
        self.assertIsNone(self.source.poll())
        self.assertFalse(self.source.state["connected"])
        maps.close()
        self.clock.now += 3.0
        self.assertIsNone(self.source.poll(), "le jeu est ferme : la zone n'existe plus")
        with self.FakeMaps() as again:
            self.clock.now += 3.0
            self.publish(again)
            self.assertIsNotNone(self.source.poll())
            self.assertTrue(self.source.state["connected"])

    def test_unknown_layout_suspends_recording(self):
        with self.FakeMaps() as maps:
            self.publish(maps)
            maps.write("graphics", b"\x02\x00\x00\x00" * 2048)
            self.clock.now += 0.02
            frame = self.source.poll()
            self.assertIsNotNone(frame)
            self.assertEqual(frame.status, -1)
            self.assertTrue(self.source.state["problems"])

    def test_full_chain_records_a_lap(self):
        storage = Storage(temp_db())
        engine = Engine(storage, self.source)
        with self.FakeMaps() as maps:
            for _ in range(20000):
                self.publish(maps)
                engine.step()
                if storage.combos() and storage.combos()[0]["laps"] >= 1:
                    break
        engine.recorder.flush()
        combos = storage.combos()
        self.assertEqual(len(combos), 1)
        self.assertEqual(combos[0]["car"], "Démo GT3")
        lap = storage.laps(combos[0]["id"])[0]
        self.assertEqual(lap["time_source"], "jeu")
        self.assertEqual(lap["source"], "evo")
        self.assertTrue(lap["has_pos"])
        storage.close()


if __name__ == "__main__":
    unittest.main()
