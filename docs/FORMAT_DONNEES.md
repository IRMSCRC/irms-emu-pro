# Formats de données

Tout est enregistré sur ton ordinateur. Rien n'est envoyé ailleurs.

## Emplacement

| Système | Dossier par défaut |
| --- | --- |
| Windows | `%LOCALAPPDATA%\IRMS-emu-pro` |
| Linux, macOS | `~/.local/share/irms-emu-pro` |

Le dossier contient `irms.sqlite` (tes tours) et, si tu as lancé la démonstration, `demo.sqlite` (tours simulés, séparés des tiens). L'option `--data chemin` choisit un autre dossier.

**Sauvegarde** : ferme IRMS, puis copie `irms.sqlite`. **Remise à zéro** : ferme IRMS, puis supprime ce fichier.

## Base SQLite

Version du schéma : 1 (`PRAGMA user_version`).

### Table `combos` : un profil par voiture et circuit

| Colonne | Type | Contenu |
| --- | --- | --- |
| `id` | entier | Identifiant. |
| `car` | texte | Voiture, telle que publiée par le jeu. |
| `track`, `config` | texte | Circuit et tracé. |
| `track_length` | réel | Longueur du tour en mètres. |
| `created_at` | texte | Date de création. |
| `ref_lap_id` | entier ou vide | Tour de référence choisi à la main ; vide = meilleur tour valide. |
| `corner_names` | texte JSON | Noms de virage personnalisés : `{"position de la corde en m": "nom"}`. |

Le quadruplet voiture, circuit, tracé, longueur est unique.

### Table `laps` : un tour

| Colonne | Type | Contenu |
| --- | --- | --- |
| `id`, `combo_id` | entier | Identifiant, profil. |
| `created_at` | texte | Date et heure locales. |
| `time_ms` | entier | Temps retenu, en millisecondes. |
| `own_ms` | entier | Temps mesuré par IRMS au passage de la ligne. |
| `valid` | 0 ou 1 | Validité. |
| `reason` | texte | Motif d'invalidité, vide sinon. |
| `time_source` | texte | `jeu` (temps officiel) ou `mesure` (temps d'IRMS). |
| `source` | texte | `evo`, `demo` ou `import`. |
| `has_pos` | 0 ou 1 | Le tour contient la position de la voiture. |
| `n` | entier | Nombre d'échantillons. |
| `meta` | texte JSON | Version du jeu, session, températures, gomme, secteurs. |
| `data` | binaire | Voies de télémétrie compressées (voir ci-dessous). |

### Table `settings`

Paires clé et valeur. Clé actuelle : `pedals` (`position` ou `loadcell`).

### Format de la colonne `data`

Le contenu est compressé avec zlib. Une fois décompressé :

1. une ligne JSON terminée par un saut de ligne : `{"channels": ["d", "t", ...], "n": 1234}` ;
2. pour chaque voie, dans l'ordre annoncé, `n` nombres flottants de 32 bits petit-boutistes.

## Voies de télémétrie

| Voie | Unité | Contenu |
| --- | --- | --- |
| `d` | m | Distance depuis la ligne. |
| `t` | s | Temps depuis le début du tour. |
| `speed` | km/h | Vitesse. |
| `gas` | 0 à 1 | Accélérateur. |
| `brake` | 0 à 1 | Frein. |
| `steer` | −1 à +1 | Volant (négatif à gauche). |
| `gear` | entier | Rapport : −1 marche arrière, 0 point mort, 1 première. |
| `rpm` | tr/min | Régime moteur. |
| `glat` | g | Accélération latérale publiée par le jeu (signe non vérifié ; non utilisée par l'analyse). |
| `x`, `z` | m | Position sur le plan du circuit ; 0 si indisponible. |

## Export et import d'un tour

### JSON : `irms-tour-<id>.irmslap.json`

C'est le format d'échange : un tour exporté peut être importé dans une autre installation d'IRMS, par exemple pour comparer tes tours avec ceux d'un ami **sur la même voiture et le même circuit**.

```json
{
  "format": "irms-lap",
  "version": 1,
  "app_version": "3.0.0",
  "car": "…",
  "track": "…",
  "config": "…",
  "track_length": 3544.0,
  "time_ms": 80923,
  "own_ms": 80921,
  "valid": true,
  "reason": "",
  "time_source": "jeu",
  "has_pos": true,
  "created_at": "2026-11-17 14:02:11",
  "meta": {"game_version": "…", "session": "…", "air_temp": 22.0, "road_temp": 30.0, "compound": "…", "sectors": [26.1, 27.4, 27.4]},
  "channels": {"d": [], "t": [], "speed": [], "gas": [], "brake": [], "steer": [], "gear": [], "rpm": [], "glat": [], "x": [], "z": []}
}
```

Contrôles à l'import : champ `format` égal à `irms-lap`, les 11 voies présentes et de même longueur, 40 à 200 000 échantillons, longueur de piste de 100 m à 30 km, temps de 15 s à 1 h, fichier de 32 Mo au plus. Le tour importé rejoint le profil de sa voiture et de son circuit, avec la source `import`. Le fichier ne contient pas ton nom.

### CSV : `irms-tour-<id>.csv`

Pour un tableur ou un autre outil d'analyse. Séparateur virgule, point décimal, une ligne par échantillon :

```
distance_m,temps_s,vitesse_kmh,gaz,frein,volant,rapport,regime,g_lateral,x,z
```

Le CSV ne se réimporte pas.

## API HTTP locale

Le serveur écoute sur `http://127.0.0.1:8765` (option `--port`). Les réponses sont en JSON ; une erreur renvoie `{"error": "message"}` avec le code HTTP correspondant.

### Lecture

| Méthode et chemin | Réponse |
| --- | --- |
| `GET /api/status` | Version, mode, état de la connexion au jeu. |
| `GET /api/live` | Flux temps réel (Server-Sent Events). |
| `GET /api/live.json` | Dernier état temps réel, en une fois. |
| `GET /api/combos` | Liste des profils. |
| `GET /api/combos/<id>` | Tours, record, meilleur tour théorique, secteurs. |
| `GET /api/combos/<id>/track?lap=<id>` | Plan, virages, courbes de la référence et du tour demandé. |
| `GET /api/combos/<id>/coaching` | Cartes de conseil et points forts. |
| `GET /api/settings` | Réglages. |
| `GET /api/doctor` | Rapport de diagnostic. |
| `GET /api/laps/<id>/export?format=json` ou `csv` | Fichier du tour. |

### Écriture

| Méthode et chemin | Corps JSON | Effet |
| --- | --- | --- |
| `POST /api/combos/<id>/reference` | `{"lap_id": 12}` ou `{"lap_id": null}` | Choisit le tour de référence, ou revient au meilleur tour. |
| `POST /api/combos/<id>/corners` | `{"names": {...}}` | Renomme des virages. |
| `POST /api/laps/<id>/valid` | `{"valid": true}` | Change la validité d'un tour. |
| `POST /api/import` | un tour `irms-lap` | Importe un tour. |
| `POST /api/settings` | `{"pedals": "position"}` | Change un réglage. |
| `POST /api/demo/car` | `{"car": "…"}` | Mode démo : change de voiture. |
| `DELETE /api/laps/<id>` | | Supprime un tour. |
| `DELETE /api/combos/<id>` | | Supprime un profil et ses tours. |

### Protections

- Par défaut, le serveur n'écoute que sur l'ordinateur lui-même. `--lan` l'ouvre au réseau local (pour la tablette) en lecture seule ; `--lan-write` autorise aussi les modifications depuis le réseau.
- Les écritures exigent l'en-tête `Content-Type: application/json` (sinon 415).
- Une requête dont l'en-tête `Host` ne désigne pas le serveur est refusée (403), de même qu'une écriture venant d'une autre origine web (403).
- Il n'y a pas de mot de passe : n'utilise `--lan` que sur un réseau de confiance, jamais sur un réseau public.

Cette API est interne à l'application : elle peut changer d'une version à l'autre. Les formats de fichier `irms-lap` et CSV sont, eux, versionnés.
