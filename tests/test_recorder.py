"""Decoupage du flux en tours : temps, validite, cas limites."""
import unittest

from irms.frame import STATUS_PAUSE, STATUS_REPLAY
from irms.recorder import CHANNELS, Recorder
from irms.simulator import DemoSource


class Harness(object):
    """Fait tourner le simulateur dans un Recorder en gardant la main sur chaque image."""

    def __init__(self, car="Démo GT3", seed=1):
        self.source = DemoSource(car, seed=seed)
        self.laps = []
        self.combos = []
        self.recorder = Recorder(self.laps.append, lambda combo, length: self.combos.append(combo))
        self.shift = 0.0
        self.last = None

    def step(self, dt=0.02, mutate=None, feed=True):
        frame = self.source.advance(dt)
        frame.t += self.shift
        if mutate:
            mutate(frame)
        self.last = frame
        if feed:
            self.recorder.feed(frame)
        return frame

    def run_until_laps(self, count, mutate=None, limit=400000):
        steps = 0
        while len(self.laps) < count and steps < limit:
            self.step(mutate=mutate)
            steps += 1
        if len(self.laps) < count:
            raise AssertionError("seulement %d tour(s) en %d images" % (len(self.laps), steps))

    def run_until_npos(self, low, high):
        for _ in range(400000):
            frame = self.step()
            if low <= frame.npos <= high and self.recorder.lap_in_progress:
                return frame
        raise AssertionError("position jamais atteinte")


class Laps(unittest.TestCase):
    def test_partial_first_lap_is_never_recorded(self):
        h = Harness()
        self.assertFalse(h.recorder.lap_in_progress)
        frame = h.step()
        self.assertGreater(frame.npos, 0.5, "la demo demarre en milieu de tour")
        while h.step().npos > 0.5:
            pass
        self.assertEqual(h.laps, [], "le tour entame au demarrage ne compte pas")
        self.assertTrue(h.recorder.lap_in_progress)

    def test_lap_time_matches_the_game_to_the_millisecond(self):
        h = Harness()
        h.run_until_laps(3)
        for lap in h.laps:
            self.assertEqual(lap.time_source, "jeu")
            self.assertLessEqual(abs(lap.own_ms - lap.time_ms), 2, "mesure propre proche du temps officiel")
            self.assertGreater(lap.time_ms, 60000)
        self.assertEqual(h.laps[-1].time_ms, h.last.last_lap_ms)

    def test_samples_cover_the_whole_lap(self):
        h = Harness()
        h.run_until_laps(1)
        lap = h.laps[0]
        self.assertEqual(sorted(lap.samples), sorted(CHANNELS))
        lengths = set(len(lap.samples[name]) for name in CHANNELS)
        self.assertEqual(len(lengths), 1)
        d = lap.samples["d"]
        self.assertLess(d[0], 5.0)
        self.assertGreater(d[-1], lap.track_length - 5.0)
        self.assertTrue(all(b > a for a, b in zip(d, d[1:])), "distance strictement croissante")
        self.assertTrue(lap.has_pos)
        self.assertTrue(lap.valid)
        self.assertEqual((lap.car, lap.config), ("Démo GT3", "Grand Prix"))

    def test_own_time_is_used_when_the_game_publishes_none(self):
        h = Harness()

        def mute(frame):
            frame.last_lap_ms = 0

        h.run_until_laps(1, mutate=mute)
        lap = h.laps[0]
        self.assertEqual(lap.time_source, "mesure")
        self.assertEqual(lap.time_ms, lap.own_ms)
        self.assertGreater(lap.own_ms, 60000)

    def test_absurd_official_time_is_ignored(self):
        h = Harness()

        def wrong(frame):
            if frame.last_lap_ms:
                frame.last_lap_ms += 9000

        h.run_until_laps(1, mutate=wrong)
        self.assertEqual(h.laps[0].time_source, "mesure")

    def test_duplicate_packets_are_ignored(self):
        h = Harness()
        twin = Harness()
        while len(h.laps) < 1:
            frame = h.step()
            h.recorder.feed(frame)  # meme image relue : le jeu n'a rien publie de neuf
            twin.step()
        self.assertEqual(len(twin.laps), 1)
        self.assertEqual(h.laps[0].own_ms, twin.laps[0].own_ms)
        self.assertEqual(h.laps[0].n, twin.laps[0].n)


class Validity(unittest.TestCase):
    def test_game_invalidation_is_kept_with_its_reason(self):
        h = Harness()
        h.run_until_npos(0.30, 0.32)

        def cut(frame):
            if 0.32 < frame.npos < 0.40:
                frame.valid = False

        h.run_until_laps(1, mutate=cut)
        self.assertFalse(h.laps[0].valid)
        self.assertIn("limites de piste", h.laps[0].reason)
        h.run_until_laps(2)
        self.assertTrue(h.laps[1].valid, "le tour suivant repart valide")

    def test_pit_lane_invalidates(self):
        h = Harness()
        h.run_until_npos(0.2, 0.22)

        def pit(frame):
            if 0.22 < frame.npos < 0.25:
                frame.in_pit = True

        h.run_until_laps(1, mutate=pit)
        self.assertFalse(h.laps[0].valid)
        self.assertIn("stands", h.laps[0].reason)

    def test_pause_is_removed_from_the_time_and_invalidates(self):
        clean = Harness()
        clean.run_until_laps(1)
        h = Harness()
        h.run_until_npos(0.4, 0.42)
        for _ in range(50):  # 5 secondes de pause : le jeu publie le statut pause
            h.shift += 0.1
            frame = h.source.advance(0.0)
            frame.t += h.shift
            frame.status = STATUS_PAUSE
            h.recorder.feed(frame)
        h.run_until_laps(1)
        lap = h.laps[0]
        self.assertFalse(lap.valid)
        self.assertIn("interruption", lap.reason)
        self.assertLess(abs(lap.own_ms - clean.laps[0].own_ms), 150, "la pause ne compte pas dans le temps")

    def test_teleport_back_to_pits_discards_the_lap(self):
        h = Harness()
        h.run_until_npos(0.5, 0.52)
        frame = h.step(mutate=lambda f: setattr(f, "npos", 0.05))
        self.assertFalse(h.recorder.lap_in_progress)
        self.assertIsNone(h.recorder.lap_seconds)
        while h.step().npos > 0.5:
            pass
        self.assertEqual(h.laps, [], "le tour interrompu par un retour au stand est abandonne")
        h.run_until_laps(1)
        self.assertTrue(h.laps[0].valid)

    def test_forward_jump_invalidates(self):
        h = Harness()
        h.run_until_npos(0.30, 0.31)
        skipped = [False]

        def jump(frame):
            if not skipped[0]:
                skipped[0] = True
                h.source._lap_t += 6.0  # six secondes de piste avalees d'un coup

        h.run_until_laps(1, mutate=jump)
        self.assertFalse(h.laps[0].valid)
        self.assertTrue("saut de position" in h.laps[0].reason or "incomplètes" in h.laps[0].reason)

    def test_replay_and_menu_drop_the_lap_in_progress(self):
        h = Harness()
        h.run_until_npos(0.4, 0.42)
        h.step(mutate=lambda f: setattr(f, "status", STATUS_REPLAY))
        self.assertFalse(h.recorder.lap_in_progress)
        while h.step().npos > 0.3:
            pass
        self.assertEqual(h.laps, [])

    def test_inconsistent_data_status_stops_recording(self):
        h = Harness()
        h.run_until_npos(0.4, 0.42)
        h.step(mutate=lambda f: setattr(f, "status", -1))
        self.assertFalse(h.recorder.lap_in_progress)

    def test_ai_driven_laps_are_not_recorded(self):
        h = Harness()

        def ai(frame):
            frame.ai = True

        for _ in range(12000):
            h.step(mutate=ai)
        self.assertEqual(h.laps, [])


class Combos(unittest.TestCase):
    def test_changing_car_opens_a_new_profile_and_drops_the_lap(self):
        h = Harness()
        h.run_until_laps(1)
        h.run_until_npos(0.3, 0.32)
        h.source.set_car("Démo Roadster Cup")
        h.run_until_laps(2)
        self.assertEqual([c[0] for c in h.combos], ["Démo GT3", "Démo Roadster Cup"])
        self.assertEqual(h.laps[0].car, "Démo GT3")
        self.assertEqual(h.laps[1].car, "Démo Roadster Cup")
        self.assertGreater(h.laps[1].time_ms, h.laps[0].time_ms, "la Roadster est plus lente que la GT3")

    def test_changing_layout_opens_a_new_profile(self):
        h = Harness()
        h.step()
        h.step(mutate=lambda f: setattr(f, "config", "National"))
        self.assertEqual(h.combos[-1], ("Démo GT3", "Circuit de démonstration", "National"))
        self.assertEqual(len(h.combos), 2)

    def test_pending_lap_is_kept_on_flush(self):
        h = Harness()

        def mute(frame):
            frame.last_lap_ms = 0

        while not h.recorder._pending:
            h.step(mutate=mute)
        self.assertEqual(h.laps, [])
        h.recorder.flush()
        self.assertEqual(len(h.laps), 1)


if __name__ == "__main__":
    unittest.main()
