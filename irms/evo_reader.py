"""Connecteur Assetto Corsa EVO : lecture seule de la memoire partagee.

Correctif de fraicheur pour IRMS emu pro 3.0.0.

Le decodage et les interfaces publiques du lecteur d'origine sont conserves.
La fraicheur est determinee a partir du contenu utile de graphics, et non
uniquement de packetId. L'historique de fraicheur survit aux reconnexions :
rouvrir une zone contenant les memes octets ne la rend pas a nouveau active.

Aucune ecriture dans la memoire du jeu. Aucune modification des tours SQLite.
Ce module ne gere pas la conservation du bilan dans l'interface web.
"""
import re
import sys
import time

from .evo_structs import STRUCTS
from .frame import Frame, STATUS_LIVE, STATUS_PAUSE
from .layout import Layout

PHYSICS = Layout(STRUCTS, "SPageFilePhysics")
GRAPHICS = Layout(STRUCTS, "SPageFileGraphicEvo")
STATIC = Layout(STRUCTS, "SPageFileStaticEvo")

MAP_NAMES = {
    "physics": ("Local\\acevo_pmf_physics", "Local\\acpmf_physics"),
    "graphics": ("Local\\acevo_pmf_graphics", "Local\\acpmf_graphics"),
    "static": ("Local\\acevo_pmf_static", "Local\\acpmf_static"),
}
MIN_SIZES = {"physics": 800, "graphics": 3844, "static": 208}
STALE_SECONDS = 3.0
RETRY_SECONDS = 2.0
_BOOL_PROBES = (
    "is_rpm_limiter_on", "tc_active", "abs_active", "is_valid_lap",
    "is_in_pit_lane", "timing_state.is_invalid",
)
_VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}")


def _clamp(value, low, high):
    if value != value:
        return low
    return low if value < low else high if value > high else value


def _printable(text):
    return bool(text) and text.isprintable()


def _finite(value):
    return value is not None and value == value and abs(value) < 1e12


def player_position(graphics, physics):
    """Position monde (x, z) du joueur, ou None (logique d'origine)."""
    coords = GRAPHICS.fields["car_coordinates"].read(graphics)
    ids = GRAPHICS.fields["car_ids"].read(graphics)
    if coords and ids:
        a = GRAPHICS.get(graphics, "player_car_id_a", 0)
        b = GRAPHICS.get(graphics, "player_car_id_b", 0)
        if a or b:
            for index, pair in enumerate(ids):
                if index < len(coords) and pair[0] == a and pair[1] == b:
                    x, _, z = coords[index]
                    if _finite(x) and _finite(z) and (abs(x) > 1e-6 or abs(z) > 1e-6):
                        return x, z, "car_coordinates"
                    break
    points = PHYSICS.fields["tyreContactPoint"].read(physics)
    if points:
        xs = [p[0] for p in points]
        zs = [p[2] for p in points]
        if all(_finite(v) for v in xs + zs) and any(abs(v) > 1e-6 for v in xs + zs):
            return sum(xs) / 4.0, sum(zs) / 4.0, "tyreContactPoint"
    return None


def decode_frame(physics, graphics, static, t=0.0):
    """Convertit les trois zones en (Frame, problemes, details).

    Fonction de decodage conservee a partir du fichier fourni par l'utilisateur.
    Aucun nouveau champ de Frame ni changement de structure memoire requis.
    """
    problems = []
    details = {}
    g = GRAPHICS
    if graphics is None or len(graphics) < MIN_SIZES["graphics"]:
        problems.append("zone graphics absente ou trop petite (%d octets)" % len(graphics or b""))
        return Frame(t=t), problems, details
    if static is None or len(static) < MIN_SIZES["static"]:
        problems.append("zone static absente ou trop petite (%d octets)" % len(static or b""))
        return Frame(t=t), problems, details

    frame = Frame(t=t)
    frame.packet = g.get(graphics, "packetId", 0)
    frame.status = g.get(graphics, "status", 0)
    frame.car = g.get(graphics, "car_model", "")
    frame.track = STATIC.get(static, "track", "")
    frame.config = STATIC.get(static, "track_configuration", "")
    frame.track_length = STATIC.get(static, "track_length_m", 0.0)
    frame.session = STATIC.get(static, "session_name", "")
    frame.game_version = STATIC.get(static, "ac_evo_version", "")
    details["sm_version"] = STATIC.get(static, "sm_version", "")
    frame.npos = g.get(graphics, "npos", 0.0)
    frame.lap_time_ms = g.get(graphics, "current_lap_time_ms", 0)
    frame.last_lap_ms = g.get(graphics, "last_laptime_ms", 0)
    frame.best_lap_ms = g.get(graphics, "best_laptime_ms", 0)
    frame.lap_count = g.get(graphics, "total_lap_count", 0)
    frame.valid = bool(g.get(graphics, "is_valid_lap", True)) and not g.get(graphics, "timing_state.is_invalid", False)
    frame.in_pit = bool(
        g.get(graphics, "is_in_pit_lane", False)
        or g.get(graphics, "is_in_pit_box", False)
        or g.get(graphics, "car_location", 4) in (1, 2, 3)
    )
    frame.abs = bool(g.get(graphics, "abs_active", False))
    frame.tc = bool(g.get(graphics, "tc_active", False))
    frame.fuel = g.get(graphics, "fuel_liter_current_quantity", 0.0)
    frame.compound = g.get(graphics, "tyre_lf.tyre_compound_front", "")
    frame.delta_ms = g.get(graphics, "delta_time_ms", None)
    frame.steer = _clamp(g.get(graphics, "steering_percent", 0.0), -1.0, 1.0)
    frame.glat = g.get(graphics, "g_forces_x", 0.0)
    frame.glon = g.get(graphics, "g_forces_y", 0.0)

    gear_raw = g.get(graphics, "gear_int", 1)
    rpm = g.get(graphics, "rpm", 0)
    speed = float(g.get(graphics, "display_speed_kmh", 0))
    gas = g.get(graphics, "gas_percent", 0.0)
    brake = g.get(graphics, "brake_percent", 0.0)
    g_gas, g_brake = gas, brake
    details["inputs"] = "graphics"

    p_ok = (
        physics is not None and len(physics) >= MIN_SIZES["physics"]
        and PHYSICS.get(physics, "packetId", 0) != 0
    )
    if p_ok:
        p_speed = PHYSICS.get(physics, "speedKmh", 0.0)
        p_gas = PHYSICS.get(physics, "gas", 0.0)
        p_brake = PHYSICS.get(physics, "brake", 0.0)
        if (
            _finite(p_speed) and 0.0 <= p_speed <= 500.0
            and _finite(p_gas) and _finite(p_brake)
            and -0.01 <= p_gas <= 1.01 and -0.01 <= p_brake <= 1.01
            and abs(p_speed - speed) <= max(15.0, 0.15 * speed)
        ):
            speed, gas, brake = p_speed, p_gas, p_brake
            details["inputs"] = "physics"
        frame.max_rpm = PHYSICS.get(physics, "currentMaxRpm", 0)
        frame.ai = bool(PHYSICS.get(physics, "isAIControlled", 0))
        air = PHYSICS.get(physics, "airTemp", 0.0)
        road = PHYSICS.get(physics, "roadTemp", 0.0)
        if _finite(air) and -40.0 < air < 70.0 and air != 0.0:
            frame.air_temp = air
        if _finite(road) and -40.0 < road < 90.0 and road != 0.0:
            frame.road_temp = road
    if frame.air_temp is None:
        frame.air_temp = STATIC.get(static, "starting_ambient_temperature_c", None) or None
    if frame.road_temp is None:
        frame.road_temp = STATIC.get(static, "starting_ground_temperature_c", None) or None

    frame.speed = speed
    frame.gas = _clamp(gas, 0.0, 1.0)
    frame.brake = _clamp(brake, 0.0, 1.0)
    frame.gear = gear_raw - 1
    frame.rpm = rpm
    position = player_position(graphics, physics if p_ok else None)
    if position:
        frame.x, frame.z, details["position"] = position
        frame.has_pos = True
    else:
        details["position"] = "indisponible"

    if frame.status not in (0, 1, 2, 3):
        problems.append("status inattendu (%r)" % frame.status)
    version = frame.game_version
    if version and not _VERSION_RE.match(version):
        problems.append("version du jeu illisible (%r)" % version[:20])
    ranges = []
    if not _finite(frame.npos) or not -0.05 <= frame.npos <= 1.05:
        ranges.append("position normalisee hors limites (%r)" % frame.npos)
    if not 0 <= gear_raw <= 13:
        ranges.append("rapport hors limites (%r)" % gear_raw)
    if not 0 <= rpm <= 25000:
        ranges.append("regime hors limites (%r)" % rpm)
    if not _finite(speed) or not 0.0 <= speed <= 500.0:
        ranges.append("vitesse hors limites (%r)" % speed)
    for label, value in (("accelerateur", g_gas), ("frein", g_brake)):
        if not _finite(value) or not -0.01 <= value <= 1.01:
            ranges.append("%s hors limites (%r)" % (label, value))
    for label, value in (("position normalisee", frame.npos), ("accelerateur", g_gas), ("frein", g_brake)):
        if _finite(value) and 0.0 < abs(value) < 1e-20:
            ranges.append("%s denormalisee (%r)" % (label, value))
    for name in _BOOL_PROBES:
        field = g.fields[name]
        if field.offset < len(graphics) and graphics[field.offset] > 1:
            ranges.append("booleen %s invalide (%d)" % (name, graphics[field.offset]))
            break
    if frame.status == STATUS_LIVE:
        problems.extend(ranges)
        if not _finite(frame.track_length) or not 100.0 <= frame.track_length <= 30000.0:
            problems.append("longueur de piste hors limites (%r)" % frame.track_length)
        if not 0 <= frame.lap_time_ms <= 6 * 3600 * 1000:
            problems.append("temps au tour hors limites (%r)" % frame.lap_time_ms)
        details["suspect"] = []
    else:
        details["suspect"] = ranges
    if frame.status in (STATUS_LIVE, STATUS_PAUSE):
        if not _printable(frame.car):
            problems.append("nom de voiture vide ou illisible")
        if not _printable(frame.track):
            problems.append("nom de circuit vide ou illisible")
    return frame, problems, details


FILE_MAP_READ = 0x0004
ERROR_ACCESS_DENIED = 5
FILE_MAP_WRITE = 0x0002
PAGE_READWRITE = 0x04


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fields = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
    ]
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        fields.append(("PartitionId", wintypes.WORD))
    fields += [
        ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD),
    ]

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = fields

    k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.OpenFileMappingW.restype = wintypes.HANDLE
    k32.CreateFileMappingW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
    ]
    k32.CreateFileMappingW.restype = wintypes.HANDLE
    k32.MapViewOfFile.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, ctypes.c_size_t,
    ]
    k32.MapViewOfFile.restype = ctypes.c_void_p
    k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    k32.UnmapViewOfFile.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.VirtualQuery.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
    ]
    k32.VirtualQuery.restype = ctypes.c_size_t
    return ctypes, k32, MEMORY_BASIC_INFORMATION


class MappedView(object):
    """Vue en lecture seule d'une zone existante ; aucune creation de zone."""

    def __init__(self, name):
        ctypes, k32, mbi_type = _kernel32()
        self._ctypes = ctypes
        self._k32 = k32
        self.name = name
        self.handle = None
        self.address = None
        self.size = 0
        self.handle = k32.OpenFileMappingW(FILE_MAP_READ, False, name)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "zone introuvable: %s" % name)
        self.address = k32.MapViewOfFile(self.handle, FILE_MAP_READ, 0, 0, 0)
        if not self.address:
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "projection impossible: %s" % name)
        info = mbi_type()
        got = k32.VirtualQuery(self.address, ctypes.byref(info), ctypes.sizeof(info))
        self.size = int(info.RegionSize) if got else 0
        if self.size <= 0 or self.size > 1 << 24:
            self.close()
            raise OSError(0, "taille de zone inattendue: %s" % name)

    def read(self):
        """Copie stable ; refuse les quatre tentatives si elles sont dechirees."""
        if not self.address:
            raise OSError(0, "zone fermee: %s" % self.name)
        ctypes = self._ctypes
        for _ in range(4):
            before = ctypes.c_int32.from_address(self.address).value
            data = ctypes.string_at(self.address, self.size)
            after = ctypes.c_int32.from_address(self.address).value
            if before == after:
                return data
        raise OSError(0, "lecture instable: %s" % self.name)

    def close(self):
        if self.address:
            self._k32.UnmapViewOfFile(self.address)
            self.address = None
        if self.handle:
            self._k32.CloseHandle(self.handle)
            self.handle = None


class EvoSource(object):
    """Source EVO. poll() rend une Frame, ou None sans nouvelle source fiable.

    connected indique une source recemment actualisee ; stale signifie que le
    contenu utile de graphics n'a pas evolue depuis STALE_SECONDS. La presence
    d'une zone memoire seule ne prouve pas que la simulation tourne encore.
    """

    kind = "evo"

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._views = {}
        self._denied = False
        self._next_try = 0.0
        self._last_packet = None
        self._last_signature = None
        self._last_change = 0.0
        self._needs_progress = False
        self.state = {
            "source": "evo",
            "platform_ok": sys.platform == "win32",
            "connected": False,
            "maps": {},
            "problems": [],
            "suspect": [],
            "stale": False,
            "status": 0,
            "game_version": "",
            "sm_version": "",
            "inputs": "",
            "position": "",
            "message": "",
            "graphics_packet": None,
            "last_data_age_s": None,
            "freshness_method": "graphics_content",
        }
        if not self.state["platform_ok"]:
            self.state["message"] = (
                "La mémoire partagée d'Assetto Corsa EVO n'existe que sous Windows. "
                "Utilise le mode démo sur ce système."
            )

    @staticmethod
    def _dispose(views):
        for view in views.values():
            try:
                view.close()
            except OSError:
                pass

    def _open(self):
        self._denied = False
        for index in (0, 1):
            views = {}
            try:
                for key, names in MAP_NAMES.items():
                    views[key] = MappedView(names[index])
            except OSError as exc:
                if exc.errno == ERROR_ACCESS_DENIED:
                    self._denied = True
                self._dispose(views)
                continue
            except Exception as exc:
                self._dispose(views)
                self.state["message"] = "Erreur d'accès mémoire : %s" % exc
                self._views = {}
                self.state["maps"] = {}
                return False
            self._views = views
            self.state["maps"] = {
                key: {"name": view.name, "size": view.size}
                for key, view in views.items()
            }
            return True
        self._views = {}
        self.state["maps"] = {}
        return False

    def close(self):
        """Libere les vues SANS oublier les derniers octets observes.

        C'est le point essentiel du correctif : une reouverture ne doit pas
        offrir trois nouvelles secondes de validite a la meme vieille image.
        """
        self._dispose(self._views)
        self._views = {}
        self.state["connected"] = False
        self.state["maps"] = {}

    def _mark_stale(self, now):
        self._needs_progress = True
        self.close()
        self._next_try = now + RETRY_SECONDS
        self.state["stale"] = True
        self.state["status"] = 0
        self.state["message"] = (
            "Télémétrie suspendue : les données du jeu ne progressent plus "
            "(fin de session, pause, menu, chargement ou jeu fermé). "
            "Attente de données réellement nouvelles ; reconnexion automatique."
        )

    def poll(self):
        state = self.state
        if not state["platform_ok"]:
            return None
        now = self._clock()
        if not self._views:
            if now < self._next_try:
                return None
            self._next_try = now + RETRY_SECONDS
            if not self._open():
                state["connected"] = False
                state["status"] = 0
                if self._denied:
                    state["message"] = (
                        "Windows refuse l'accès aux données du jeu. Lance le jeu et IRMS "
                        "avec les mêmes droits, normalement sans mode administrateur."
                    )
                elif not self._needs_progress:
                    state["message"] = (
                        "Assetto Corsa EVO non détecté. Lance le jeu et charge une session. "
                        "La connexion est automatique."
                    )
                return None
            # NE PAS reinitialiser _last_signature ou _last_change ici.

        try:
            raw = {key: view.read() for key, view in self._views.items()}
        except OSError as exc:
            self._needs_progress = self._last_signature is not None
            self.close()
            self._next_try = now + RETRY_SECONDS
            state["stale"] = self._needs_progress
            state["status"] = 0
            state["message"] = "Lecture mémoire interrompue : %s. Nouvelle tentative automatique." % exc
            return None

        # Comparer uniquement la partie utile de graphics. Ne pas utiliser static
        # comme battement de vie : cette page est normalement constante. Ne pas
        # laisser physics seule maintenir une position/tour graphics perimee.
        graphics = raw.get("graphics")
        signature = bytes(graphics[:MIN_SIZES["graphics"]]) if graphics else b""
        changed = self._last_signature is None or signature != self._last_signature
        if changed:
            self._last_signature = signature
            self._last_change = now
            self._needs_progress = False
        age = max(0.0, now - self._last_change)
        state["last_data_age_s"] = round(age, 3)

        if self._needs_progress or age > STALE_SECONDS:
            self._mark_stale(now)
            return None

        frame, problems, details = decode_frame(
            raw.get("physics"), graphics, raw.get("static"), now
        )
        self._last_packet = frame.packet
        state["graphics_packet"] = frame.packet
        state["status"] = frame.status
        state["game_version"] = frame.game_version
        state["sm_version"] = details.get("sm_version", "")
        state["inputs"] = details.get("inputs", "")
        state["position"] = details.get("position", "")
        state["problems"] = problems
        state["suspect"] = details.get("suspect", [])
        state["stale"] = False
        state["connected"] = True
        if problems:
            state["message"] = (
                "Données incohérentes : la disposition mémoire peut différer de celle connue. "
                "Enregistrement suspendu."
            )
            frame.status = -1
            return frame
        if frame.status == STATUS_LIVE:
            state["message"] = "Connecté à Assetto Corsa EVO %s." % (frame.game_version or "")
        elif frame.status == STATUS_PAUSE:
            state["message"] = "Assetto Corsa EVO en pause. Enregistrement suspendu."
        else:
            state["message"] = (
                "Assetto Corsa EVO détecté, hors conduite active (menu, chargement ou rediffusion)."
            )
        return frame
