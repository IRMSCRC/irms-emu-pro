# Journal des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et les numéros suivent le [versionnage sémantique](https://semver.org/lang/fr/).

## [3.0.0] - 2026-11-17

Première version publiée. Le code a été entièrement réécrit et vérifié pour être partagé.

### Ajouté

- Connecteur Assetto Corsa EVO fondé sur la disposition mémoire documentée du jeu, vérifiée champ par champ contre un compilateur C++ et contre une capture réelle du jeu (0.6.2).
- Contrôles de cohérence : si les données du jeu ne sont pas plausibles, l'enregistrement est suspendu et le problème est expliqué dans l'onglet Diagnostic.
- Détection automatique de la voiture, du circuit et du tracé ; un profil par combinaison.
- Position de la voiture lue dans le jeu : le plan du circuit vient de la trajectoire réelle.
- Détection des virages par courbure, tronçon par virage, meilleur tour théorique, régularité.
- Coaching par virage (constat, hypothèse, exercice), distinction récurrent / variable / ponctuel, report d'une perte sur le virage suivant, adaptation au type de pédalier.
- Aide en direct : prochain virage, consigne, écart au tour de référence.
- Tour de référence au choix, validation manuelle, export JSON et CSV, import.
- Vue tablette en lecture seule sur le réseau local.
- Mode démonstration avec deux voitures simulées.
- Diagnostic (`python -m irms doctor`) avec capture mémoire anonymisée.
- Faux jeu pour Windows (`tools/fake_evo.py`) pour essayer toute la chaîne sans le jeu.
- 130 tests automatiques, intégration continue Windows et Linux.
- Protections du serveur local : écoute locale par défaut, contrôle de l'en-tête Host et de l'origine, écritures refusées depuis le réseau, politique de sécurité du contenu.

### Modifié

- Interface refaite (thème clair et sombre, style « verre »), sans aucune ressource externe.
- Les données sont rangées dans le dossier utilisateur et non plus dans le dossier du programme.

### Versions antérieures

Les versions 1.0, 2.0 et 2.1 étaient des versions de travail privées. Elles n'ont pas été publiées.
