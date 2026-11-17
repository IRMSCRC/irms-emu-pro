"""Fausses zones memoire EVO (Windows uniquement) pour les tests.

Cree les trois zones nommees comme le ferait le jeu et permet d'y ecrire
des pages produites par le simulateur. Sert aux tests automatiques et a
``tools/fake_evo.py`` (essayer toute la chaine sans lancer le jeu).
Ne jamais utiliser pendant que le vrai jeu tourne.
"""
from .evo_reader import FILE_MAP_WRITE, MAP_NAMES, PAGE_READWRITE, _kernel32

SIZES = {"physics": 4096, "graphics": 8192, "static": 4096}


class FakeMaps(object):
    def __init__(self, legacy_names=False):
        ctypes, k32, _ = _kernel32()
        self._ctypes = ctypes
        self._k32 = k32
        self._items = {}
        invalid = ctypes.c_void_p(-1).value
        for key, names in MAP_NAMES.items():
            name = names[1 if legacy_names else 0]
            handle = k32.CreateFileMappingW(invalid, None, PAGE_READWRITE, 0, SIZES[key], name)
            if not handle:
                raise OSError(ctypes.get_last_error(), "creation impossible: %s" % name)
            address = k32.MapViewOfFile(handle, FILE_MAP_WRITE, 0, 0, SIZES[key])
            if not address:
                raise OSError(ctypes.get_last_error(), "projection impossible: %s" % name)
            self._items[key] = (handle, address)

    def write(self, key, data):
        data = bytes(data)[: SIZES[key]]
        self._ctypes.memmove(self._items[key][1], data, len(data))

    def close(self):
        for handle, address in self._items.values():
            self._k32.UnmapViewOfFile(address)
            self._k32.CloseHandle(handle)
        self._items = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
