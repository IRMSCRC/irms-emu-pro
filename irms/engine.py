"""Boucle temps reel : lit la source, enregistre les tours, prepare le direct."""
import threading
import time

from . import analysis as A
from .frame import STATUS_LABELS, STATUS_LIVE
from .insights import Insights
from .recorder import Recorder

APPROACH_METRES = 200.0


def _interp(values, position):
    last = len(values) - 1
    if position <= 0:
        return values[0]
    if position >= last:
        return values[last]
    i = int(position)
    return values[i] + (position - i) * (values[i + 1] - values[i])


def next_cue(corners, dist, length):
    """Prochain repere de pilotage d'apres le tour de reference.

    Phases : ``gaz`` (accelere), ``approche`` (freinage dans moins de
    200 m), ``frein`` (zone de freinage de la reference), ``corde``
    (entre la fin du freinage et la reprise des gaz), ``passe`` (virage
    pris sans freiner).
    """
    if not corners:
        return None
    chosen = None
    previous = None
    offset = 0.0
    for index, corner in enumerate(corners):
        limit = corner["gas_on"] if corner["gas_on"] is not None else corner["apex"]
        if dist <= limit:
            chosen = corner
            previous = corners[index - 1] if index else None
            break
    if chosen is None:
        chosen = corners[0]
        previous = corners[-1]
        offset = length
    cue = {"name": chosen["name"], "dir": chosen["dir"], "min_speed": round(chosen["min_speed"]),
           "min_gear": chosen["min_gear"], "to_apex": round(chosen["apex"] + offset - dist),
           "to_brake": None, "braking": chosen["brake_on"] is not None}
    exiting = previous is not None and dist <= previous["seg_end"]
    if chosen["brake_on"] is not None:
        to_brake = chosen["brake_on"] + offset - dist
        if to_brake > 0:
            cue["to_brake"] = round(to_brake)
            near = APPROACH_METRES if not exiting else 50.0
            cue["phase"] = "approche" if to_brake <= near else "gaz"
        elif dist - offset <= chosen["brake_off"]:
            cue["phase"] = "frein"
        else:
            cue["phase"] = "corde"
    else:
        to_apex = chosen["apex"] + offset - dist
        cue["phase"] = "gaz" if to_apex > 120.0 else "passe"
    return cue


class Engine(object):
    def __init__(self, storage, source):
        self.storage = storage
        self.source = source
        self.insights = Insights(storage)
        self.recorder = Recorder(self._on_lap, self._on_combo)
        self.combo_id = None
        self._lock = threading.Lock()
        self._live = {"connected": False, "seq": 0}
        self._ref = None
        self._ref_revision = None
        self._ref_wanted = threading.Event()
        self._running = False
        self._threads = []
        self._event = None
        self._event_seq = 0
        self._seq = 0
        self.frames = 0
        self.last_frame = None

    # -- cycle de vie ---------------------------------------------------
    def start(self):
        self._running = True
        for target in (self._loop, self._ref_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self):
        self._running = False
        self._ref_wanted.set()
        for thread in self._threads:
            thread.join(2.0)
        self.recorder.flush()
        self.source.close()

    def _loop(self):
        pause = 0.01 if self.source.kind == "demo" else 0.004
        while self._running:
            try:
                self.step()
            except Exception as exc:  # la boucle ne doit jamais mourir
                self.source.state["message"] = "Erreur interne : %s" % exc
                time.sleep(0.5)
            time.sleep(pause)

    def _ref_loop(self):
        while self._running:
            self._ref_wanted.wait(1.0)
            self._ref_wanted.clear()
            if not self._running:
                break
            try:
                self.refresh_reference()
            except Exception:
                pass

    def refresh_reference(self):
        combo_id = self.combo_id
        revision = self.storage.revision
        if combo_id is None:
            self._ref = None
            self._ref_revision = None
            return
        if self._ref_revision == (combo_id, revision):
            return
        self._ref = self.insights.combo(combo_id).live_reference()
        self._ref_revision = (combo_id, revision)

    # -- evenements de l'enregistreur -------------------------------------
    def _on_combo(self, combo, length):
        self.combo_id = self.storage.find_combo(combo[0], combo[1], combo[2], length)
        self._ref = None
        self._ref_revision = None
        self._ref_wanted.set()

    def _on_lap(self, lap):
        rs = A.resample(lap.samples, lap.track_length, lap.own_ms / 1000.0)
        lap.meta["sectors"] = [round(v, 3) for v in A.sectors(rs)]
        combo_id, lap_id = self.storage.add_lap(lap, self.source.kind)
        self.combo_id = combo_id
        self._event_seq += 1
        self._event = {"seq": self._event_seq, "lap_id": lap_id, "combo_id": combo_id, "time_ms": lap.time_ms,
                       "valid": lap.valid, "reason": lap.reason}
        self._ref_wanted.set()

    # -- une iteration ----------------------------------------------------
    def step(self):
        frame = self.source.poll()
        state = self.source.state
        if frame is None:
            with self._lock:
                self._seq += 1
                self._live = {"seq": self._seq, "connected": False, "source": state["source"],
                              "message": state["message"], "event": self._event,
                              "revision": self.storage.revision}
            return None
        self.frames += 1
        self.last_frame = frame
        self.recorder.feed(frame)
        live = frame.status == STATUS_LIVE
        length = float(round(frame.track_length))
        dist = max(0.0, min(1.0, frame.npos)) * length
        payload = {
            "connected": True, "source": state["source"], "message": state["message"],
            "status": frame.status, "status_label": STATUS_LABELS.get(frame.status, "données incohérentes"),
            "car": frame.car, "track": frame.track, "config": frame.config, "length": length,
            "combo_id": self.combo_id, "speed": round(frame.speed, 1), "gear": frame.gear, "rpm": int(frame.rpm),
            "max_rpm": int(frame.max_rpm), "gas": round(frame.gas, 3), "brake": round(frame.brake, 3),
            "steer": round(frame.steer, 3), "dist": round(dist, 1), "npos": round(frame.npos, 5),
            "lap_time_ms": int(frame.lap_time_ms), "last_lap_ms": int(frame.last_lap_ms),
            "valid": bool(frame.valid) and not self.recorder.current_reason,
            "reason": self.recorder.current_reason, "in_pit": bool(frame.in_pit),
            "recording": self.recorder.lap_in_progress and live, "abs": frame.abs, "tc": frame.tc,
            "delta": None, "ref_speed": None, "cue": None, "ref_ms": None, "event": self._event,
            "revision": self.storage.revision, "problems": state["problems"],
            "suspect": state.get("suspect", []),
        }
        ref = self._ref
        if live and ref and ref["combo_id"] == self.combo_id:
            position = dist / ref["step"]
            payload["ref_ms"] = ref["time_ms"]
            payload["ref_speed"] = round(_interp(ref["speed"], position), 1)
            if self.recorder.lap_seconds is not None:
                payload["delta"] = round(self.recorder.lap_seconds - _interp(ref["t"], position), 3)
            payload["cue"] = next_cue(ref["corners"], dist, length)
        with self._lock:
            self._seq += 1
            payload["seq"] = self._seq
            self._live = payload
        return payload

    def live(self):
        with self._lock:
            return self._live


def seed_demo(storage, laps_per_car=12):
    """Remplit la base de demo avec des tours simules pour chaque voiture."""
    import datetime

    from .simulator import CARS, DemoSource

    base = datetime.datetime.now().replace(microsecond=0) - datetime.timedelta(hours=2)
    for car_index, car in enumerate(sorted(CARS)):
        source = DemoSource(car, seed=1)
        count = [0]
        stamp = [base + datetime.timedelta(minutes=45 * car_index)]

        def on_lap(lap, count=count, stamp=stamp):
            rs = A.resample(lap.samples, lap.track_length, lap.own_ms / 1000.0)
            lap.meta["sectors"] = [round(v, 3) for v in A.sectors(rs)]
            stamp[0] += datetime.timedelta(milliseconds=lap.own_ms)
            storage.add_lap(lap, "demo", stamp[0].replace(microsecond=0).isoformat(sep=" "))
            count[0] += 1

        recorder = Recorder(on_lap)
        guard = 0
        while count[0] < laps_per_car and guard < 2000000:
            recorder.feed(source.advance(0.02))
            guard += 1
        recorder.flush()
