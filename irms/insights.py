"""Assemble stockage, analyse et conseils pour l'interface et le direct."""
import threading

from . import analysis as A
from . import coaching

ANALYSED = 30
RS_CACHE = 48


def _r(values, digits):
    return [round(v, digits) for v in values]


class ComboAnalysis(object):
    """Etat d'analyse d'un profil voiture + circuit a un instant donne."""

    def __init__(self, insights, combo_id):
        store = insights.storage
        self.combo = store.combo(combo_id)
        self.laps = store.laps(combo_id) if self.combo else []
        self.length = self.combo["track_length"] if self.combo else 0.0
        self.valid = [lap for lap in self.laps if lap["valid"]]
        self.best = min(self.valid, key=lambda lap: lap["time_ms"]) if self.valid else None
        by_id = dict((lap["id"], lap) for lap in self.laps)
        pinned = by_id.get(self.combo["ref_lap_id"]) if self.combo else None
        self.ref_pinned = bool(pinned)
        self.ref_provisional = False
        self.ref = pinned or self.best
        if self.ref is None and self.laps:
            self.ref = min(self.laps, key=lambda lap: lap["time_ms"])
            self.ref_provisional = True
        self.ref_rs = None
        self.geo = None
        self.corners = []
        self.metrics = {}
        self.best_seg = []
        self.theoretical_ms = None
        self._insights = insights
        if self.ref is None:
            return
        self.ref_rs = insights.resampled(self.ref["id"])
        self.step = self.ref_rs["step"]
        self.geo = A.geometry(self.ref_rs, bool(self.ref["has_pos"]))
        self.corners = A.detect_corners(self.ref_rs, self.geo)
        names = {}
        try:
            import json
            names = json.loads(self.combo["corner_names"] or "{}")
        except ValueError:
            names = {}
        for corner in self.corners:
            apex_m = corner["apex"] * self.step
            for key, label in names.items():
                try:
                    if abs(float(key) - apex_m) <= 40.0 and label:
                        corner["name"] = label
                except ValueError:
                    pass
        chosen = self.valid[-ANALYSED:]
        ids = set(lap["id"] for lap in chosen)
        for extra in (self.ref, self.best):
            if extra and extra["id"] not in ids:
                chosen.append(extra)
                ids.add(extra["id"])
        self.analysed = chosen
        for lap in chosen:
            self.metrics[lap["id"]] = A.lap_metrics(insights.resampled(lap["id"]), self.corners)
        pool = [lap for lap in chosen if lap["valid"]]
        for index in range(len(self.corners)):
            if pool:
                best = min(pool, key=lambda lap: self.metrics[lap["id"]][index]["time"])
                self.best_seg.append((self.metrics[best["id"]][index]["time"], best["id"]))
            else:
                self.best_seg.append((self.metrics[self.ref["id"]][index]["time"], self.ref["id"]))
        if pool and self.corners:
            self.theoretical_ms = int(round(1000 * sum(item[0] for item in self.best_seg)))
            if self.best and self.theoretical_ms > self.best["time_ms"]:
                self.theoretical_ms = self.best["time_ms"]

    # -- vues -------------------------------------------------------------
    def overview(self):
        if not self.combo:
            return None
        best_ms = self.best["time_ms"] if self.best else None
        times = [lap["time_ms"] for lap in self.valid]
        recent = times[-coaching.RECENT:]
        laps = []
        best_sectors = None
        for number, lap in enumerate(self.laps, 1):
            sect = lap["meta"].get("sectors")
            if lap["valid"] and sect:
                best_sectors = sect if best_sectors is None else [min(a, b) for a, b in zip(best_sectors, sect)]
            laps.append({
                "id": lap["id"], "no": number, "created_at": lap["created_at"], "time_ms": lap["time_ms"],
                "valid": bool(lap["valid"]), "reason": lap["reason"], "time_source": lap["time_source"],
                "source": lap["source"], "sectors": sect, "has_pos": bool(lap["has_pos"]),
                "gap_ms": None if best_ms is None else lap["time_ms"] - best_ms,
                "is_ref": bool(self.ref and lap["id"] == self.ref["id"]),
                "is_best": bool(self.best and lap["id"] == self.best["id"]),
                "conditions": dict((k, lap["meta"].get(k)) for k in ("air_temp", "road_temp", "compound", "session",
                                                                    "game_version")),
            })
        return {
            "combo": dict((k, self.combo[k]) for k in ("id", "car", "track", "config", "track_length")),
            "laps": laps,
            "best_ms": best_ms,
            "theoretical_ms": self.theoretical_ms,
            "best_sectors": best_sectors,
            "ref_lap_id": self.ref["id"] if self.ref else None,
            "ref_pinned": self.ref_pinned,
            "ref_provisional": self.ref_provisional,
            "stats": {
                "total": len(self.laps), "valid": len(self.valid),
                "mean_ms": A.mean(recent) if recent else None,
                "stdev_ms": A.stdev(recent) if len(recent) >= 2 else None,
                "recent": len(recent),
            },
            "profile": A.car_profile(self.ref_rs) if self.ref_rs else None,
            "corners": len(self.corners),
        }

    def _corner_view(self, metrics):
        step = self.step
        out = {}
        for key in ("brake_on", "brake_off", "gas_on", "full_on", "lift_on", "min_at"):
            out[key] = None if metrics[key] is None else round(metrics[key] * step, 1)
        for key in ("min_speed", "entry_speed", "exit_speed", "brake_peak", "time", "coast", "trail"):
            out[key] = round(metrics[key], 3)
        out["min_gear"] = metrics["min_gear"]
        out["lifts"] = metrics["lifts"]
        return out

    def track_view(self, lap_id=None):
        if not self.ref_rs:
            return {"ready": False}
        insights = self._insights
        ref_rs = self.ref_rs
        n, step = ref_rs["n"], self.step
        lap = None
        if lap_id and lap_id != self.ref["id"]:
            lap = next((item for item in self.laps if item["id"] == lap_id), None)
        lap_rs = insights.resampled(lap["id"]) if lap else None
        lap_metrics = None
        if lap:
            lap_metrics = self.metrics.get(lap["id"]) or A.lap_metrics(lap_rs, self.corners)
        ref_metrics = self.metrics[self.ref["id"]]

        def channels(rs):
            return {"speed": _r(rs["speed"], 1), "gas": _r(rs["gas"], 2), "brake": _r(rs["brake"], 2),
                    "gear": [int(round(g)) for g in rs["gear"]], "t": _r(rs["t"], 3), "steer": _r(rs["steer"], 3)}

        corners = []
        for index, corner in enumerate(self.corners):
            item = {
                "index": index, "name": corner["name"], "dir": corner["dir"], "kind": corner["kind"],
                "angle": None if corner["angle"] is None else round(corner["angle"]),
                "start": round(corner["start"] * step, 1), "apex": round(corner["apex"] * step, 1),
                "end": round(corner["end"] * step, 1), "seg_start": round(corner["seg_start"] * step, 1),
                "seg_end": round(corner["seg_end"] * step, 1),
                "ref": self._corner_view(ref_metrics[index]),
                "best_time": round(self.best_seg[index][0], 3),
                "best_lap_id": self.best_seg[index][1],
            }
            if lap_metrics:
                item["lap"] = self._corner_view(lap_metrics[index])
                item["loss"] = round(lap_metrics[index]["time"] - ref_metrics[index]["time"], 3)
            corners.append(item)
        view = {
            "ready": True, "length": self.length, "step": step, "n": n,
            "has_pos": self.geo["has_pos"], "corners": corners,
            "ref": {"lap_id": self.ref["id"], "time_ms": self.ref["time_ms"], "valid": bool(self.ref["valid"]),
                    "channels": channels(ref_rs)},
            "ref_provisional": self.ref_provisional,
        }
        if self.geo["has_pos"]:
            sign = -1.0 if self.geo["flip"] else 1.0
            view["x"] = _r(ref_rs["x"], 1)
            view["y"] = _r([sign * v for v in ref_rs["z"]], 1)
        if lap:
            view["lap"] = {"lap_id": lap["id"], "time_ms": lap["time_ms"], "valid": bool(lap["valid"]),
                           "channels": channels(lap_rs)}
            view["delta"] = _r(A.delta(lap_rs, ref_rs), 3)
            if self.geo["has_pos"] and lap["has_pos"]:
                sign = -1.0 if self.geo["flip"] else 1.0
                view["lap"]["x"] = _r(lap_rs["x"], 1)
                view["lap"]["y"] = _r([sign * v for v in lap_rs["z"]], 1)
        return view

    def coaching_view(self, pedals="position"):
        valid = self.valid
        base = {"ready": False, "valid_laps": len(valid), "needed": coaching.MIN_VALID, "cards": [],
                "strengths": [], "best_ms": self.best["time_ms"] if self.best else None,
                "theoretical_ms": self.theoretical_ms}
        times = [lap["time_ms"] for lap in valid]
        if len(valid) < coaching.MIN_VALID or not self.corners:
            base["cards"] = coaching.global_cards(self.laps, times, None, None, [])
            return base
        recent = valid[-coaching.RECENT:]
        cards = []
        strengths = []
        for index, corner in enumerate(self.corners):
            best_time, best_id = self.best_seg[index]
            target = self.metrics[best_id][index]
            rows = [self.metrics[lap["id"]][index] for lap in recent]
            losses = [row["time"] - best_time for row in rows]
            prev_name = self.corners[index - 1]["name"] if index else None
            card = coaching.corner_card(corner, target, rows, losses, self.step, pedals, prev_name)
            if card["cause"] == "carry" and cards and cards[-1]["corner"] == index - 1:
                # la perte prolonge celle du virage precedent : on la lui rattache
                previous = cards[-1]
                previous["gain_s"] = round(previous["gain_s"] + card["gain_s"], 3)
                previous["carry"] = {"name": corner["name"], "gain_s": card["gain_s"]}
                previous["focus"][1] = card["focus"][1]
                previous["observation"] += (" La perte se prolonge dans %s (%s s de plus en moyenne)."
                                            % (corner["name"], ("%.2f" % card["gain_s"]).replace(".", ",")))
                if previous["pattern"] == "ponctuel":
                    pass  # une erreur isolee reste "a surveiller"
                elif previous["gain_s"] >= 0.20:
                    previous["severity"] = "prioritaire"
                elif previous["gain_s"] >= 0.08:
                    previous["severity"] = "à travailler"
                continue
            if card["gain_s"] >= 0.08 or (card["pattern"] == "ponctuel" and card["worst_s"] >= 0.3):
                cards.append(card)
            elif card["gain_s"] < 0.04:
                strengths.append(corner["name"])
        cards.sort(key=lambda c: c["gain_s"], reverse=True)
        weak_names = [self.corners[c["corner"]]["name"] for c in cards]
        base["ready"] = True
        base["cards"] = cards[:6] + coaching.global_cards(self.laps, times, base["best_ms"], self.theoretical_ms,
                                                           weak_names)
        base["strengths"] = strengths
        base["potential_s"] = round(sum(c["gain_s"] for c in cards[:6]), 3)
        base["laps_used"] = len(recent)
        return base

    def live_reference(self):
        """Donnees compactes pour l'aide en direct (ecart, prochain virage)."""
        if not self.ref_rs:
            return None
        step = self.step
        metrics = self.metrics[self.ref["id"]]
        corners = []
        for corner, m in zip(self.corners, metrics):
            corners.append({
                "name": corner["name"], "dir": corner["dir"], "apex": corner["apex"] * step,
                "seg_start": corner["seg_start"] * step, "seg_end": corner["seg_end"] * step,
                "brake_on": None if m["brake_on"] is None else m["brake_on"] * step,
                "brake_off": None if m["brake_off"] is None else m["brake_off"] * step,
                "gas_on": None if m["gas_on"] is None else m["gas_on"] * step,
                "min_speed": m["min_speed"], "min_gear": m["min_gear"],
            })
        return {"combo_id": self.combo["id"], "lap_id": self.ref["id"], "time_ms": self.ref["time_ms"],
                "step": step, "n": self.ref_rs["n"], "t": self.ref_rs["t"], "speed": self.ref_rs["speed"],
                "corners": corners, "provisional": self.ref_provisional}


class Insights(object):
    """Cache des analyses, invalide a chaque modification de la base."""

    def __init__(self, storage):
        self.storage = storage
        self._lock = threading.RLock()
        self._rs = {}
        self._rs_order = []
        self._combo = {}

    def resampled(self, lap_id):
        with self._lock:
            if lap_id in self._rs:
                return self._rs[lap_id]
        lap = self.storage.lap(lap_id)
        combo = self.storage.combo(lap["combo_id"])
        rs = A.resample(lap["samples"], combo["track_length"], lap["own_ms"] / 1000.0)
        with self._lock:
            self._rs[lap_id] = rs
            self._rs_order.append(lap_id)
            while len(self._rs_order) > RS_CACHE:
                self._rs.pop(self._rs_order.pop(0), None)
        return rs

    def forget_lap(self, lap_id):
        with self._lock:
            self._rs.pop(lap_id, None)
            if lap_id in self._rs_order:
                self._rs_order.remove(lap_id)

    def combo(self, combo_id):
        revision = self.storage.revision
        with self._lock:
            cached = self._combo.get(combo_id)
            if cached and cached[0] == revision:
                return cached[1]
        analysis = ComboAnalysis(self, combo_id)
        with self._lock:
            self._combo = {combo_id: (revision, analysis)} if len(self._combo) > 6 else self._combo
            self._combo[combo_id] = (revision, analysis)
        return analysis
