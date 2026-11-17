"""API HTTP : lectures, ecritures, protections."""
import gzip
import http.client
import json
import threading
import unittest

from irms import __version__
from irms import server as server_module
from irms.engine import Engine
from irms.server import App, make_server
from irms.simulator import DemoSource
from irms.storage import Storage

from .helpers import seeded_storage, temp_db


def copy_seed():
    """Base neuve contenant les tours de demo (les tests d'ecriture la modifient)."""
    source = seeded_storage()
    path = temp_db()
    source._db.commit()
    import sqlite3
    target = sqlite3.connect(path)
    with source._lock:
        source._db.backup(target)
    target.close()
    return Storage(path)


class ServerCase(unittest.TestCase):
    lan = False
    lan_write = False

    @classmethod
    def setUpClass(cls):
        cls.storage = copy_seed()
        cls.engine = Engine(cls.storage, DemoSource("Démo GT3", seed=2))
        for _ in range(5):
            cls.engine.step()
        cls.app = App(cls.engine, lan=cls.lan, lan_write=cls.lan_write, port=0)
        cls.server = make_server(cls.app, "127.0.0.1")
        cls.port = cls.server.server_address[1]
        cls.app.port = cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        cls.thread.start()
        cls.combo_id = [c for c in cls.storage.combos() if c["car"] == "Démo GT3"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2.0)
        cls.storage.close()

    def request(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        send = {"Host": "127.0.0.1:%d" % self.port}
        payload = raw
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            send["Content-Type"] = "application/json"
        send.update(headers or {})
        conn.request(method, path, payload, send)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        if response.getheader("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return response, data

    def get_json(self, path, status=200):
        response, data = self.request("GET", path)
        self.assertEqual(response.status, status, data[:200])
        return json.loads(data.decode("utf-8"))

    def post(self, path, body, status=200, **kw):
        response, data = self.request("POST", path, body, **kw)
        self.assertEqual(response.status, status, data[:200])
        return json.loads(data.decode("utf-8"))


class Reads(ServerCase):
    def test_status(self):
        status = self.get_json("/api/status")
        self.assertEqual(status["version"], __version__)
        self.assertEqual(status["source"], "demo")
        self.assertEqual(status["pedals"], "position")
        self.assertFalse(status["lan"])
        self.assertEqual(sorted(status["demo_cars"]), ["Démo GT3", "Démo Roadster Cup"])

    def test_live_snapshot(self):
        live = self.get_json("/api/live.json")
        self.assertTrue(live["connected"])
        self.assertEqual(live["car"], "Démo GT3")
        self.assertEqual(live["combo_id"], self.combo_id, "la voiture du jeu retrouve son profil")
        for key in ("speed", "gear", "gas", "brake", "dist", "lap_time_ms", "valid", "recording", "revision", "cue"):
            self.assertIn(key, live)

    def test_live_stream_sends_events(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/live", headers={"Host": "127.0.0.1:%d" % self.port})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertTrue(response.getheader("Content-Type").startswith("text/event-stream"))
        line = response.fp.readline().decode("utf-8")
        conn.close()
        self.assertTrue(line.startswith("data: "))
        self.assertIn("connected", json.loads(line[6:]))

    def test_combos_and_overview(self):
        combos = self.get_json("/api/combos")
        self.assertEqual(len(combos["combos"]), 2)
        overview = self.get_json("/api/combos/%d" % self.combo_id)
        self.assertEqual(overview["combo"]["car"], "Démo GT3")
        self.assertEqual(len(overview["laps"]), 12)
        self.assertEqual(overview["corners"], 10)
        self.assertEqual(sum(1 for lap in overview["laps"] if lap["is_ref"]), 1)
        self.assertEqual(sum(1 for lap in overview["laps"] if lap["is_best"]), 1)
        self.assertLessEqual(overview["theoretical_ms"], overview["best_ms"])
        for lap in overview["laps"]:
            self.assertAlmostEqual(sum(lap["sectors"]), lap["time_ms"] / 1000.0, delta=0.05)

    def test_track_view(self):
        overview = self.get_json("/api/combos/%d" % self.combo_id)
        other = [lap for lap in overview["laps"] if not lap["is_ref"]][0]
        track = self.get_json("/api/combos/%d/track?lap=%d" % (self.combo_id, other["id"]))
        self.assertTrue(track["ready"])
        self.assertTrue(track["has_pos"])
        n = track["n"]
        self.assertEqual(len(track["x"]), n + 1)
        self.assertEqual(len(track["delta"]), n + 1)
        self.assertEqual(len(track["ref"]["channels"]["speed"]), n + 1)
        self.assertEqual(track["lap"]["lap_id"], other["id"])
        self.assertEqual(len(track["corners"]), 10)
        for corner in track["corners"]:
            self.assertLessEqual(corner["seg_start"], corner["apex"])
            self.assertLessEqual(corner["apex"], corner["seg_end"])
            self.assertIn("lap", corner)

    def test_coaching(self):
        coaching = self.get_json("/api/combos/%d/coaching" % self.combo_id)
        self.assertTrue(coaching["ready"])
        self.assertTrue(coaching["cards"])

    def test_doctor_report_has_no_personal_data(self):
        text = json.dumps(self.get_json("/api/doctor")).lower()
        self.assertNotIn("driver", text)
        self.assertIn("structures", text)

    def test_static_files_and_security_headers(self):
        response, data = self.request("GET", "/", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.status, 200)
        self.assertIn(b"IRMS", data)
        self.assertEqual(response.getheader("Content-Encoding"), "gzip")
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
        self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
        for path, ctype in (("/app.js", "application/javascript"), ("/style.css", "text/css"),
                            ("/icon.svg", "image/svg+xml")):
            response, data = self.request("GET", path)
            self.assertEqual(response.status, 200, path)
            self.assertTrue(response.getheader("Content-Type").startswith(ctype), path)
            self.assertGreater(len(data), 100)

    def test_interface_needs_no_external_resource(self):
        import os
        import re
        for name in os.listdir(server_module.WEB_ROOT):
            if name.rsplit(".", 1)[-1] not in ("html", "css", "js"):
                continue
            with open(os.path.join(server_module.WEB_ROOT, name), "r", encoding="utf-8") as handle:
                text = handle.read()
            links = [u for u in re.findall(r"https?://[^\s\"')]+", text) if "w3.org" not in u]
            self.assertEqual(links, [], "%s doit fonctionner hors ligne" % name)

    def test_unknown_addresses(self):
        for path in ("/api/nope", "/api/combos/9999", "/api/combos/abc", "/nope.html", "/api/laps/9999/export"):
            response, _ = self.request("GET", path)
            self.assertEqual(response.status, 404, path)


class Protections(ServerCase):
    def test_path_traversal_is_refused(self):
        for path in ("/../irms/server.py", "/..%2Firms%2Fserver.py", "/%2e%2e/README.md", "//etc/passwd",
                     "/../../../../etc/passwd", "/..\\irms\\server.py"):
            response, data = self.request("GET", path)
            self.assertEqual(response.status, 404, path)
            self.assertNotIn(b"import", data)

    def test_foreign_host_header_is_refused(self):
        """Protection contre le DNS rebinding : seul un nom local est accepte."""
        for host in ("evil.example", "evil.example:%d" % self.port, "192.168.1.50:%d" % self.port, ""):
            response, _ = self.request("GET", "/api/status", headers={"Host": host})
            self.assertEqual(response.status, 403, host)
        response, _ = self.request("GET", "/api/status", headers={"Host": "localhost:%d" % self.port})
        self.assertEqual(response.status, 200)

    def test_cross_site_write_is_refused(self):
        self.post("/api/settings", {"pedals": "loadcell"}, 403, headers={"Origin": "https://evil.example"})
        self.assertEqual(self.get_json("/api/settings")["pedals"], "position")
        self.post("/api/settings", {"pedals": "position"}, 200, headers={"Origin": "http://127.0.0.1:%d" % self.port})

    def test_form_posts_are_refused(self):
        """Un formulaire HTML d'un autre site ne peut pas envoyer du JSON."""
        for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            response, _ = self.request("POST", "/api/settings", raw=b'{"pedals":"loadcell"}',
                                       headers={"Content-Type": ctype})
            self.assertEqual(response.status, 415, ctype)

    def test_bad_bodies(self):
        response, _ = self.request("POST", "/api/settings", raw=b"{oops", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status, 400)
        response, _ = self.request("POST", "/api/settings", raw=b"[1,2]", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status, 400)
        response, _ = self.request("POST", "/api/settings", raw=b"", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status, 413)
        self.post("/api/settings", {"pedals": "hydraulique"}, 400)
        self.post("/api/demo/car", {"car": "Inconnue"}, 400)
        self.post("/api/import", {"format": "autre"}, 400)
        self.post("/api/laps/9999/valid", {"valid": True}, 404)
        self.post("/api/combos/%d/reference" % self.combo_id, {"lap_id": 9999}, 404)
        self.post("/api/combos/%d/corners" % self.combo_id, {"names": {"abc": "x"}}, 400)

    def test_errors_never_leak_a_traceback(self):
        response, data = self.request("POST", "/api/import", {"format": "irms-lap", "channels": 5})
        self.assertEqual(response.status, 400)
        self.assertNotIn(b"Traceback", data)
        self.assertNotIn(b"File \"", data)

    def test_unsupported_methods(self):
        response, _ = self.request("PUT", "/api/status")
        self.assertIn(response.status, (405, 501))
        response, _ = self.request("DELETE", "/api/status")
        self.assertEqual(response.status, 404)


class LanReadOnly(ServerCase):
    lan = True

    def setUp(self):
        self._loopback = server_module.LOOPBACK
        server_module.LOOPBACK = ()  # le client de test est traite comme un appareil du reseau

    def tearDown(self):
        server_module.LOOPBACK = self._loopback

    def test_network_devices_can_read(self):
        self.assertTrue(self.get_json("/api/status")["lan"])
        self.assertTrue(self.get_json("/api/combos")["combos"])
        self.assertTrue(self.get_json("/api/combos/%d/track" % self.combo_id)["ready"])

    def test_network_devices_cannot_write(self):
        laps = self.get_json("/api/combos/%d" % self.combo_id)["laps"]
        self.post("/api/settings", {"pedals": "loadcell"}, 403)
        self.post("/api/laps/%d/valid" % laps[0]["id"], {"valid": False}, 403)
        response, _ = self.request("DELETE", "/api/laps/%d" % laps[0]["id"])
        self.assertEqual(response.status, 403)
        response, _ = self.request("DELETE", "/api/combos/%d" % self.combo_id)
        self.assertEqual(response.status, 403)
        self.assertEqual(len(self.get_json("/api/combos/%d" % self.combo_id)["laps"]), len(laps))


class LanWrite(LanReadOnly):
    lan_write = True

    def test_network_devices_cannot_write(self):
        self.post("/api/settings", {"pedals": "loadcell"}, 200)
        self.post("/api/settings", {"pedals": "position"}, 200)


class Writes(ServerCase):
    def laps(self):
        return self.get_json("/api/combos/%d" % self.combo_id)["laps"]

    def test_1_export_then_import_round_trip(self):
        lap = self.laps()[4]
        response, data = self.request("GET", "/api/laps/%d/export?format=json" % lap["id"])
        self.assertEqual(response.status, 200)
        self.assertIn("attachment", response.getheader("Content-Disposition"))
        exported = json.loads(data.decode("utf-8"))
        self.assertEqual(exported["format"], "irms-lap")
        self.assertEqual(exported["car"], "Démo GT3")
        self.assertNotIn("driver", data.decode("utf-8").lower())
        exported["car"] = "Voiture importée"
        result = self.post("/api/import", exported)
        self.assertNotEqual(result["combo_id"], self.combo_id, "autre voiture, autre profil")
        overview = self.get_json("/api/combos/%d" % result["combo_id"])
        self.assertEqual(len(overview["laps"]), 1)
        self.assertEqual(overview["laps"][0]["time_ms"], lap["time_ms"])
        self.assertEqual(overview["laps"][0]["source"], "import")
        self.assertEqual(overview["corners"], 10)
        response, _ = self.request("DELETE", "/api/combos/%d" % result["combo_id"])
        self.assertEqual(response.status, 200)
        self.get_json("/api/combos/%d" % result["combo_id"], 404)

    def test_2_csv_export(self):
        lap = self.laps()[0]
        response, data = self.request("GET", "/api/laps/%d/export?format=csv" % lap["id"])
        self.assertEqual(response.status, 200)
        lines = data.decode("utf-8").strip().split("\n")
        self.assertTrue(lines[0].startswith("distance_m,temps_s,vitesse_kmh,gaz,frein"))
        self.assertGreater(len(lines), 500)
        self.assertEqual(len(lines[1].split(",")), 11)

    def test_3_invalidate_changes_the_record(self):
        before = self.get_json("/api/combos/%d" % self.combo_id)
        best = [lap for lap in before["laps"] if lap["is_best"]][0]
        revision = self.get_json("/api/live.json")["revision"]
        self.post("/api/laps/%d/valid" % best["id"], {"valid": False})
        after = self.get_json("/api/combos/%d" % self.combo_id)
        self.assertGreater(after["best_ms"], before["best_ms"])
        self.assertNotEqual(after["ref_lap_id"], best["id"])
        self.assertEqual(after["stats"]["valid"], before["stats"]["valid"] - 1)
        self.engine.step()
        self.assertGreater(self.get_json("/api/live.json")["revision"], revision, "l'interface est prevenue")
        self.post("/api/laps/%d/valid" % best["id"], {"valid": True})
        self.assertEqual(self.get_json("/api/combos/%d" % self.combo_id)["best_ms"], before["best_ms"])

    def test_4_pin_and_release_reference(self):
        laps = self.laps()
        target = [lap for lap in laps if lap["valid"] and not lap["is_ref"]][0]
        self.post("/api/combos/%d/reference" % self.combo_id, {"lap_id": target["id"]})
        overview = self.get_json("/api/combos/%d" % self.combo_id)
        self.assertEqual(overview["ref_lap_id"], target["id"])
        self.assertTrue(overview["ref_pinned"])
        self.engine.refresh_reference()
        self.engine.step()
        self.assertEqual(self.get_json("/api/live.json")["ref_ms"], target["time_ms"], "l'aide en direct suit")
        self.post("/api/combos/%d/reference" % self.combo_id, {"lap_id": None})
        self.assertFalse(self.get_json("/api/combos/%d" % self.combo_id)["ref_pinned"])

    def test_5_rename_corner(self):
        track = self.get_json("/api/combos/%d/track" % self.combo_id)
        apex = track["corners"][2]["apex"]
        self.post("/api/combos/%d/corners" % self.combo_id, {"names": {str(apex): "<b>Épingle</b> très très longue"}})
        name = self.get_json("/api/combos/%d/track" % self.combo_id)["corners"][2]["name"]
        self.assertEqual(name, "<b>Épingle</b> très très"[:24])
        self.post("/api/combos/%d/corners" % self.combo_id, {"names": {}})
        self.assertEqual(self.get_json("/api/combos/%d/track" % self.combo_id)["corners"][2]["name"], "T3")

    def test_6_pedal_setting_changes_the_advice(self):
        self.post("/api/settings", {"pedals": "loadcell"})
        self.assertEqual(self.get_json("/api/status")["pedals"], "loadcell")
        text = json.dumps(self.get_json("/api/combos/%d/coaching" % self.combo_id), ensure_ascii=False)
        self.assertIn("cellule de charge", text)
        self.post("/api/settings", {"pedals": "position"})

    def test_7_delete_lap(self):
        laps = self.laps()
        response, _ = self.request("DELETE", "/api/laps/%d" % laps[0]["id"])
        self.assertEqual(response.status, 200)
        self.assertEqual(len(self.laps()), len(laps) - 1)
        self.get_json("/api/laps/%d/export" % laps[0]["id"], 404)

    def test_8_demo_car_switch_opens_the_other_profile(self):
        self.post("/api/demo/car", {"car": "Démo Roadster Cup"})
        self.engine.step()
        live = self.get_json("/api/live.json")
        self.assertEqual(live["car"], "Démo Roadster Cup")
        self.assertNotEqual(live["combo_id"], self.combo_id)
        self.assertIsNotNone(live["combo_id"])
        self.engine.refresh_reference()
        self.engine.step()
        live = self.get_json("/api/live.json")
        roadster = self.get_json("/api/combos/%d" % live["combo_id"])
        self.assertEqual(live["ref_ms"], roadster["best_ms"], "les reperes sont ceux de la nouvelle voiture")
        self.assertIsNotNone(live["cue"])

    def test_9_delete_profile(self):
        response, _ = self.request("DELETE", "/api/combos/%d" % self.combo_id)
        self.assertEqual(response.status, 200)
        self.assertEqual(len(self.get_json("/api/combos")["combos"]), 1)


if __name__ == "__main__":
    unittest.main()
