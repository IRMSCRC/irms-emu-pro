# Publier le projet sur GitHub

Ce guide s'adresse à la personne qui met le projet en ligne pour la première fois. Il avance une action à la fois. Il utilise GitHub Desktop, qui évite la ligne de commande. L'interface de GitHub Desktop et de GitHub est en anglais : les noms des boutons sont donc cités en anglais.

Durée : environ 15 minutes.

## Avant de commencer

1. Vérifie que l'application fonctionne chez toi (voir `INSTALLATION_WINDOWS.txt`). Publier un projet que tu as vu tourner est plus confortable.
2. Vérifie que le dossier du projet ne contient ni fichier `.sqlite` ni `irms-diagnostic.json`. Le fichier `.gitignore` les écarte déjà, mais un coup d'œil ne coûte rien : ces fichiers sont tes données.

## Partie 1 : préparer les fichiers

### Étape 1 : choisir le nom affiché dans la licence

Ouvre le fichier `LICENSE` avec le Bloc-notes. La deuxième ligne utile est :

```
Copyright (c) 2026 Les contributeurs d'IRMS ému pro
```

Tu peux la laisser telle quelle, ou la remplacer par ton nom ou ton pseudo. Enregistre.

La licence MIT autorise chacun à utiliser, modifier et redistribuer le code, à condition de conserver cette mention. Si tu préfères une autre licence, c'est le moment d'en changer, avant la première publication.

### Étape 2 : mettre l'adresse de ton dépôt

Dans `CONTRIBUTING.md`, remplace `<ton-compte>` par ton nom d'utilisateur GitHub. Enregistre.

## Partie 2 : créer le dépôt

### Étape 3 : créer un compte GitHub

Si tu n'en as pas, crée-le sur [github.com](https://github.com/signup).

### Étape 4 : installer GitHub Desktop

Télécharge-le sur [desktop.github.com](https://desktop.github.com/), installe-le, puis connecte-toi avec ton compte GitHub.

### Étape 5 : déclarer le dossier

1. Dans GitHub Desktop, ouvre le menu **File**, puis **Add local repository** (raccourci Ctrl+O).
2. Clique sur **Choose…** et sélectionne le dossier du projet (celui qui contient `README.md`).
3. GitHub Desktop signale que ce dossier n'est pas encore un dépôt Git et propose d'en créer un : clique sur le lien **create a repository**.
4. Dans la fenêtre qui s'ouvre :
   - **Name** : `irms-emu-pro` ;
   - laisse **Initialize this repository with a README** décoché ;
   - laisse **Git ignore** et **License** sur **None** (le projet fournit déjà ces fichiers).
5. Clique sur **Create repository**.

### Étape 6 : vérifier le premier enregistrement

GitHub Desktop crée un premier enregistrement (« commit ») avec les fichiers du dossier. Ouvre l'onglet **History** : tu dois y voir une ligne, et la liste des fichiers à droite.

Si des fichiers apparaissent encore dans l'onglet **Changes**, écris un court message dans le champ **Summary** (par exemple `IRMS ému pro 3.0.0`), puis clique sur **Commit to main**.

Contrôle dans la liste qu'aucun fichier `.sqlite` ni `irms-diagnostic.json` n'est présent.

### Étape 7 : publier

1. Clique sur **Publish repository**, en haut.
2. **Keep this code private** : laisse coché si tu veux d'abord vérifier le résultat en privé (conseillé). Tu pourras rendre le dépôt public ensuite.
3. Clique sur **Publish repository**.
4. Menu **Repository**, puis **View on GitHub** : le dépôt s'ouvre dans ton navigateur.

## Partie 3 : vérifier en ligne

### Étape 8 : regarder la page d'accueil

Le fichier `README.md` s'affiche, avec les captures d'écran. Si une image manque, vérifie que le dossier `docs/images` a bien été envoyé.

### Étape 9 : regarder les tests automatiques

Ouvre l'onglet **Actions**. Un contrôle nommé « Tests » se lance à chaque envoi : il exécute les tests sous Windows et Linux, avec trois versions de Python.

- Coche verte : tout passe.
- Croix rouge : clique dessus pour lire le journal.

Ces tests ont été exécutés avant la publication sur une machine Linux et avec un Python Windows, mais **jamais encore sur GitHub** : la première exécution est donc la vraie vérification de ce fichier de configuration. En cas d'échec, ouvre un signalement avec le journal, ou corrige `.github/workflows/ci.yml`.

### Étape 10 : rendre le dépôt public

Quand tout te convient : onglet **Settings**, tout en bas, zone **Danger Zone**, **Change repository visibility**, puis **Make public**.

## Partie 4 : réglages conseillés

Chaque réglage est indépendant ; fais-les dans l'ordre qui te convient.

### Description et mots-clés

Sur la page d'accueil du dépôt, clique sur la roue dentée à côté de **About**. Propositions :

- Description : `Coach de pilotage local pour Assetto Corsa EVO : plan du circuit, repères de freinage, analyse par virage et conseils, adaptés à chaque voiture.`
- Topics : `assetto-corsa-evo`, `sim-racing`, `telemetry`, `python`, `coaching`.

### Signalement privé des failles

Le fichier `SECURITY.md` demande de signaler les failles en privé. Pour que ce soit possible : **Settings**, section **Security and quality** de la colonne de gauche, **Advanced Security**, puis **Enable** à droite de **Private vulnerability reporting** ([documentation GitHub](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)).

### Discussions

**Settings**, **General**, section **Features**, coche **Discussions**. Les questions d'utilisation y ont mieux leur place que dans les signalements de bogue.

### Protéger la branche principale

Quand d'autres personnes contribuent : **Settings**, **Rules**, **Rulesets**, crée une règle sur `main` qui exige une pull request et le succès du contrôle « Tests ».

## Partie 5 : publier une version téléchargeable

La plupart des joueurs ne connaissent pas Git. Une « release » leur donne un fichier ZIP à télécharger.

1. Sur la page du dépôt, colonne de droite, clique sur **Releases**, puis **Create a new release**.
2. **Choose a tag** : tape `v3.0.0`, puis **Create new tag**.
3. **Release title** : `IRMS ému pro 3.0.0`.
4. Dans la description, colle la section 3.0.0 de `CHANGELOG.md`.
5. Glisse le fichier `IRMS-emu-pro-3.0.0.zip` dans la zone **Attach binaries**.
6. Clique sur **Publish release**.

## Par la suite

### Publier une modification

1. Modifie les fichiers.
2. Lance les tests : `python -m unittest discover -s tests -t .`
3. Dans GitHub Desktop, onglet **Changes** : écris un message court, clique sur **Commit to main**, puis sur **Push origin**.

### Publier une nouvelle version

1. Change le numéro dans `irms/__init__.py` (`__version__`). C'est le seul endroit : `pyproject.toml` le lit à cet emplacement.
2. Ajoute une section dans `CHANGELOG.md`.
3. Envoie la modification, puis crée une release avec le nouveau numéro.

Numérotation : le premier chiffre change quand le format des données ou l'usage change de façon incompatible, le deuxième pour une nouveauté, le troisième pour une correction.

### Quand le jeu est mis à jour

Lance `DIAGNOSTIC_EVO.bat` en piste. Si le rapport signale un problème, suis `docs/CONNECTEUR_EVO.md`, section « Mettre à jour la table des champs ».

### Recevoir des contributions

Les modèles de signalement et de pull request sont dans `.github/`. Avant d'accepter une contribution, vérifie que le contrôle « Tests » est vert et qu'aucun code d'un projet sous licence GPL ou AGPL n'a été copié : il ne pourrait pas être redistribué sous la licence MIT de ce projet. Voir aussi `CONTRIBUTING.md` et `THIRD_PARTY_NOTICES.md`.
