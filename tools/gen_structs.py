#!/usr/bin/env python3
"""Regenere irms/evo_structs.py et tests/fixtures/golden_offsets.json.

Usage (developpeurs uniquement, necessite g++ ou clang++) :

    python tools/gen_structs.py chemin/vers/SharedFileOut.hpp

L'en-tete C++ du jeu n'est pas distribue avec ce depot. Il accompagne la
documentation "Shared Memory" d'Assetto Corsa EVO (guide Steam 3707421508)
et se trouve aussi dans des projets libres comme acevo-shared-memory
(src/bindings/source/wrapper.hpp).
Le script :
  1. lit les structures C++ de l'en-tete ;
  2. ecrit la table des champs Python (irms/evo_structs.py) ;
  3. compile un petit programme qui imprime offsetof/sizeof de chaque champ,
     et enregistre le resultat comme reference de test (golden_offsets.json).
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIMS = {
    "float": "f", "int": "i", "int32_t": "i", "uint32_t": "I", "short": "h",
    "unsigned short": "H", "int8_t": "b", "uint8_t": "B", "bool": "?",
    "uint64_t": "Q", "char": "c",
}
FIELD = re.compile(r"([\w ]+?)\s+(\w+)((?:\[\d+\])*)\s*(?:=[^;]*|\{\})?;")


def parse(src):
    typedefs = dict((m.group(1), "i") for m in re.finditer(r"typedef int (\w+);", src))
    structs = {}
    for m in re.finditer(r"struct (\w+) \{(.*?)\n\t\};", src, re.S):
        fields = []
        for line in m.group(2).split("\n"):
            line = line.strip()
            if not line or line[0] in "/*":
                continue
            fm = FIELD.match(line)
            if not fm:
                continue
            ctype, name, dims = fm.group(1).strip(), fm.group(2), fm.group(3)
            shape = tuple(int(d) for d in re.findall(r"\[(\d+)\]", dims))
            code = PRIMS.get(ctype) or typedefs.get(ctype) or ctype
            fields.append((name, code, shape))
        structs[m.group(1)] = fields
    return structs


def golden(header, structs):
    lines = ["#include <cstdio>", "#include <cstddef>", '#include "%s"' % header.name,
             "using namespace ks;", "int main(){"]
    for s, fields in structs.items():
        lines.append('printf("%s * 0 %%zu\\n", sizeof(%s));' % (s, s))
        for name, _, _ in fields:
            lines.append('printf("%s %s %%zu %%zu\\n", offsetof(%s,%s), sizeof(((%s*)0)->%s));'
                         % (s, name, s, name, s, name))
    lines.append("}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / header.name).write_text(header.read_text(encoding="utf-8"), encoding="utf-8")
        (tmp / "gen.cpp").write_text("\n".join(lines))
        subprocess.check_call(["g++", "-std=c++17", "-Wno-invalid-offsetof", "gen.cpp", "-o", "gen"], cwd=tmp)
        out = subprocess.check_output([str(tmp / "gen")], text=True)
    result = {}
    for line in out.splitlines():
        s, name, off, size = line.split()
        entry = result.setdefault(s, {"size": 0, "fields": {}})
        if name == "*":
            entry["size"] = int(size)
        else:
            entry["fields"][name] = [int(off), int(size)]
    return result


def main():
    header = pathlib.Path(sys.argv[1])
    structs = parse(header.read_text(encoding="utf-8"))
    out = ['"""Table des champs de la memoire partagee Assetto Corsa EVO.',
           "",
           "FICHIER GENERE par tools/gen_structs.py a partir de l'en-tete C++ de la",
           "documentation Shared Memory d'Assetto Corsa EVO (guide Steam 3707421508).",
           "Ne pas modifier a la main : relancer le generateur.",
           "",
           "Chaque champ est (nom, type, dimensions). Types : f float32, i int32,",
           "I uint32, h int16, H uint16, b int8, B uint8, ? bool (1 octet),",
           "Q uint64, c char (tableau 1D = chaine ASCII terminee par zero),",
           'ou le nom d\'une autre structure. Alignement : #pragma pack(4).',
           '"""',
           "",
           "STRUCTS = {"]
    for s, fields in structs.items():
        out.append("    %r: [" % s)
        for name, code, shape in fields:
            out.append("        (%r, %r, %r)," % (name, code, shape))
        out.append("    ],")
    out.append("}")
    out.append("")
    (ROOT / "irms" / "evo_structs.py").write_text("\n".join(out), encoding="utf-8")
    gold = golden(header, structs)
    (ROOT / "tests" / "fixtures" / "golden_offsets.json").write_text(
        json.dumps(gold, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("structures:", {k: len(v) for k, v in structs.items()})


if __name__ == "__main__":
    main()
