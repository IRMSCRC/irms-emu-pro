"""Stockage local SQLite : profils (voiture + circuit + trace) et tours."""
import datetime
import json
import os
import sqlite3
import struct
import threading
import zlib

from .recorder import CHANNELS

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS combos (
    id INTEGER PRIMARY KEY,
    car TEXT NOT NULL,
    track TEXT NOT NULL,
    config TEXT NOT NULL,
    track_length REAL NOT NULL,
    created_at TEXT NOT NULL,
    ref_lap_id INTEGER,
    corner_names TEXT NOT NULL DEFAULT '{}',
    UNIQUE (car, track, config, track_length)
);
CREATE TABLE IF NOT EXISTS laps (
    id INTEGER PRIMARY KEY,
    combo_id INTEGER NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    time_ms INTEGER NOT NULL,
    own_ms INTEGER NOT NULL,
    valid INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    time_source TEXT NOT NULL DEFAULT 'mesure',
    source TEXT NOT NULL DEFAULT 'evo',
    has_pos INTEGER NOT NULL DEFAULT 1,
    n INTEGER NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS laps_combo ON laps (combo_id, valid, time_ms);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def pack_samples(samples):
    n = len(samples["d"])
    head = json.dumps({"channels": list(CHANNELS), "n": n}).encode("ascii") + b"\n"
    body = b"".join(struct.pack("<%df" % n, *samples[name]) for name in CHANNELS)
    return zlib.compress(head + body, 6)


def unpack_samples(blob):
    raw = zlib.decompress(blob)
    head, body = raw.split(b"\n", 1)
    info = json.loads(head.decode("ascii"))
    n = info["n"]
    out = {}
    for index, name in enumerate(info["channels"]):
        out[name] = list(struct.unpack_from("<%df" % n, body, index * 4 * n))
    for name in CHANNELS:
        out.setdefault(name, [0.0] * n)
    return out


def _now():
    return datetime.datetime.now().replace(microsecond=0).isoformat(sep=" ")


class Storage(object):
    def __init__(self, path):
        self.path = path
        if path != ":memory:":
            folder = os.path.dirname(os.path.abspath(path))
            if not os.path.isdir(folder):
                os.makedirs(folder)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self.revision = 0
        with self._lock, self._db:
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Base créée par une version plus récente d'IRMS ému pro (schéma %d)." % version)
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)

    def close(self):
        with self._lock:
            self._db.close()

    def _bump(self):
        self.revision += 1

    # -- profils ----------------------------------------------------------
    def combo_id(self, car, track, config, track_length):
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT id FROM combos WHERE car=? AND track=? AND config=? AND track_length=?",
                (car, track, config, float(track_length))).fetchone()
            if row:
                return row["id"]
            cur = self._db.execute(
                "INSERT INTO combos (car, track, config, track_length, created_at) VALUES (?,?,?,?,?)",
                (car, track, config, float(track_length), _now()))
            self._bump()
            return cur.lastrowid

    def find_combo(self, car, track, config, track_length):
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM combos WHERE car=? AND track=? AND config=? AND track_length=?",
                (car, track, config, float(track_length))).fetchone()
        return row["id"] if row else None

    def combos(self):
        with self._lock:
            rows = self._db.execute("""
                SELECT c.*, COUNT(l.id) AS laps, SUM(l.valid) AS valid_laps,
                       MIN(CASE WHEN l.valid=1 THEN l.time_ms END) AS best_ms,
                       MAX(l.created_at) AS last_at
                FROM combos c LEFT JOIN laps l ON l.combo_id = c.id
                GROUP BY c.id ORDER BY last_at DESC, c.id DESC""").fetchall()
        return [dict(r) for r in rows]

    def combo(self, combo_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM combos WHERE id=?", (combo_id,)).fetchone()
        return dict(row) if row else None

    def delete_combo(self, combo_id):
        with self._lock, self._db:
            self._db.execute("DELETE FROM combos WHERE id=?", (combo_id,))
            self._bump()

    def set_reference(self, combo_id, lap_id):
        with self._lock, self._db:
            self._db.execute("UPDATE combos SET ref_lap_id=? WHERE id=?", (lap_id, combo_id))
            self._bump()

    def set_corner_names(self, combo_id, names):
        with self._lock, self._db:
            self._db.execute("UPDATE combos SET corner_names=? WHERE id=?",
                             (json.dumps(names, ensure_ascii=False), combo_id))
            self._bump()

    # -- tours ------------------------------------------------------------
    def add_lap(self, lap, source="evo", created_at=None):
        combo_id = self.combo_id(lap.car, lap.track, lap.config, lap.track_length)
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO laps (combo_id, created_at, time_ms, own_ms, valid, reason, time_source, source,"
                " has_pos, n, meta, data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (combo_id, created_at or _now(), int(lap.time_ms), int(lap.own_ms), 1 if lap.valid else 0,
                 lap.reason, lap.time_source, source, 1 if lap.has_pos else 0, lap.n,
                 json.dumps(lap.meta, ensure_ascii=False), pack_samples(lap.samples)))
            self._bump()
            return combo_id, cur.lastrowid

    def laps(self, combo_id):
        with self._lock:
            rows = self._db.execute(
                "SELECT id, combo_id, created_at, time_ms, own_ms, valid, reason, time_source, source, has_pos, n, meta"
                " FROM laps WHERE combo_id=? ORDER BY id", (combo_id,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["meta"] = json.loads(item["meta"] or "{}")
            out.append(item)
        return out

    def lap(self, lap_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM laps WHERE id=?", (lap_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["meta"] = json.loads(item["meta"] or "{}")
        item["samples"] = unpack_samples(item.pop("data"))
        return item

    def set_lap_valid(self, lap_id, valid, reason=""):
        with self._lock, self._db:
            self._db.execute("UPDATE laps SET valid=?, reason=? WHERE id=?", (1 if valid else 0, reason, lap_id))
            self._bump()

    def delete_lap(self, lap_id):
        with self._lock, self._db:
            self._db.execute("UPDATE combos SET ref_lap_id=NULL WHERE ref_lap_id=?", (lap_id,))
            self._db.execute("DELETE FROM laps WHERE id=?", (lap_id,))
            self._bump()

    # -- reglages ---------------------------------------------------------
    def setting(self, key, default=None):
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        with self._lock, self._db:
            self._db.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
            self._bump()
