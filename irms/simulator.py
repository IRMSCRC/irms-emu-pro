"""Telemetrie synthetique : mode demo et donnees de test.

Rien ici ne pretend reproduire un vrai circuit ou une vraie voiture. Le but
est de fournir des tours plausibles (freinages, cordes, reprises des gaz,
erreurs recurrentes ou ponctuelles) pour essayer l'application sans le jeu
et pour tester toute la chaine d'analyse de facon reproductible.
"""
import bisect
import math
import random
import time

from .frame import Frame, STATUS_LIVE

G = 9.81
DEMO_TRACK = "Circuit de démonstration"
DEMO_CONFIG = "Grand Prix"

# Sommets du trace (x, z, rayon du virage) en metres, sens horaire.
_VERTICES = [
    (-350, 0, 70), (700, 0, 55), (640, 260, 80), (880, 400, 40), (760, 640, 150),
    (300, 700, 70), (150, 480, 60), (-250, 520, 30), (-100, 330, 60), (-420, 200, 50),
]

CARS = {
    "Démo GT3": dict(a_lat=17.5, a_brake=15.5, a_acc=7.5, vtop=74.0, gears=6, max_rpm=8200,
                     weak={2: ("brake", 0.66, 0.85), 6: ("throttle", 0.50, 0.75)}),
    "Démo Roadster Cup": dict(a_lat=11.5, a_brake=10.0, a_acc=3.4, vtop=52.0, gears=6, max_rpm=7200,
                              weak={0: ("apex", 0.90, 0.8), 4: ("lift", 0.0, 0.7)}),
}


def _fillet_polygon(vertices, step=0.5):
    """Polygone aux coins arrondis : lignes droites reliees par des arcs."""
    n = len(vertices)
    arcs = []
    for i in range(n):
        ax, az = vertices[i - 1][:2]
        bx, bz, radius = vertices[i]
        cx, cz = vertices[(i + 1) % n][:2]
        ux, uz = ax - bx, az - bz
        lu = math.hypot(ux, uz)
        ux, uz = ux / lu, uz / lu
        wx, wz = cx - bx, cz - bz
        lw = math.hypot(wx, wz)
        wx, wz = wx / lw, wz / lw
        theta = math.acos(max(-1.0, min(1.0, ux * wx + uz * wz)))
        tangent = min(radius / math.tan(theta / 2.0), 0.45 * lu, 0.45 * lw)
        radius = tangent * math.tan(theta / 2.0)
        p1 = (bx + ux * tangent, bz + uz * tangent)
        p2 = (bx + wx * tangent, bz + wz * tangent)
        mx, mz = ux + wx, uz + wz
        lm = math.hypot(mx, mz)
        reach = radius / math.sin(theta / 2.0)
        center = (bx + mx / lm * reach, bz + mz / lm * reach)
        a1 = math.atan2(p1[1] - center[1], p1[0] - center[0])
        a2 = math.atan2(p2[1] - center[1], p2[0] - center[0])
        sweep = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        arcs.append((p1, p2, center, radius, a1, sweep))
    out = []
    for i in range(n):
        p1, _, center, radius, a1, sweep = arcs[i]
        q = arcs[i - 1][1]
        count = max(1, int(math.hypot(p1[0] - q[0], p1[1] - q[1]) / step))
        for j in range(count):
            out.append((q[0] + (p1[0] - q[0]) * j / count, q[1] + (p1[1] - q[1]) * j / count))
        count = max(1, int(abs(sweep) * radius / step))
        for j in range(count):
            angle = a1 + sweep * j / count
            out.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
    return out


def _smooth_cyclic(values, half):
    n = len(values)
    window = 2 * half + 1
    total = sum(values[(i - half) % n] for i in range(window))
    out = [0.0] * n
    for i in range(n):
        out[i] = total / window
        total += values[(i + half + 1) % n] - values[(i - half) % n]
    return out


class DemoTrack(object):
    """Trace ferme, re-echantillonne tous les metres."""

    def __init__(self, offset=(-1200.0, 850.0)):
        dense = _fillet_polygon(_VERTICES)
        # ligne de depart au milieu de la ligne droite principale
        start = min(range(len(dense)), key=lambda i: abs(dense[i][0] - 150.0) + 1000.0 * abs(dense[i][1]))
        dense = dense[start:] + dense[:start]
        dense.append(dense[0])
        cum = [0.0]
        for a, b in zip(dense, dense[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        length = round(cum[-1])
        scale = length / cum[-1]
        n = int(round(length))
        self.n = n
        self.ds = length / n
        self.length = length
        xs, zs = [], []
        j = 0
        for i in range(n):
            target = i * self.ds / scale
            while cum[j + 1] < target:
                j += 1
            f = (target - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
            xs.append((dense[j][0] + f * (dense[j + 1][0] - dense[j][0])) * scale + offset[0])
            zs.append((dense[j][1] + f * (dense[j + 1][1] - dense[j][1])) * scale + offset[1])
        self.x, self.z = xs, zs
        heading = []
        for i in range(n):
            heading.append(math.atan2(zs[(i + 1) % n] - zs[i - 1], xs[(i + 1) % n] - xs[i - 1]))
        kappa = []
        for i in range(n):
            d = heading[(i + 1) % n] - heading[i - 1]
            d = (d + math.pi) % (2 * math.pi) - math.pi
            kappa.append(d / (2 * self.ds))
        self.kappa = _smooth_cyclic(_smooth_cyclic(kappa, 7), 7)


class LapProfile(object):
    """Un tour simule : toutes les voies sur une grille d'un metre."""

    __slots__ = ("v", "t", "gas", "brake", "steer", "gear", "rpm", "glat", "glon", "time", "valid_until")


class DemoCarModel(object):
    def __init__(self, name, track, seed=1):
        self.name = name
        self.track = track
        self.p = CARS[name]
        self.rng = random.Random("%s-%s" % (name, seed))
        self.lap_index = 0
        p = self.p
        n = track.n
        self.v_lim = [min(p["vtop"], math.sqrt(p["a_lat"] / max(abs(k), 1e-6))) for k in track.kappa]
        # sommets : minima locaux marques de la vitesse limite
        apexes = []
        for i in range(n):
            v = self.v_lim[i]
            if v < 0.9 * p["vtop"] and v <= min(self.v_lim[(i + d) % n] for d in range(-25, 26)):
                if not apexes or (i - apexes[-1]) > 60:
                    apexes.append(i)
        self.apexes = apexes

    def _accel(self, v):
        p = self.p
        return max(0.0, p["a_acc"] * (1.0 - (v / p["vtop"]) ** 2)) + 0.05

    def build_lap(self):
        p, track, rng = self.p, self.track, self.rng
        n, ds = track.n, track.ds
        k = self.lap_index
        self.lap_index += 1
        progress = min(1.0, k / 12.0)  # le pilote virtuel progresse un peu
        noise = 1.0 - 0.6 * progress
        v_lim = list(self.v_lim)
        brake_f = [1.0] * n
        acc_f = [1.0] * n
        for j, apex in enumerate(self.apexes):
            f_apex = 1.0 - rng.uniform(0.0, 0.035) * noise
            f_brake = 1.0 - rng.uniform(0.0, 0.10) * noise
            f_acc = 1.0 - rng.uniform(0.0, 0.10) * noise
            lift = False
            weak = p["weak"].get(j)
            if weak and rng.random() < weak[2]:
                kind, amount = weak[0], weak[1]
                if kind == "brake":
                    f_brake = amount + rng.uniform(-0.04, 0.04)
                elif kind == "throttle":
                    f_acc = amount + rng.uniform(-0.05, 0.05)
                elif kind == "apex":
                    f_apex = amount + rng.uniform(-0.015, 0.015)
                elif kind == "lift":
                    lift = True
            elif rng.random() < 0.05:
                f_apex = 0.88  # grosse erreur ponctuelle
            for d in range(-45, 46):
                w = 1.0 - abs(d) / 46.0
                i = (apex + d) % n
                v_lim[i] = v_lim[i] * (1.0 - (1.0 - f_apex) * w)
            for d in range(0, 260):
                brake_f[(apex - d) % n] = f_brake
            for d in range(0, 130):
                acc_f[(apex + d) % n] = f_acc
            if lift:
                for d in range(55, 85):
                    acc_f[(apex + d) % n] = -0.35
        v = list(v_lim)
        for _ in range(2):
            for i in range(n - 1, -1, -1):
                nxt = v[(i + 1) % n]
                v[i] = min(v[i], math.sqrt(nxt * nxt + 2.0 * p["a_brake"] * brake_f[i] * ds))
        for _ in range(2):
            for i in range(n):
                a = self._accel(v[i]) * acc_f[i]
                if a < 0:
                    a = -0.5  # pied leve : frein moteur seul
                v[(i + 1) % n] = min(v[(i + 1) % n], math.sqrt(max(9.0, v[i] * v[i] + 2.0 * a * ds)))
        lap = LapProfile()
        gas, brake, glon = [0.0] * n, [0.0] * n, [0.0] * n
        for i in range(n):
            a = (v[(i + 1) % n] ** 2 - v[i] ** 2) / (2.0 * ds)
            glon[i] = a / G
            if a < -0.6:
                brake[i] = min(1.0, max(0.06, -a / p["a_brake"]))
            elif a > 0.15:
                gas[i] = min(1.0, max(0.25, a / self._accel(v[i])))
            elif v[i] > 0.985 * p["vtop"]:
                gas[i] = 1.0
            else:
                gas[i] = 0.0 if acc_f[i] < 0 else 0.28
        lap.v = v
        lap.gas = _smooth_cyclic(gas, 4)
        lap.brake = _smooth_cyclic(brake, 3)
        for i in range(n):
            if lap.brake[i] > 0.04:
                lap.gas[i] = 0.0
        lap.glon = glon
        lap.steer = [max(-1.0, min(1.0, kk * 24.0)) for kk in track.kappa]
        lap.glat = [v[i] * v[i] * track.kappa[i] / G for i in range(n)]
        gears, max_rpm = p["gears"], p["max_rpm"]
        lap.gear, lap.rpm = [], []
        for i in range(n):
            ratio = v[i] / p["vtop"]
            gear = min(gears, max(1, int(ratio ** 1.25 * gears) + 1))
            lo = ((gear - 1) / float(gears)) ** 0.8 * p["vtop"]
            hi = (gear / float(gears)) ** 0.8 * p["vtop"]
            frac = max(0.0, min(1.0, (v[i] - lo) / max(1.0, hi - lo)))
            lap.gear.append(gear)
            lap.rpm.append(int(max_rpm * (0.56 + 0.42 * frac)))
        t = [0.0] * (n + 1)
        for i in range(n):
            t[i + 1] = t[i] + ds / (0.5 * (v[i] + v[(i + 1) % n]))
        lap.t = t
        lap.time = t[n]
        # environ un tour sur dix est invalide (sortie de piste simulee)
        lap.valid_until = rng.uniform(0.2, 0.9) * lap.time if rng.random() < 0.10 else None
        return lap


class DemoSource(object):
    """Source de telemetrie simulee. Meme interface que EvoSource."""

    kind = "demo"

    def __init__(self, car="Démo GT3", speed=1.0, seed=1, clock=time.monotonic, start_npos=0.72):
        self.track = DemoTrack()
        self.model = DemoCarModel(car, self.track, seed)
        self.speed = speed
        self._clock = clock
        self._last_clock = None
        self._lap = self.model.build_lap()
        self._lap_t = self._lap.t[int(start_npos * self.track.n)]
        self._lap_count = 0
        self._last_lap_ms = 0
        self._best_lap_ms = 0
        self._packet = 0
        self._sim_time = 0.0
        self._outlap = True
        self.state = {
            "source": "demo", "platform_ok": True, "connected": True, "maps": {}, "problems": [], "suspect": [],
            "stale": False, "status": STATUS_LIVE, "game_version": "démo", "sm_version": "",
            "inputs": "simulateur", "position": "simulateur",
            "message": "Mode démo : données simulées, aucun lien avec le jeu.",
        }

    def set_car(self, car):
        self.model = DemoCarModel(car, self.track, 1)
        self._lap = self.model.build_lap()
        self._lap_t = self._lap.t[int(0.72 * self.track.n)]
        self._lap_count = 0
        self._last_lap_ms = 0
        self._best_lap_ms = 0
        self._outlap = True

    def advance(self, dt):
        """Avance la simulation de ``dt`` secondes et rend la Frame."""
        self._sim_time += dt
        self._lap_t += dt
        while self._lap_t >= self._lap.time:
            self._lap_t -= self._lap.time
            if not self._outlap:
                self._last_lap_ms = int(round(self._lap.time * 1000))
                if self._lap.valid_until is None and (not self._best_lap_ms or self._last_lap_ms < self._best_lap_ms):
                    self._best_lap_ms = self._last_lap_ms
            self._outlap = False
            self._lap_count += 1
            self._lap = self.model.build_lap()
        lap, track = self._lap, self.track
        n = track.n
        i = min(n - 1, max(0, bisect.bisect_right(lap.t, self._lap_t) - 1))
        f = (self._lap_t - lap.t[i]) / max(1e-9, lap.t[i + 1] - lap.t[i])
        j = (i + 1) % n

        def mix(arr):
            return arr[i] + f * (arr[j] - arr[i])

        self._packet += 1
        frame = Frame(t=self._sim_time, packet=self._packet, status=STATUS_LIVE)
        frame.car = self.model.name
        frame.track = DEMO_TRACK
        frame.config = DEMO_CONFIG
        frame.track_length = track.length
        frame.npos = (i + f) / n
        frame.lap_time_ms = int(self._lap_t * 1000)
        frame.last_lap_ms = self._last_lap_ms
        frame.best_lap_ms = self._best_lap_ms
        frame.lap_count = self._lap_count
        frame.valid = lap.valid_until is None or self._lap_t < lap.valid_until
        frame.speed = mix(lap.v) * 3.6
        frame.gas = max(0.0, min(1.0, mix(lap.gas)))
        frame.brake = max(0.0, min(1.0, mix(lap.brake)))
        frame.steer = mix(lap.steer)
        frame.gear = lap.gear[i]
        frame.rpm = lap.rpm[i]
        frame.max_rpm = self.model.p["max_rpm"]
        frame.glat = mix(lap.glat)
        frame.glon = lap.glon[i]
        frame.x = mix(track.x) if j else track.x[i]
        frame.z = mix(track.z) if j else track.z[i]
        frame.has_pos = True
        frame.abs = frame.brake > 0.97
        frame.fuel = 40.0
        frame.session = "Démo"
        frame.game_version = "démo"
        frame.air_temp = 22.0
        frame.road_temp = 31.0
        frame.compound = "Démo"
        return frame

    def poll(self):
        now = self._clock()
        if self._last_clock is None:
            self._last_clock = now
        dt = min(0.25, max(0.0, now - self._last_clock)) * self.speed
        self._last_clock = now
        return self.advance(dt)

    def close(self):
        pass


def encode_pages(frame, player_index=2, cars=6, version="0.6.2"):
    """Fabrique les trois pages memoire EVO a partir d'une Frame.

    Sert aux tests (aller-retour codage/decodage) et aux fausses zones
    memoire. Retourne (physics, graphics, static) en ``bytes``.
    """
    from .evo_reader import GRAPHICS, PHYSICS, STATIC

    ids = [[1000 + i, 9000000000000000000 + i] for i in range(60)]
    coords = [[0.0, 0.0, 0.0] for _ in range(60)]
    for i in range(cars):
        coords[i] = [frame.x + 7.0 * (i - player_index), 12.5, frame.z - 5.0 * (i - player_index)]
    physics = PHYSICS.encode({
        "packetId": frame.packet, "gas": frame.gas, "brake": frame.brake, "gear": frame.gear + 1,
        "rpms": int(frame.rpm), "steerAngle": frame.steer, "speedKmh": frame.speed,
        "accG": [frame.glat, 0.0, frame.glon], "currentMaxRpm": int(frame.max_rpm),
        "airTemp": frame.air_temp or 0.0, "roadTemp": frame.road_temp or 0.0,
        "tyreContactPoint": [[frame.x + dx, 0.0, frame.z + dz] for dx, dz in ((-0.8, 1.3), (0.8, 1.3), (-0.8, -1.3), (0.8, -1.3))],
    }, 4096)
    graphics = GRAPHICS.encode({
        "packetId": frame.packet, "status": frame.status,
        "player_car_id_a": ids[player_index][0], "player_car_id_b": ids[player_index][1],
        "focused_car_id_a": ids[player_index][0], "focused_car_id_b": ids[player_index][1],
        "rpm": int(frame.rpm), "display_speed_kmh": int(round(frame.speed)), "gear_int": frame.gear + 1,
        "gas_percent": frame.gas, "brake_percent": frame.brake, "steering_percent": frame.steer,
        "g_forces_x": frame.glat, "g_forces_y": frame.glon, "npos": frame.npos,
        "current_lap_time_ms": int(frame.lap_time_ms), "last_laptime_ms": int(frame.last_lap_ms),
        "best_laptime_ms": int(frame.best_lap_ms), "total_lap_count": int(frame.lap_count),
        "is_valid_lap": bool(frame.valid), "is_in_pit_lane": bool(frame.in_pit), "car_location": 1 if frame.in_pit else 4,
        "car_model": frame.car, "car_coordinates": coords, "car_ids": ids, "active_cars": cars,
        "total_drivers": cars, "fuel_liter_current_quantity": frame.fuel, "abs_active": bool(frame.abs),
        "tyre_lf.tyre_compound_front": frame.compound,
    }, 8192)
    static = STATIC.encode({
        "sm_version": "1.0", "ac_evo_version": version, "session_name": frame.session or "Practice",
        "track": frame.track, "track_configuration": frame.config, "track_length_m": frame.track_length,
        "starting_ambient_temperature_c": frame.air_temp or 0.0,
        "starting_ground_temperature_c": frame.road_temp or 0.0,
    }, 4096)
    return bytes(physics), bytes(graphics), bytes(static)
