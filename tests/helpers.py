"""Outils communs aux tests : dossier de fixtures, base de demo partagee."""
import atexit
import os
import shutil
import tempfile

from irms.engine import seed_demo
from irms.storage import Storage

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture_bytes(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="ascii") as handle:
        return bytes.fromhex(handle.read().strip())


def temp_db():
    """Chemin d'une base SQLite vide dans un dossier temporaire neuf."""
    folder = tempfile.mkdtemp(prefix="irms-test-")
    _FOLDERS.append(folder)
    return os.path.join(folder, "irms.sqlite")


_SEEDED = {}
_FOLDERS = []


@atexit.register
def _cleanup():
    """Ferme les bases partagees puis supprime les dossiers temporaires."""
    for storage in _SEEDED.values():
        try:
            storage.close()
        except Exception:
            pass
    for folder in _FOLDERS:
        shutil.rmtree(folder, ignore_errors=True)


def seeded_storage(laps=12):
    """Base de demo (2 voitures) fabriquee une seule fois par session de test."""
    if laps not in _SEEDED:
        storage = Storage(temp_db())
        seed_demo(storage, laps)
        _SEEDED[laps] = storage
    return _SEEDED[laps]
