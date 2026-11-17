"""Diagnostic : tout ce qu'il faut pour un rapport de bug ou de compatibilite."""
import json
import platform
import sys
import time

from . import __version__
from .evo_reader import GRAPHICS, MAP_NAMES, MIN_SIZES, PHYSICS, STATIC, EvoSource

# Champs personnels effaces avant toute capture partageable.
PRIVATE_FIELDS = {"graphics": ("driver_name", "driver_surname")}
_LAYOUTS = {"graphics": GRAPHICS, "static": STATIC}


def scrub(page, key="graphics"):
    """Efface les champs personnels d'une page avant de la partager."""
    data = bytearray(page)
    layout = _LAYOUTS.get(key)
    for name in PRIVATE_FIELDS.get(key, ()):
        field = layout.fields[name]
        if field.offset + field.size <= len(data):
            data[field.offset:field.offset + field.size] = b"\x00" * field.size
    return bytes(data)


def report(engine=None, source=None):
    info = {
        "application": "IRMS ému pro %s" % __version__,
        "python": sys.version.split()[0],
        "systeme": "%s %s (%s)" % (platform.system(), platform.release(), platform.machine()),
        "structures": {"physics": PHYSICS.size, "graphics": GRAPHICS.size, "static": STATIC.size},
        "tailles_minimales": MIN_SIZES,
        "zones_recherchees": dict((k, list(v)) for k, v in MAP_NAMES.items()),
    }
    source = source or (engine.source if engine else None)
    if source is not None:
        info["source"] = dict(source.state)
    if engine is not None:
        frame = engine.last_frame
        info["images_lues"] = engine.frames
        if frame is not None:
            info["derniere_image"] = {
                "voiture": frame.car, "circuit": frame.track, "trace": frame.config,
                "longueur_m": frame.track_length, "statut": frame.status, "position": round(frame.npos, 4),
                "vitesse": round(frame.speed, 1), "rapport": frame.gear, "regime": frame.rpm,
                "tour_valide": frame.valid, "position_monde": frame.has_pos, "version_jeu": frame.game_version,
            }
        info["base"] = {"profils": len(engine.storage.combos()), "revision": engine.storage.revision}
    return info


def run(dump=None, seconds=3.0):
    """Mode console : essaie de se connecter au jeu et affiche le rapport."""
    source = EvoSource()
    frame = None
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        got = source.poll()
        if got is not None:
            frame = got
        time.sleep(0.05)
    info = report(source=source)
    if frame is not None:
        info["derniere_image"] = {"voiture": frame.car, "circuit": frame.track, "trace": frame.config,
                                  "longueur_m": frame.track_length, "statut": frame.status,
                                  "vitesse": round(frame.speed, 1), "version_jeu": frame.game_version}
    text = json.dumps(info, indent=2, ensure_ascii=False)
    print(text)
    if dump and source._views:
        pages = dict((key, view.read()) for key, view in source._views.items())
        pages = dict((key, scrub(value, key)) for key, value in pages.items())
        payload = {"irms": __version__, "rapport": info,
                   "pages": dict((key, value.hex()) for key, value in pages.items())}
        with open(dump, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        print("\nCapture écrite dans %s (nom du pilote effacé)." % dump)
        if source.state.get("problems") or source.state.get("suspect"):
            print("Attention : la disposition des données semble avoir changé. Le nom du pilote peut se trouver "
                  "ailleurs dans la capture : ouvre le fichier et cherche ton nom avant de le partager.")
    elif dump:
        print("\nAucune capture : le jeu n'est pas détecté.")
    source.close()
    return 0 if source.state["platform_ok"] else 1
