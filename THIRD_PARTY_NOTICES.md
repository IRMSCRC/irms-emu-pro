# Sources et éléments tiers

IRMS ému pro n'embarque aucune bibliothèque tierce : il n'utilise que la bibliothèque standard de Python et du HTML, CSS et JavaScript écrits pour ce projet. Aucune police ni image externe n'est incluse.

## Disposition de la mémoire partagée d'Assetto Corsa EVO

La table des champs `irms/evo_structs.py` est **générée** par `tools/gen_structs.py` à partir de l'en-tête C++ qui accompagne la documentation « Shared Memory » d'Assetto Corsa EVO ([guide Steam 3707421508](https://steamcommunity.com/sharedfiles/filedetails/?id=3707421508)). L'en-tête lui-même n'est pas redistribué dans ce dépôt ; seuls les noms, types et tailles des champs, nécessaires à l'interopérabilité, en sont dérivés. La copie utilisée pour la génération est celle du projet [acevo-shared-memory](https://github.com/dSyncro/acevo-shared-memory) (`src/bindings/source/wrapper.hpp`).

Assetto Corsa EVO est un jeu de Kunos Simulazioni. Ce projet n'est ni affilié à Kunos Simulazioni ni approuvé par cette société.

## Captures de test

Les fichiers `tests/fixtures/evo_0_6_2_graphics.hex` et `tests/fixtures/evo_0_6_2_static.hex` sont les captures mémoire réelles (4096 et 2048 octets, Assetto Corsa EVO 0.6.2) fournies comme données de test par le projet [acevo-sdk](https://github.com/glebulon/acevo-sdk), sous licence MIT, Copyright (c) 2026 SimLaps. Le champ du nom de pilote y a été effacé.

```
MIT License

Copyright (c) 2026 SimLaps

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Documentation consultée

Ces projets ont aidé à comprendre le comportement du jeu. Aucun code n'en a été copié.

- [live-telemetry-evo](https://github.com/albertowd/live-telemetry-evo/blob/develop/docs/SHARED_MEMORY.md) : référence détaillée de la mémoire partagée (ouverture en lecture seule, conventions des rapports et des pédales).
- [acevo-sdk](https://github.com/glebulon/acevo-sdk) : validation empirique des emplacements de champs.
- [acevo-shared-memory](https://github.com/dSyncro/acevo-shared-memory) : copie de l'en-tête C++.
