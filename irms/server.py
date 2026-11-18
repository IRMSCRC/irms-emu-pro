"""Serveur HTTP local : interface web, API JSON et flux temps reel (SSE).

Aucune dependance externe. Par defaut le serveur n'ecoute que sur cet
ordinateur (127.0.0.1). En mode reseau local (--lan), les autres appareils
(iPad) peuvent consulter mais pas modifier ni supprimer.
"""
import csv
import gzip
import io
import json
import os
import re
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from . import doctor
from .recorder import CHANNELS, LapRecord
from . import analysis as A

WEB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MAX_BODY = 32 * 1024 * 1024
MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8",
}
# Tout est servi localement : aucune ressource externe n'est autorisee.
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def lan_addresses():
    found = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            found.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = item[4][0]
            if address not in found and not address.startswith("127."):
                found.append(address)
    except OSError:
        pass
    return [a for a in found if not a.startswith("127.")]


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


class App(object):
    """Etat partage entre les requetes."""

    def __init__(self, engine, lan=False, lan_write=False, port=8765):
        self.engine = engine
        self.storage = engine.storage
        self.insights = engine.insights
        self.lan = lan
        self.lan_write = lan_write
        self.port = port
        self.addresses = lan_addresses() if lan else []
        hosts = set(["localhost", "127.0.0.1", "[::1]"])
        if lan:
            hosts.update(self.addresses)
            name = socket.gethostname().lower()
            hosts.update([name, name + ".local"])
        self.hosts = hosts

    # -- lectures ---------------------------------------------------------
    def status(self):
        state = self.engine.source.state
        return {
            "app": "IRMS ému pro", "version": __version__, "source": state["source"],
            "connected": state["connected"], "message": state["message"], "problems": state["problems"],
            "platform_ok": state["platform_ok"], "game_version": state["game_version"],
            "lan": self.lan, "lan_urls": ["http://%s:%d/" % (a, self.port) for a in self.addresses],
            "combo_id": self.engine.combo_id, "revision": self.storage.revision,
            "pedals": self.storage.setting("pedals", "position"),
            "demo_cars": self._demo_cars(),
        }

    def _demo_cars(self):
        if self.engine.source.kind != "demo":
            return []
        from .simulator import CARS
        return sorted(CARS)

    def combos(self):
        return {"combos": self.storage.combos(), "current": self.engine.combo_id}

    def _analysis(self, combo_id):
        analysis = self.insights.combo(combo_id)
        if not analysis.combo:
            raise ApiError(404, "Profil introuvable.")
        return analysis

    def export_lap(self, lap_id, fmt):
        lap = self.storage.lap(lap_id)
        if not lap:
            raise ApiError(404, "Tour introuvable.")
        combo = self.storage.combo(lap["combo_id"])
        if fmt == "csv":
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(["distance_m", "temps_s", "vitesse_kmh", "gaz", "frein", "volant", "rapport", "regime",
                             "g_lateral", "x", "z"])
            samples = lap["samples"]
            for i in range(len(samples["d"])):
                writer.writerow([round(samples[name][i], 4) for name in CHANNELS])
            return out.getvalue().encode("utf-8"), "text/csv; charset=utf-8", "irms-tour-%d.csv" % lap_id
        payload = {
            "format": "irms-lap", "version": 1, "app_version": __version__,
            "car": combo["car"], "track": combo["track"], "config": combo["config"],
            "track_length": combo["track_length"], "time_ms": lap["time_ms"], "own_ms": lap["own_ms"],
            "valid": bool(lap["valid"]), "reason": lap["reason"], "time_source": lap["time_source"],
            "has_pos": bool(lap["has_pos"]), "created_at": lap["created_at"], "meta": lap["meta"],
            "channels": dict((name, [round(v, 4) for v in lap["samples"][name]]) for name in CHANNELS),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return body, "application/json; charset=utf-8", "irms-tour-%d.irmslap.json" % lap_id

    # -- ecritures --------------------------------------------------------
    def import_lap(self, data):
        if not isinstance(data, dict) or data.get("format") != "irms-lap":
            raise ApiError(400, "Ce fichier n'est pas un tour IRMS (format irms-lap attendu).")
        try:
            channels = data["channels"]
            n = len(channels["d"])
            if n < 40 or n > 200000:
                raise ValueError("nombre d'échantillons")
            samples = {}
            for name in CHANNELS:
                column = channels[name]
                if len(column) != n:
                    raise ValueError("voie %s" % name)
                samples[name] = [float(v) for v in column]
            length = float(data["track_length"])
            if not 100.0 <= length <= 30000.0:
                raise ValueError("longueur de piste")
            lap = LapRecord((str(data["car"])[:64], str(data["track"])[:64], str(data.get("config", ""))[:64]),
                            float(round(length)), samples)
            lap.own_ms = int(data["own_ms"])
            lap.time_ms = int(data["time_ms"])
            if not 15000 <= lap.own_ms <= 3600000 or not 15000 <= lap.time_ms <= 3600000:
                raise ValueError("temps au tour")
            lap.valid = bool(data.get("valid", True))
            lap.reason = str(data.get("reason", ""))[:200]
            lap.time_source = str(data.get("time_source", "mesure"))[:20]
            lap.has_pos = bool(data.get("has_pos", True))
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            lap.meta = dict((k, meta.get(k)) for k in ("game_version", "session", "air_temp", "road_temp", "compound"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(400, "Fichier de tour invalide (%s)." % exc)
        rs = A.resample(lap.samples, lap.track_length, lap.own_ms / 1000.0)
        lap.meta["sectors"] = [round(v, 3) for v in A.sectors(rs)]
        combo_id, lap_id = self.storage.add_lap(lap, "import")
        return {"combo_id": combo_id, "lap_id": lap_id}

    def set_demo_car(self, car):
        if self.engine.source.kind != "demo" or car not in self._demo_cars():
            raise ApiError(400, "Voiture de démo inconnue.")
        self.engine.source.set_car(car)
        return {"ok": True}


_ROUTE_COMBO = re.compile(r"^/api/combos/(\d+)(?:/(track|coaching|reference|corners))?$")
_ROUTE_LAP = re.compile(r"^/api/laps/(\d+)(?:/(export|valid))?$")


class Handler(BaseHTTPRequestHandler):
    server_version = "IRMS/" + __version__
    app = None  # renseigne par make_server

    def log_message(self, fmt, *args):  # silence : la console reste lisible
        pass

    # -- utilitaires ------------------------------------------------------
    def _send(self, status, body, ctype, extra=None):
        headers = {"Content-Type": ctype, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                   "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                   "Content-Security-Policy": CSP}
        if extra:
            headers.update(extra)
        if len(body) > 2048 and "gzip" in self.headers.get("Accept-Encoding", "") \
                and ctype.split(";")[0] in ("application/json", "text/html", "text/css", "application/javascript",
                                            "text/javascript", "image/svg+xml"):
            body = gzip.compress(body, 5)
            headers["Content-Encoding"] = "gzip"
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, status=200):
        self._send(status, json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _is_local(self):
        return self.client_address[0] in LOOPBACK

    def _check_host(self):
        host = (self.headers.get("Host") or "").lower()
        name = host.rsplit(":", 1)[0] if not host.endswith("]") else host
        if name not in self.app.hosts:
            raise ApiError(403, "Hôte non autorisé.")

    def _check_write(self):
        if not self._is_local() and not self.app.lan_write:
            raise ApiError(403, "Lecture seule depuis le réseau local. Fais cette action sur le PC.")
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc.lower() != (self.headers.get("Host") or "").lower():
            raise ApiError(403, "Origine non autorisée.")

    def _body(self):
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            raise ApiError(415, "Content-Type application/json attendu.")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "Longueur invalide.")
        if length <= 0 or length > MAX_BODY:
            raise ApiError(413, "Corps de requête vide ou trop volumineux.")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            raise ApiError(400, "JSON invalide.")
        if not isinstance(data, dict):
            raise ApiError(400, "Objet JSON attendu.")
        return data

    def _dispatch(self, method):
        try:
            self._check_host()
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if method in ("POST", "DELETE"):
                self._check_write()
            if url.path.startswith("/api/"):
                self._api(method, url.path, query)
            elif method in ("GET", "HEAD"):
                self._static(url.path)
            else:
                raise ApiError(405, "Méthode non autorisée.")
        except ApiError as exc:
            self._json({"error": exc.message}, exc.status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as exc:  # erreur inattendue : jamais de trace vers le client
            try:
                self._json({"error": "Erreur interne : %s" % exc.__class__.__name__}, 500)
            except Exception:
                pass

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    # -- fichiers statiques ----------------------------------------------
    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.realpath(os.path.join(WEB_ROOT, path.lstrip("/")))
        root = os.path.realpath(WEB_ROOT)
        if not (full == root or full.startswith(root + os.sep)) or not os.path.isfile(full):
            raise ApiError(404, "Page introuvable.")
        # Table fixe : sous Windows, mimetypes lit le registre, qui est parfois faux.
        ctype = MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        with open(full, "rb") as handle:
            self._send(200, handle.read(), ctype)

    # -- API --------------------------------------------------------------
    def _api(self, method, path, query):
        app = self.app
        if method in ("GET", "HEAD"):
            if path == "/api/status":
                return self._json(app.status())
            if path == "/api/live":
                return self._stream()
            if path == "/api/live.json":
                return self._json(app.engine.live())
            if path == "/api/assistant":
                from .assistant_plan import build_plan
                raw = query.get("combo", [None])[0]
                if raw is not None and (not raw.isascii() or not raw.isdigit() or len(raw) > 18):
                    raise ApiError(400, "Identifiant de profil invalide.")
                combo_id = int(raw) if raw is not None else app.engine.combo_id
                if combo_id is None:
                    return self._json(build_plan({}, {}))
                analysis = app._analysis(combo_id)
                pedals = app.storage.setting("pedals", "position")
                return self._json(build_plan(analysis.overview(), analysis.coaching_view(pedals), pedals))
            if path == "/api/combos":
                return self._json(app.combos())
            if path == "/api/doctor":
                return self._json(doctor.report(app.engine))
            if path == "/api/settings":
                return self._json({"pedals": app.storage.setting("pedals", "position")})
            match = _ROUTE_COMBO.match(path)
            if match:
                analysis = app._analysis(int(match.group(1)))
                kind = match.group(2)
                if kind is None:
                    return self._json(analysis.overview())
                if kind == "track":
                    lap = query.get("lap", [None])[0]
                    return self._json(analysis.track_view(int(lap) if lap and lap.isdigit() else None))
                if kind == "coaching":
                    return self._json(analysis.coaching_view(app.storage.setting("pedals", "position")))
            match = _ROUTE_LAP.match(path)
            if match and match.group(2) == "export":
                fmt = query.get("format", ["json"])[0]
                body, ctype, name = app.export_lap(int(match.group(1)), fmt)
                return self._send(200, body, ctype, {"Content-Disposition": 'attachment; filename="%s"' % name})
            raise ApiError(404, "Adresse inconnue.")
        if method == "POST":
            data = self._body()
            if path == "/api/import":
                return self._json(app.import_lap(data))
            if path == "/api/settings":
                if data.get("pedals") not in ("position", "loadcell"):
                    raise ApiError(400, "Type de pédalier inconnu.")
                app.storage.set_setting("pedals", data["pedals"])
                return self._json({"ok": True})
            if path == "/api/demo/car":
                return self._json(app.set_demo_car(data.get("car")))
            match = _ROUTE_COMBO.match(path)
            if match and match.group(2) in ("reference", "corners"):
                combo_id = int(match.group(1))
                analysis = app._analysis(combo_id)
                if match.group(2) == "reference":
                    lap_id = data.get("lap_id")
                    if lap_id is not None and not any(lap["id"] == lap_id for lap in analysis.laps):
                        raise ApiError(404, "Tour introuvable dans ce profil.")
                    app.storage.set_reference(combo_id, lap_id)
                else:
                    names = data.get("names")
                    if not isinstance(names, dict) or len(names) > 200:
                        raise ApiError(400, "Noms de virages invalides.")
                    clean = {}
                    for key, value in names.items():
                        try:
                            float(key)
                        except ValueError:
                            raise ApiError(400, "Clé de virage invalide.")
                        if str(value).strip():
                            clean[str(key)] = str(value).strip()[:24]
                    app.storage.set_corner_names(combo_id, clean)
                app.engine._ref_wanted.set()
                return self._json({"ok": True})
            match = _ROUTE_LAP.match(path)
            if match and match.group(2) == "valid":
                if not app.storage.lap(int(match.group(1))):
                    raise ApiError(404, "Tour introuvable.")
                valid = bool(data.get("valid"))
                app.storage.set_lap_valid(int(match.group(1)), valid, "" if valid else "invalidé à la main")
                app.engine._ref_wanted.set()
                return self._json({"ok": True})
            raise ApiError(404, "Adresse inconnue.")
        if method == "DELETE":
            match = _ROUTE_LAP.match(path)
            if match and match.group(2) is None:
                lap_id = int(match.group(1))
                app.storage.delete_lap(lap_id)
                app.insights.forget_lap(lap_id)
                app.engine._ref_wanted.set()
                return self._json({"ok": True})
            match = _ROUTE_COMBO.match(path)
            if match and match.group(2) is None:
                combo_id = int(match.group(1))
                app.storage.delete_combo(combo_id)
                if app.engine.combo_id == combo_id:
                    app.engine.combo_id = None
                app.engine._ref_wanted.set()
                return self._json({"ok": True})
            raise ApiError(404, "Adresse inconnue.")
        raise ApiError(405, "Méthode non autorisée.")

    def _stream(self):
        """Flux Server-Sent Events : environ 20 images par seconde."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        last = None
        idle = 0
        try:
            while True:
                live = self.app.engine.live()
                if live.get("seq") != last:
                    last = live.get("seq")
                    idle = 0
                    data = json.dumps(live, ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(("data: %s\n\n" % data).encode("utf-8"))
                    self.wfile.flush()
                else:
                    idle += 1
                    if idle >= 100:  # battement de coeur toutes les 5 s
                        idle = 0
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass


def make_server(app, host):
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = ThreadingHTTPServer((host, app.port), handler)
    server.daemon_threads = True
    return server
