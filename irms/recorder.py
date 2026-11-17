"""Decoupe le flux de telemetrie en tours et juge leur validite.

Regles principales :

* un tour commence et finit au passage de la position normalisee de ~1 a ~0 ;
* le tour en cours quand l'application demarre (ou apres un retour au
  stand) est incomplet : il n'est jamais enregistre ;
* changer de voiture, de circuit ou de trace ouvre un nouveau profil ;
* le temps officiel du jeu est utilise des qu'il est publie ; sinon le
  temps mesure par l'application (interpolation au passage de la ligne).
"""
from .frame import STATUS_LIVE, STATUS_PAUSE

CHANNELS = ("d", "t", "speed", "gas", "brake", "steer", "gear", "rpm", "glat", "x", "z")
OFFICIAL_WAIT = 2.5      # secondes d'attente du temps officiel apres la ligne
OFFICIAL_TOLERANCE = 1.5  # ecart maximal accepte entre temps officiel et mesure
MIN_LAP_SECONDS = 15.0


class LapRecord(object):
    def __init__(self, combo, track_length, samples):
        self.car, self.track, self.config = combo
        self.track_length = track_length
        self.samples = samples
        self.own_ms = 0
        self.time_ms = 0
        self.time_source = "mesure"
        self.valid = True
        self.reason = ""
        self.has_pos = True
        self.meta = {}

    @property
    def n(self):
        return len(self.samples["d"])


class Recorder(object):
    def __init__(self, on_lap, on_combo=None):
        self.on_lap = on_lap
        self.on_combo = on_combo
        self.combo = None
        self.track_length = 0.0
        self._prev = None
        self._pending = None
        self._reset_lap(False)
        self._t_offset = 0.0
        self._last_live_t = None
        self.lap_seconds = None

    # -- etat -----------------------------------------------------------
    def _reset_lap(self, complete, start_t=0.0):
        self._samples = dict((name, []) for name in CHANNELS)
        self._complete = complete
        self._start_t = start_t
        self._reason = ""
        self._has_pos = True
        self._max_gap = 0.0
        self._meta = {}

    @property
    def lap_in_progress(self):
        return self._complete

    @property
    def current_reason(self):
        return self._reason

    def _invalidate(self, reason):
        if not self._reason:
            self._reason = reason

    def flush(self):
        """Termine un tour en attente de temps officiel (arret, changement)."""
        if self._pending:
            lap = self._pending[0]
            self._pending = None
            self._emit(lap)

    def _emit(self, lap):
        if lap.own_ms < MIN_LAP_SECONDS * 1000 or lap.n < 40:
            return
        self.on_lap(lap)

    # -- flux -----------------------------------------------------------
    def feed(self, frame):
        if frame.status != STATUS_LIVE:
            if frame.status != STATUS_PAUSE:
                # replay, menu, donnees incoherentes : le tour en cours est perdu
                self.flush()
                self._reset_lap(False)
                self._prev = None
            return
        if frame.ai:
            self.flush()
            self._reset_lap(False)
            self._prev = None
            return
        prev = self._prev
        if prev is not None and frame.packet == prev.packet:
            return
        combo = frame.combo()
        length = float(round(frame.track_length))
        if combo != self.combo or length != self.track_length:
            self.flush()
            self.combo = combo
            self.track_length = length
            self._reset_lap(False)
            prev = None
            if self.on_combo:
                self.on_combo(combo, length)
        # temps propre, pauses retirees
        if self._last_live_t is not None:
            gap = frame.t - self._last_live_t
            if gap > 1.0:
                self._t_offset += gap
                self._invalidate("interruption (pause ou blocage de plus d'une seconde)")
        self._last_live_t = frame.t
        now = frame.t - self._t_offset
        self.lap_seconds = (now - self._start_t) if self._complete else None

        if self._pending:
            lap, last_before, deadline = self._pending
            official = frame.last_lap_ms
            if official and official > 0 and official != last_before:
                if abs(official - lap.own_ms) <= OFFICIAL_TOLERANCE * 1000:
                    lap.time_ms = int(official)
                    lap.time_source = "jeu"
                self._pending = None
                self._emit(lap)
            elif now >= deadline:
                self._pending = None
                self._emit(lap)

        if prev is None:
            self._prev = frame
            self._prev_now = now
            return

        length = self.track_length
        wrapped = prev.npos > 0.8 and frame.npos < 0.2
        if wrapped:
            ahead = max(0.0, 1.0 - prev.npos)
            total = ahead + max(0.0, frame.npos)
            fraction = ahead / total if total > 0 else 1.0
            cross = self._prev_now + fraction * (now - self._prev_now)
            if self._complete and self._samples["d"]:
                self.flush()
                lap = self._finish(cross)
                self._pending = (lap, prev.last_lap_ms, now + OFFICIAL_WAIT)
                # le temps officiel peut deja etre publie sur cette meme image
                official = frame.last_lap_ms
                if official and official > 0 and official != prev.last_lap_ms:
                    if abs(official - lap.own_ms) <= OFFICIAL_TOLERANCE * 1000:
                        lap.time_ms = int(official)
                        lap.time_source = "jeu"
                    self._pending = None
                    self._emit(lap)
            self._reset_lap(True, cross)
            self.lap_seconds = now - cross
        else:
            moved = (frame.npos - prev.npos) * length
            dt = max(1e-3, now - self._prev_now)
            if moved < -30.0:
                # retour au stand, teleportation, marche arriere prolongee
                self._reset_lap(False)
                self.lap_seconds = None
                self._prev = frame
                self._prev_now = now
                return
            if moved > max(60.0, frame.speed / 3.6 * dt * 3.0 + 20.0):
                self._invalidate("saut de position (téléportation ou perte de données)")

        if self._complete:
            if frame.in_pit:
                self._invalidate("passage par les stands")
            if not frame.valid:
                self._invalidate("invalidé par le jeu (limites de piste)")
            s = self._samples
            d = max(0.0, min(1.0, frame.npos)) * length
            t = now - self._start_t
            if not s["d"] or d - s["d"][-1] >= 0.2:
                if s["d"]:
                    self._max_gap = max(self._max_gap, d - s["d"][-1])
                else:
                    self._meta = {"game_version": frame.game_version, "session": frame.session,
                                  "air_temp": frame.air_temp, "road_temp": frame.road_temp,
                                  "compound": frame.compound}
                s["d"].append(d)
                s["t"].append(t)
                s["speed"].append(frame.speed)
                s["gas"].append(frame.gas)
                s["brake"].append(frame.brake)
                s["steer"].append(frame.steer)
                s["gear"].append(float(frame.gear))
                s["rpm"].append(float(frame.rpm))
                s["glat"].append(frame.glat)
                s["x"].append(frame.x)
                s["z"].append(frame.z)
                if not frame.has_pos:
                    self._has_pos = False
        self._prev = frame
        self._prev_now = now

    def _finish(self, cross):
        lap = LapRecord(self.combo, self.track_length, self._samples)
        lap.own_ms = int(round((cross - self._start_t) * 1000))
        lap.time_ms = lap.own_ms
        lap.has_pos = self._has_pos
        lap.meta = self._meta
        s = self._samples
        length = self.track_length
        if s["d"]:
            gap = max(self._max_gap, s["d"][0], length - s["d"][-1])
            if gap > max(80.0, 0.03 * length):
                self._invalidate("données incomplètes (trou de %d m)" % gap)
        lap.valid = not self._reason
        lap.reason = self._reason
        return lap
