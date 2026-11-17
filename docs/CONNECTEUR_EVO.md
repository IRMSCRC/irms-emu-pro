# Connecteur Assetto Corsa EVO

Ce document décrit comment IRMS lit le jeu, ce qui a été vérifié, et quoi faire quand une mise à jour du jeu change les données.

## Source des données

Sous Windows, le jeu publie trois zones de mémoire partagée nommées. Leur contenu est décrit par la documentation « Shared Memory » du jeu ([guide Steam](https://steamcommunity.com/sharedfiles/filedetails/?id=3707421508)) :

| Zone | Nom actuel | Ancien nom | Structure | Rythme |
| --- | --- | --- | --- | --- |
| physics | `Local\acevo_pmf_physics` | `Local\acpmf_physics` | `SPageFilePhysics` (800 octets) | chaque pas de simulation |
| graphics | `Local\acevo_pmf_graphics` | `Local\acpmf_graphics` | `SPageFileGraphicEvo` (4900 octets) | chaque image affichée |
| static | `Local\acevo_pmf_static` | `Local\acpmf_static` | `SPageFileStaticEvo` (208 octets) | au chargement de la session |

IRMS essaie les noms actuels, puis les anciens.

## Règles de lecture

- **Lecture seule.** Les zones sont ouvertes avec `OpenFileMappingW(FILE_MAP_READ)`. IRMS n'utilise jamais `mmap(tagname=...)`, qui créerait une zone vide si le jeu n'est pas lancé.
- **Structures `#pragma pack(4)`**, petit-boutiste. Les chaînes sont des tableaux `char[N]` terminés par zéro ; les booléens font un octet.
- **Lecture cohérente.** Le compteur d'images en tête de zone est lu avant et après la copie ; si le jeu a écrit entre-temps, la copie est refaite.
- **Jeu arrêté.** Si le compteur d'images ne change plus pendant 3 secondes, la connexion est considérée comme perdue, les zones sont refermées et IRMS réessaie toutes les 2 secondes.

## Champs utilisés

| Donnée | Zone et champ | Remarque |
| --- | --- | --- |
| État du jeu | graphics `status` | 0 arrêté, 1 rediffusion, 2 en piste, 3 pause. Seul l'état 2 est enregistré. |
| Voiture | graphics `car_model` | Sert de clé de profil. |
| Circuit, tracé, longueur | static `track`, `track_configuration`, `track_length_m` | |
| Position sur le tour | graphics `npos` | De 0 à 1 ; distance = `npos` × longueur. |
| Régime, rapport | graphics `rpm`, `gear_int` | Rapport brut : 0 marche arrière, 1 point mort, 2 première. |
| Vitesse | physics `speedKmh`, sinon graphics `display_speed_kmh` | La valeur de physics n'est retenue que si elle concorde avec celle de graphics. |
| Gaz, frein | physics `gas`, `brake`, sinon graphics `gas_percent`, `brake_percent` | Physics est utilisée si la zone est vivante et cohérente avec la vitesse de graphics. Valeurs de 0 à 1. |
| Volant | graphics `steering_percent` | De −1 (gauche) à +1 (droite). |
| Position sur le plan | graphics `car_coordinates[i]` pour la voiture du joueur (`car_ids`) | Repli : moyenne des points de contact des pneus de physics. Sans position, le plan n'est pas tracé mais l'analyse fonctionne. |
| Tour valide | graphics `is_valid_lap`, `timing_state.is_invalid` | |
| Stands | graphics `is_in_pit_lane`, `is_in_pit_box`, `car_location` | Un passage par les stands invalide le tour. |
| Temps officiel | graphics `last_laptime_ms` | Utilisé s'il arrive dans les 2,5 s après la ligne et s'il diffère de moins de 1,5 s du temps mesuré. |
| Versions | static `sm_version`, `ac_evo_version` | Affichées dans le diagnostic. |

Le nom du pilote (`driver_name`, `driver_surname`) existe dans la zone graphics. IRMS ne le lit pas.

## Ce qui a été vérifié

- Les emplacements calculés par `irms/layout.py` sont identiques à ceux que donne un compilateur C++ (`offsetof`, `sizeof`) pour les 11 structures et leurs 349 champs. Test : `tests/test_layout.py`.
- Une capture réelle du jeu en version 0.6.2 est décodée avec les bonnes valeurs (Brands Hatch Indy, 1944 m, Dallara EXP, 154 km/h, 4e rapport). Test : `tests/test_evo_reader.py`.
- La lecture de vraies zones mémoire nommées Windows, la perte et la reprise de connexion, et la chaîne complète jusqu'à l'enregistrement d'un tour. Test : `tests/test_windows.py`.

## Ce qui n'a pas été vérifié

- Les versions du jeu postérieures à 0.6.2.
- Le contenu exact des zones dans les menus, en pause et en rediffusion.
- La zone physics sur une vraie session (la capture réelle disponible ne contient que graphics et static). C'est pourquoi les pédales ont un repli sur graphics.
- Le signe des accélérations publiées par le jeu : la décélération affichée est calculée à partir de la vitesse.

## Détection d'un changement de disposition

Le jeu est en accès anticipé. Si une mise à jour ajoute ou retire des champs, toutes les valeurs situées après sont décalées. IRMS contrôle donc chaque image :

- état du jeu dans 0..3, position dans 0..1, rapport, régime et vitesse dans des plages réalistes ;
- pédales entre 0 et 1, absence de nombres flottants dénormalisés ;
- octets des booléens égaux à 0 ou 1 ;
- noms de voiture et de circuit composés de caractères imprimables, longueur de piste entre 100 m et 30 km.

Un échec en piste suspend l'enregistrement et s'affiche dans l'onglet Diagnostic.

**Limites de cette détection.** Dans les tests, tout ajout d'octets avant le champ `car_model` est détecté. Un retrait d'octets, ou une zone dont le début est à zéro, n'est détecté qu'en partie : la zone ressemble alors à un jeu « arrêté » et rien n'est enregistré, sans message explicite. Dans ce cas, l'onglet Diagnostic indique que le jeu est connecté mais jamais « en piste ».

## Mettre à jour la table des champs

Quand la documentation du jeu change :

1. Récupère le nouvel en-tête C++ (il accompagne la documentation ; une copie se trouve dans le projet [acevo-shared-memory](https://github.com/dSyncro/acevo-shared-memory), fichier `src/bindings/source/wrapper.hpp`).
2. Lance `python tools/gen_structs.py chemin/vers/en-tete.hpp` (nécessite `g++` ou `clang++`). Le script réécrit `irms/evo_structs.py` et `tests/fixtures/golden_offsets.json`.
3. Adapte `MIN_SIZES` et les noms de champs dans `irms/evo_reader.py` si nécessaire.
4. Lance les tests, puis vérifie en piste avec `python -m irms doctor`.

L'en-tête lui-même n'est pas distribué dans ce dépôt.

## Outils

- `python -m irms doctor` : essaie de se connecter pendant 3 secondes et affiche un rapport.
- `python -m irms doctor --dump fichier.json` : ajoute une copie des trois zones, nom du pilote effacé. C'est la pièce à joindre à un signalement de compatibilité.
- `python tools/fake_evo.py` (Windows) : publie de fausses zones à partir du simulateur. Options `--car`, `--legacy`, `--speed`. Ne pas l'utiliser pendant que le jeu tourne.

## Sources

- [Documentation Shared Memory du jeu (guide Steam)](https://steamcommunity.com/sharedfiles/filedetails/?id=3707421508)
- [live-telemetry-evo, référence de la mémoire partagée](https://github.com/albertowd/live-telemetry-evo/blob/develop/docs/SHARED_MEMORY.md)
- [acevo-sdk](https://github.com/glebulon/acevo-sdk)
- [acevo-shared-memory](https://github.com/dSyncro/acevo-shared-memory)
