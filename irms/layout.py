"""Moteur de disposition memoire compatible ``#pragma pack(4)``.

Pourquoi ne pas utiliser ``ctypes.Structure`` ? Parce que ce module doit
donner exactement le meme resultat sur Windows, Linux et macOS (tests,
simulateur, relecture de captures), y compris pour les ``uint64`` alignes
sur 4 octets. Le calcul est donc fait a la main, puis verifie dans les tests
contre les ``offsetof`` produits par un compilateur C++ a partir de
l'en-tete C++ de la documentation Shared Memory du jeu.
"""
import struct

PACK = 4
_SIZES = {"f": 4, "i": 4, "I": 4, "h": 2, "H": 2, "b": 1, "B": 1, "?": 1, "Q": 8, "c": 1}


class Field(object):
    """Un champ aplati : chemin pointe, decalage, type et dimensions."""

    __slots__ = ("path", "offset", "code", "shape", "count", "size", "_st")

    def __init__(self, path, offset, code, shape):
        self.path = path
        self.offset = offset
        self.code = code
        self.shape = shape
        count = 1
        for dim in shape:
            count *= dim
        self.count = count
        self.size = count * _SIZES[code]
        fmt = "<%ds" % count if code == "c" else "<%d%s" % (count, code)
        self._st = struct.Struct(fmt)

    def read(self, buf):
        """Decode le champ. Retourne None si le tampon est trop court.

        Pour un tableau a deux dimensions partiellement present (cas d'une
        zone memoire plus petite que la structure la plus recente), seules
        les lignes completes disponibles sont retournees.
        """
        if buf is None:
            return None
        if self.offset + self.size > len(buf):
            if len(self.shape) != 2:
                return None
            inner = self.shape[-1]
            row = inner * _SIZES[self.code]
            rows = (len(buf) - self.offset) // row
            if rows <= 0:
                return None
            flat = struct.unpack_from("<%d%s" % (rows * inner, self.code), buf, self.offset)
            return [list(flat[i:i + inner]) for i in range(0, rows * inner, inner)]
        values = self._st.unpack_from(buf, self.offset)
        if self.code == "c":
            raw = values[0].split(b"\x00", 1)[0]
            try:
                return raw.decode("utf-8").strip()
            except UnicodeDecodeError:  # nom publie en Windows-1252 (accents)
                return raw.decode("cp1252", "replace").strip()
        if not self.shape:
            return values[0]
        if len(self.shape) == 1:
            return list(values)
        inner = self.shape[-1]
        return [list(values[i:i + inner]) for i in range(0, self.count, inner)]

    def write(self, buf, value):
        """Ecrit le champ dans un bytearray (simulateur et tests)."""
        if self.offset + self.size > len(buf):
            raise ValueError("tampon trop court pour %s" % self.path)
        if self.code == "c":
            raw = str(value).encode("utf-8")[: self.count - 1]
            self._st.pack_into(buf, self.offset, raw)
            return
        if not self.shape:
            flat = [value]
        elif len(self.shape) == 1:
            flat = list(value)
        else:
            flat = [x for row in value for x in row]
        if len(flat) != self.count:
            raise ValueError("%s attend %d valeurs" % (self.path, self.count))
        self._st.pack_into(buf, self.offset, *flat)


class Layout(object):
    """Disposition calculee d'une structure et de ses sous-structures."""

    def __init__(self, structs, name):
        self.name = name
        self._structs = structs
        self._cache = {}
        self.fields = {}
        self.size, self.align = self._measure(name)
        self._flatten(name, "", 0)

    # -- calcul ---------------------------------------------------------
    def _measure(self, name):
        if name in self._cache:
            return self._cache[name][:2]
        offset = 0
        align = 1
        members = []
        for fname, code, shape in self._structs[name]:
            if code in _SIZES:
                unit = _SIZES[code]
                falign = min(unit, PACK)
            else:
                unit, falign = self._measure(code)
            count = 1
            for dim in shape:
                count *= dim
            offset = (offset + falign - 1) // falign * falign
            members.append((fname, code, shape, offset, unit))
            offset += unit * count
            align = max(align, falign)
        size = (offset + align - 1) // align * align
        self._cache[name] = (size, align, members)
        return size, align

    def _flatten(self, name, prefix, base):
        for fname, code, shape, offset, unit in self._cache[name][2]:
            path = prefix + fname
            if code in _SIZES:
                self.fields[path] = Field(path, base + offset, code, shape)
            elif not shape:
                self._flatten(code, path + ".", base + offset)
            else:
                for index in range(shape[0]):
                    self._flatten(code, "%s[%d]." % (path, index), base + offset + index * unit)

    # -- acces ----------------------------------------------------------
    def members(self, name=None):
        """Decalage et taille des membres directs (pour les tests)."""
        name = name or self.name
        self._measure(name)
        out = {}
        for fname, code, shape, offset, unit in self._cache[name][2]:
            count = 1
            for dim in shape:
                count *= dim
            out[fname] = (offset, unit * count)
        return out

    def size_of(self, name):
        return self._measure(name)[0]

    def get(self, buf, path, default=None):
        value = self.fields[path].read(buf)
        return default if value is None else value

    def decode(self, buf, paths):
        return dict((p, self.fields[p].read(buf)) for p in paths)

    def encode(self, values, size=None):
        buf = bytearray(size or self.size)
        for path, value in values.items():
            self.fields[path].write(buf, value)
        return buf
