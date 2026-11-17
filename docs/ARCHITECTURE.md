# Architecture

IRMS ému pro est un petit serveur web local écrit en Python pur (bibliothèque standard uniquement). L'interface est une page HTML, une feuille de style et un script, sans étape de compilation.

## Vue d'ensemble

```
            ┌──────────────┐   ┌──────────────┐
            │ evo_reader   │   │ simulator    │      sources de télémétrie
            │ (jeu, Win32) │   │ (mode démo)  │      -> objets Frame
            └──────┬───────┘   └──────┬───────┘
                   └────────┬─────────┘
                        ┌───▼────┐
                        │ engine │  boucle temps réel (fil dédié)
                        └───┬────┘
              ┌─────────────┼───────────────┐
        ┌─────▼────┐   ┌────▼─────┐   ┌─────▼─────┐
        │ recorder │   │ insights │   │  live()   │
        │ (tours)  │   │ (cache)  │   │ (direct)  │
        └─────┬────┘   └────┬─────┘   └─────┬─────┘
        ┌─────▼────┐   ┌────▼──────────┐    │
        │ storage  │◄──┤ analysis      │    │
        │ (SQLite) │   │ coaching      │    │
        └──────────┘   └───────────────┘    │
                        ┌───────────────────▼──┐
                        │ server (HTTP + SSE)  │──> navigateur, tablette
                        └──────────────────────┘
```

## Modules

| Module | Rôle |
| --- | --- |
| `irms/frame.py` | `Frame` : un échantillon de télémétrie, commun au jeu et à la démo. Ne contient aucun champ personnel. |
| `irms/layout.py` | Calcule les emplacements des champs d'une structure C `#pragma pack(4)`, de façon identique sur tous les systèmes. |
| `irms/evo_structs.py` | Table des champs de la mémoire partagée du jeu. **Fichier généré** par `tools/gen_structs.py`. |
| `irms/evo_reader.py` | Ouvre les zones mémoire du jeu en lecture seule, décode un `Frame`, contrôle la plausibilité des valeurs. |
| `irms/evo_fake.py` | Crée de fausses zones mémoire sous Windows, pour les tests et `tools/fake_evo.py`. |
| `irms/simulator.py` | Circuit et voitures fictifs, pilote simulé avec des défauts reproductibles ; sait aussi fabriquer des pages mémoire au format du jeu. |
| `irms/recorder.py` | Découpe le flux en tours, mesure le temps au passage de la ligne, juge la validité. |
| `irms/storage.py` | Base SQLite : profils, tours (voies compressées), réglages. |
| `irms/analysis.py` | Rééchantillonnage par distance, géométrie, détection des virages, mesures par virage, écarts, secteurs. |
| `irms/coaching.py` | Transforme les mesures en cartes de conseil. |
| `irms/insights.py` | Assemble stockage, analyse et conseils ; garde les résultats en cache par profil. |
| `irms/engine.py` | Boucle temps réel : lit la source, alimente l'enregistreur, prépare l'état « direct ». |
| `irms/server.py` | Fichiers de l'interface, API JSON, flux temps réel (Server-Sent Events), protections. |
| `irms/doctor.py` | Rapport de diagnostic et capture mémoire anonymisée. |
| `irms/__main__.py` | Ligne de commande : `run`, `demo`, `doctor`, `version`. |
| `irms/web/` | Interface : `index.html`, `style.css`, `app.js`, `icon.svg`. |

## Parcours d'une donnée

1. `engine` appelle `source.poll()` environ 60 fois par seconde. La source renvoie un `Frame` ou rien.
2. `recorder` ajoute l'échantillon au tour en cours. Au passage de la ligne, il clôt le tour et attend jusqu'à 2,5 s le temps officiel publié par le jeu ; à défaut, il garde son propre temps (interpolé au passage de la ligne).
3. `storage` enregistre le tour dans le profil voiture + circuit + tracé + longueur de piste.
4. `insights` invalide son cache pour ce profil. À la prochaine demande, `analysis` reprojette les tours sur une grille de distance (un point tous les 2 m environ), détecte les virages sur le tour de référence et mesure chaque tour valide.
5. `server` envoie l'état « direct » au navigateur par un flux SSE (environ 15 images par seconde). Le champ `revision` signale à l'interface qu'elle doit recharger les tours.

## Choix de conception

- **Tout est dérivé des tours du pilote.** Pas de base de circuits ni de voitures : le plan, les virages et les repères viennent de la télémétrie, donc tout circuit et toute voiture fonctionnent, y compris les futurs contenus du jeu.
- **Un profil par voiture.** Les repères de freinage n'ont de sens que pour une voiture donnée.
- **La distance, pas le temps.** Les tours sont comparés à distance égale sur la piste, ce qui permet de superposer deux tours et de mesurer un écart en chaque point.
- **Le doute suspend.** Si les données ne sont pas plausibles, on n'enregistre pas.
- **Aucune dépendance.** L'installation se limite à Python ; il n'y a rien à compiler ni à télécharger.

## Fils d'exécution

- Un fil pour la boucle `engine`.
- Un fil par connexion HTTP (`ThreadingHTTPServer`).
- `storage` protège la base par un verrou réentrant ; `insights` protège son cache de la même façon.

## Tests

| Fichier | Ce qu'il vérifie |
| --- | --- |
| `tests/test_layout.py` | Emplacements et tailles de tous les champs contre les valeurs d'un compilateur C++ (`fixtures/golden_offsets.json`). |
| `tests/test_evo_reader.py` | Décodage d'une capture réelle du jeu, pages fabriquées, détection des dispositions décalées, vie privée. |
| `tests/test_recorder.py` | Découpe des tours, temps, validité, changements de voiture. |
| `tests/test_analysis.py` | Rééchantillonnage, virages, mesures, conseils attendus sur les défauts simulés. |
| `tests/test_server.py` | API, export et import, protections. |
| `tests/test_windows.py` | Vraies zones mémoire nommées Windows (ignoré ailleurs). |

Lancer la suite : `python -m unittest discover -s tests -t .`
