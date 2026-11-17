"""Reechantillonnage, detection des virages, mesures, coaching et stockage."""
import os
import unittest

from irms import analysis as A
from irms import coaching
from irms.engine import next_cue
from irms.insights import Insights
from irms.recorder import CHANNELS, LapRecord
from irms.simulator import DemoTrack
from irms.storage import Storage, pack_samples, unpack_samples

from .helpers import seeded_storage, temp_db


def combo_of(storage, car):
    return [c for c in storage.combos() if c["car"] == car][0]


class Resample(unittest.TestCase):
    def test_linear_interpolation_on_a_regular_grid(self):
        samples = dict((name, [0.0, 0.0, 0.0]) for name in CHANNELS)
        samples["d"] = [0.0, 500.0, 1000.0]
        samples["t"] = [0.0, 10.0, 30.0]
        samples["speed"] = [100.0, 200.0, 100.0]
        samples["gear"] = [2.0, 3.0, 5.0]
        rs = A.resample(samples, 1000.0, 30.0, n=10)
        self.assertEqual(rs["n"], 10)
        self.assertEqual(len(rs["speed"]), 11)
        self.assertAlmostEqual(rs["speed"][5], 200.0)
        self.assertAlmostEqual(rs["speed"][2], 140.0)
        self.assertAlmostEqual(rs["t"][0], 0.0)
        self.assertAlmostEqual(rs["t"][10], 30.0)
        self.assertAlmostEqual(rs["t"][7], 18.0)
        self.assertIn(rs["gear"][2], (2.0, 3.0), "le rapport n'est jamais interpole")

    def test_time_is_monotonic_and_ends_on_the_lap_time(self):
        storage = seeded_storage()
        insights = Insights(storage)
        combo = combo_of(storage, "Démo GT3")
        for lap in storage.laps(combo["id"])[:3]:
            rs = insights.resampled(lap["id"])
            self.assertTrue(all(b >= a for a, b in zip(rs["t"], rs["t"][1:])))
            self.assertAlmostEqual(rs["t"][-1], lap["own_ms"] / 1000.0, places=2)
            self.assertAlmostEqual(sum(A.sectors(rs)), lap["own_ms"] / 1000.0, places=2)

    def test_duplicate_and_backward_distances_are_dropped(self):
        samples = dict((name, [1.0] * 5) for name in CHANNELS)
        samples["d"] = [0.0, 100.0, 100.0, 90.0, 200.0]
        samples["t"] = [0.0, 1.0, 1.1, 1.2, 2.0]
        rs = A.resample(samples, 200.0, 2.0, n=4)
        self.assertEqual(rs["t"], [0.0, 0.5, 1.0, 1.5, 2.0])

    def test_empty_lap_does_not_crash(self):
        rs = A.resample(dict((name, []) for name in CHANNELS), 1000.0, 0.0)
        self.assertEqual(set(rs["speed"]), {0.0})


class Corners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = seeded_storage()
        cls.insights = Insights(cls.storage)
        cls.gt3 = cls.insights.combo(combo_of(cls.storage, "Démo GT3")["id"])
        cls.roadster = cls.insights.combo(combo_of(cls.storage, "Démo Roadster Cup")["id"])

    def test_all_ten_corners_are_found_for_both_cars(self):
        self.assertEqual(len(self.gt3.corners), 10)
        self.assertEqual(len(self.roadster.corners), 10)

    def test_corners_sit_on_the_real_bends(self):
        """Chaque corde detectee tombe dans un arc du trace de demonstration."""
        track = DemoTrack()
        step = self.gt3.step
        for corner in self.gt3.corners:
            i = int(round(corner["apex"] * step / track.length * track.n)) % track.n
            self.assertGreater(abs(track.kappa[i]), 1.0 / 200.0, corner["name"])

    def test_directions_follow_the_steering(self):
        dirs = [c["dir"] for c in self.gt3.corners]
        self.assertEqual(dirs, [c["dir"] for c in self.roadster.corners], "meme circuit, memes directions")
        self.assertIn("gauche", dirs)
        self.assertGreater(dirs.count("droite"), dirs.count("gauche"), "trace horaire")

    def test_segments_tile_the_lap_without_gap_or_overlap(self):
        corners = self.gt3.corners
        self.assertEqual(corners[0]["seg_start"], 0)
        self.assertEqual(corners[-1]["seg_end"], self.gt3.ref_rs["n"])
        for prev, cur in zip(corners, corners[1:]):
            self.assertEqual(prev["seg_end"], cur["seg_start"])
            self.assertLess(prev["apex"], cur["apex"])
        for corner in corners:
            self.assertLessEqual(corner["seg_start"], corner["start"])
            self.assertLessEqual(corner["start"], corner["apex"])
            self.assertLessEqual(corner["apex"], corner["end"])
            self.assertLessEqual(corner["end"], corner["seg_end"])

    def test_segment_times_add_up_to_the_lap_time(self):
        for lap in self.gt3.valid[:4]:
            total = sum(m["time"] for m in self.gt3.metrics[lap["id"]])
            self.assertAlmostEqual(total, lap["own_ms"] / 1000.0, places=2)

    def test_brake_points_are_ordered(self):
        for m in self.gt3.metrics[self.gt3.ref["id"]]:
            if m["brake_on"] is not None:
                self.assertLess(m["brake_on"], m["min_at"] + 1)
                self.assertLessEqual(m["brake_on"], m["brake_off"])
            self.assertGreater(m["min_speed"], 30.0)
            self.assertGreaterEqual(m["entry_speed"], m["min_speed"])

    def test_the_slower_car_brakes_later_and_is_slower(self):
        """Les reperes sont propres a chaque voiture : c'est le but des profils."""
        self.assertGreater(self.roadster.best["time_ms"], self.gt3.best["time_ms"] + 10000)
        g = self.gt3.metrics[self.gt3.ref["id"]][0]
        r = self.roadster.metrics[self.roadster.ref["id"]][0]
        self.assertGreater(g["entry_speed"], r["entry_speed"] + 30.0)
        self.assertNotEqual(g["brake_on"], r["brake_on"])

    def test_mirrored_map_is_detected(self):
        rs = self.gt3.ref_rs
        normal = A.geometry(rs, True)
        mirrored = dict(rs)
        mirrored["z"] = [-v for v in rs["z"]]
        flipped = A.geometry(mirrored, True)
        self.assertNotEqual(normal["flip"], flipped["flip"])
        a = [c["dir"] for c in A.detect_corners(rs, normal)]
        b = [c["dir"] for c in A.detect_corners(mirrored, flipped)]
        self.assertEqual(a, b, "gauche et droite ne dependent pas du sens des axes du jeu")

    def test_corners_are_found_without_world_position(self):
        rs = self.gt3.ref_rs
        geo = A.geometry(rs, False)
        self.assertFalse(geo["has_pos"])
        corners = A.detect_corners(rs, geo)
        self.assertGreaterEqual(len(corners), 8)
        self.assertLessEqual(len(corners), 12)

    def test_theoretical_best_is_not_slower_than_the_record(self):
        for analysis in (self.gt3, self.roadster):
            self.assertLessEqual(analysis.theoretical_ms, analysis.best["time_ms"])
            self.assertGreater(analysis.theoretical_ms, analysis.best["time_ms"] - 3000)

    def test_delta_ends_on_the_lap_time_difference(self):
        other = [lap for lap in self.gt3.valid if lap["id"] != self.gt3.ref["id"]][0]
        view = self.gt3.track_view(other["id"])
        self.assertAlmostEqual(view["delta"][0], 0.0, places=2)
        self.assertAlmostEqual(view["delta"][-1], (other["own_ms"] - self.gt3.ref["own_ms"]) / 1000.0, places=2)
        self.assertAlmostEqual(sum(c["loss"] for c in view["corners"]), view["delta"][-1], places=1)

    def test_car_profile_reflects_the_car(self):
        g = self.gt3.overview()["profile"]
        r = self.roadster.overview()["profile"]
        self.assertGreater(g["top_speed"], r["top_speed"] + 40)
        self.assertGreater(g["brake_g"], r["brake_g"])
        self.assertGreater(g["lat_g"], r["lat_g"])
        self.assertTrue(0 < g["full_throttle"] < 100)


class Cue(unittest.TestCase):
    CORNERS = [
        {"name": "T1", "dir": "droite", "apex": 500.0, "seg_start": 0.0, "seg_end": 700.0, "brake_on": 400.0,
         "brake_off": 480.0, "gas_on": 520.0, "min_speed": 90.0, "min_gear": 2},
        {"name": "T2", "dir": "gauche", "apex": 900.0, "seg_start": 700.0, "seg_end": 1200.0, "brake_on": None,
         "brake_off": None, "gas_on": None, "min_speed": 180.0, "min_gear": 5},
    ]

    def test_phases_follow_the_lap(self):
        cue = next_cue(self.CORNERS, 100.0, 1200.0)
        self.assertEqual((cue["name"], cue["phase"], cue["to_brake"]), ("T1", "gaz", 300))
        cue = next_cue(self.CORNERS, 300.0, 1200.0)
        self.assertEqual((cue["phase"], cue["to_brake"]), ("approche", 100))
        cue = next_cue(self.CORNERS, 450.0, 1200.0)
        self.assertEqual(cue["phase"], "frein")
        cue = next_cue(self.CORNERS, 490.0, 1200.0)
        self.assertEqual(cue["phase"], "corde")

    def test_flat_corner_has_no_brake_cue(self):
        cue = next_cue(self.CORNERS, 850.0, 1200.0)
        self.assertEqual(cue["name"], "T2")
        self.assertFalse(cue["braking"])
        self.assertEqual(cue["phase"], "passe")
        self.assertIsNone(cue["to_brake"])

    def test_wraps_to_the_first_corner_after_the_last(self):
        cue = next_cue(self.CORNERS, 1100.0, 1200.0)
        self.assertEqual(cue["name"], "T1")
        self.assertEqual(cue["to_apex"], 600)

    def test_no_corner_no_cue(self):
        self.assertIsNone(next_cue([], 10.0, 1000.0))


class Coaching(unittest.TestCase):
    """Le simulateur injecte des faiblesses connues : le coaching doit les retrouver."""

    @classmethod
    def setUpClass(cls):
        storage = seeded_storage()
        insights = Insights(storage)
        cls.gt3 = insights.combo(combo_of(storage, "Démo GT3")["id"]).coaching_view("position")
        cls.gt3_lc = insights.combo(combo_of(storage, "Démo GT3")["id"]).coaching_view("loadcell")
        cls.roadster = insights.combo(combo_of(storage, "Démo Roadster Cup")["id"]).coaching_view("position")

    def card(self, view, corner):
        found = [c for c in view["cards"] if c["corner"] == corner]
        self.assertTrue(found, "aucune carte pour le virage %d" % (corner + 1))
        return found[0]

    def test_gt3_early_braking_at_t3(self):
        card = self.card(self.gt3, 2)
        self.assertEqual(card["cause"], "early_brake")
        self.assertEqual(card["pattern"], "récurrent")
        brake = [e for e in card["evidence"] if e["label"] == "Début du freinage"][0]
        self.assertLess(brake["you"], brake["target"] - 10, "freinage plus loin de la corde que la cible")

    def test_gt3_hesitant_throttle_at_t7_absorbs_the_loss_in_t8(self):
        card = self.card(self.gt3, 6)
        self.assertEqual(card["cause"], "slow_gas")
        self.assertEqual(card["severity"], "prioritaire")
        self.assertEqual(card.get("carry", {}).get("name"), "T8")
        self.assertFalse([c for c in self.gt3["cards"] if c["corner"] == 7], "T8 n'a pas de carte a part")
        self.assertTrue([e for e in card["evidence"] if e["label"] == "Plein gaz"])

    def test_roadster_weaknesses(self):
        self.assertEqual(self.card(self.roadster, 0)["cause"], "over_slow")
        self.assertIn(self.card(self.roadster, 4)["cause"], ("lift", "coast", "late_gas", "slow_gas"))

    def test_advice_differs_between_cars(self):
        gt3 = set(c["corner"] for c in self.gt3["cards"][:2])
        roadster = set(c["corner"] for c in self.roadster["cards"][:2])
        self.assertNotEqual(gt3, roadster)

    def test_cards_are_sorted_and_complete(self):
        for view in (self.gt3, self.roadster):
            self.assertTrue(view["ready"])
            corner_cards = [c for c in view["cards"] if c["corner"] is not None]
            gains = [c["gain_s"] for c in corner_cards]
            self.assertEqual(gains, sorted(gains, reverse=True))
            self.assertLessEqual(len(corner_cards), 6)
            self.assertAlmostEqual(view["potential_s"], sum(gains), places=2)
            for card in view["cards"]:
                for key in ("title", "observation", "hypothesis", "exercise", "severity", "pattern", "confidence"):
                    self.assertTrue(card[key], key)
                self.assertIn(card["severity"], ("prioritaire", "à travailler", "à surveiller"))
                self.assertIn(card["pattern"], ("récurrent", "ponctuel", "variable", "global"))

    def test_one_off_mistakes_never_rank_as_priority(self):
        for view in (self.gt3, self.roadster):
            for card in view["cards"]:
                if card["pattern"] == "ponctuel":
                    self.assertEqual(card["severity"], "à surveiller")
                    self.assertIn("Erreur isolée", card["exercise"])

    def test_hypotheses_are_worded_as_hypotheses(self):
        for card in self.gt3["cards"] + self.roadster["cards"]:
            if card["corner"] is not None:
                self.assertIn("probablement", card["hypothesis"])

    def test_brake_advice_depends_on_the_pedal_type(self):
        position = self.card(self.gt3, 2)["exercise"]
        loadcell = self.card(self.gt3_lc, 2)["exercise"]
        self.assertIn("course de la pédale", position)
        self.assertIn("pression", loadcell)
        self.assertNotEqual(position, loadcell)

    def test_strengths_are_not_also_weaknesses(self):
        weak = set("T%d" % (c["corner"] + 1) for c in self.gt3["cards"] if c["corner"] is not None)
        self.assertFalse(weak & set(self.gt3["strengths"]))

    def test_not_enough_valid_laps(self):
        storage = seeded_storage(2)
        view = Insights(storage).combo(storage.combos()[0]["id"]).coaching_view()
        self.assertFalse(view["ready"])
        self.assertEqual(view["needed"], coaching.MIN_VALID)
        self.assertLess(view["valid_laps"], coaching.MIN_VALID)


class Reference(unittest.TestCase):
    def setUp(self):
        self.storage = Storage(temp_db())
        source = seeded_storage()
        combo = combo_of(source, "Démo GT3")
        self.ids = []
        for row in source.laps(combo["id"])[:6]:
            lap = source.lap(row["id"])
            record = LapRecord((combo["car"], combo["track"], combo["config"]), combo["track_length"], lap["samples"])
            record.own_ms, record.time_ms, record.valid, record.reason = lap["own_ms"], lap["time_ms"], bool(lap["valid"]), lap["reason"]
            record.meta = lap["meta"]
            self.combo_id, lap_id = self.storage.add_lap(record, "import")
            self.ids.append(lap_id)
        self.insights = Insights(self.storage)

    def analysis(self):
        return self.insights.combo(self.combo_id)

    def test_reference_is_the_best_valid_lap_by_default(self):
        analysis = self.analysis()
        valid = [lap for lap in analysis.laps if lap["valid"]]
        best = min(valid, key=lambda lap: lap["time_ms"])
        self.assertEqual(analysis.ref["id"], best["id"])
        self.assertFalse(analysis.overview()["ref_pinned"])

    def test_invalid_lap_is_never_the_automatic_reference(self):
        analysis = self.analysis()
        fastest = min(analysis.laps, key=lambda lap: lap["time_ms"])
        self.storage.set_lap_valid(analysis.ref["id"], False, "test")
        again = self.analysis()
        self.assertNotEqual(again.ref["id"], analysis.ref["id"])
        self.assertTrue(again.ref["valid"])
        self.assertTrue(fastest)

    def test_pinned_reference_wins_and_survives_new_laps(self):
        target = self.ids[1]
        self.storage.set_reference(self.combo_id, target)
        analysis = self.analysis()
        self.assertEqual(analysis.ref["id"], target)
        self.assertTrue(analysis.overview()["ref_pinned"])
        self.storage.set_reference(self.combo_id, None)
        self.assertFalse(self.analysis().overview()["ref_pinned"])

    def test_deleting_the_pinned_reference_falls_back(self):
        target = self.ids[1]
        self.storage.set_reference(self.combo_id, target)
        self.storage.delete_lap(target)
        analysis = self.analysis()
        self.assertNotEqual(analysis.ref["id"], target)
        self.assertFalse(analysis.overview()["ref_pinned"])

    def test_only_invalid_laps_gives_a_provisional_reference(self):
        for lap_id in self.ids:
            self.storage.set_lap_valid(lap_id, False, "test")
        analysis = self.analysis()
        self.assertTrue(analysis.ref_provisional)
        self.assertTrue(analysis.track_view()["ready"])
        self.assertFalse(analysis.coaching_view()["ready"])

    def test_corner_names_follow_the_corner(self):
        analysis = self.analysis()
        apex = analysis.corners[3]["apex"] * analysis.step
        self.storage.set_corner_names(self.combo_id, {str(apex + 12.0): "Chicane"})
        names = [c["name"] for c in self.analysis().corners]
        self.assertEqual(names[3], "Chicane")
        self.assertEqual(names[2], "T3")

    def test_cache_is_refreshed_after_a_change(self):
        first = self.analysis()
        self.assertIs(first, self.analysis(), "sans changement, l'analyse est reutilisee")
        self.storage.delete_lap(self.ids[-1])
        self.assertIsNot(first, self.analysis())


class StorageTests(unittest.TestCase):
    def test_samples_round_trip(self):
        samples = dict((name, [0.5 * i for i in range(300)]) for name in CHANNELS)
        back = unpack_samples(pack_samples(samples))
        self.assertEqual(sorted(back), sorted(CHANNELS))
        for name in CHANNELS:
            self.assertEqual(len(back[name]), 300)
            self.assertAlmostEqual(back[name][299], samples[name][299], places=3)

    def test_database_survives_a_restart(self):
        path = temp_db()
        storage = Storage(path)
        samples = dict((name, [float(i) for i in range(100)]) for name in CHANNELS)
        lap = LapRecord(("Voiture", "Circuit", "GP"), 4000.0, samples)
        lap.own_ms = lap.time_ms = 90000
        combo_id, lap_id = storage.add_lap(lap)
        storage.set_setting("pedals", "loadcell")
        storage.close()
        again = Storage(path)
        self.assertEqual(again.setting("pedals"), "loadcell")
        self.assertEqual(again.lap(lap_id)["time_ms"], 90000)
        self.assertEqual(again.combos()[0]["car"], "Voiture")
        again.close()
        self.assertTrue(os.path.exists(path))

    def test_profiles_are_split_by_car_track_layout_and_length(self):
        storage = Storage(temp_db())
        a = storage.combo_id("A", "Piste", "GP", 4000.0)
        self.assertEqual(a, storage.combo_id("A", "Piste", "GP", 4000.0))
        others = set([storage.combo_id("B", "Piste", "GP", 4000.0), storage.combo_id("A", "Autre", "GP", 4000.0),
                      storage.combo_id("A", "Piste", "Court", 4000.0), storage.combo_id("A", "Piste", "GP", 4200.0)])
        self.assertEqual(len(others), 4)
        self.assertNotIn(a, others)
        self.assertIsNone(storage.find_combo("Z", "Piste", "GP", 4000.0), "find_combo ne cree rien")

    def test_deleting_a_profile_deletes_its_laps(self):
        storage = Storage(temp_db())
        samples = dict((name, [float(i) for i in range(100)]) for name in CHANNELS)
        lap = LapRecord(("Voiture", "Circuit", "GP"), 4000.0, samples)
        lap.own_ms = lap.time_ms = 90000
        combo_id, lap_id = storage.add_lap(lap)
        before = storage.revision
        storage.delete_combo(combo_id)
        self.assertIsNone(storage.lap(lap_id))
        self.assertEqual(storage.combos(), [])
        self.assertGreater(storage.revision, before)


if __name__ == "__main__":
    unittest.main()
