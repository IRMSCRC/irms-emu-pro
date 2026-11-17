"""Echantillon de telemetrie commun a toutes les sources (jeu ou demo)."""

STATUS_OFF, STATUS_REPLAY, STATUS_LIVE, STATUS_PAUSE = 0, 1, 2, 3
STATUS_LABELS = {0: "arrêté", 1: "replay", 2: "en piste", 3: "pause"}


class Frame(object):
    """Un instant de telemetrie, deja converti en unites lisibles.

    Les pedales vont de 0 a 1, le volant de -1 (gauche) a +1 (droite), le
    rapport vaut -1 (marche arriere), 0 (point mort) ou 1..n.
    """

    __slots__ = (
        "t", "packet", "status", "car", "track", "config", "track_length",
        "npos", "lap_time_ms", "last_lap_ms", "best_lap_ms", "lap_count",
        "valid", "in_pit", "speed", "gas", "brake", "steer", "gear", "rpm",
        "glat", "glon",
        "max_rpm", "x", "z", "has_pos", "abs", "tc", "fuel", "session",
        "game_version", "air_temp", "road_temp", "compound", "delta_ms", "ai",
    )

    def __init__(self, **kw):
        self.t = 0.0
        self.packet = 0
        self.status = STATUS_OFF
        self.car = ""
        self.track = ""
        self.config = ""
        self.track_length = 0.0
        self.npos = 0.0
        self.lap_time_ms = 0
        self.last_lap_ms = 0
        self.best_lap_ms = 0
        self.lap_count = 0
        self.valid = True
        self.in_pit = False
        self.speed = 0.0
        self.gas = 0.0
        self.brake = 0.0
        self.steer = 0.0
        self.gear = 0
        self.rpm = 0
        self.max_rpm = 0
        self.glat = 0.0
        self.glon = 0.0
        self.x = 0.0
        self.z = 0.0
        self.has_pos = False
        self.abs = False
        self.tc = False
        self.fuel = 0.0
        self.session = ""
        self.game_version = ""
        self.air_temp = None
        self.road_temp = None
        self.compound = ""
        self.delta_ms = None
        self.ai = False
        for key, value in kw.items():
            setattr(self, key, value)

    @property
    def dist(self):
        """Distance parcourue dans le tour, en metres."""
        return max(0.0, min(1.0, self.npos)) * self.track_length

    def combo(self):
        return (self.car, self.track, self.config)

    def as_dict(self):
        return dict((name, getattr(self, name)) for name in self.__slots__)
