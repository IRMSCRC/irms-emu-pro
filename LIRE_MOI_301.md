# IRMS ému pro 3.0.1 — réédition des fichiers source

## Ce que tu reçois exactement

Ce ZIP est un PACK DE RECONSTRUCTION : les nouveaux fichiers source et un programme pour assembler le projet complet depuis son dépôt GitHub. Ce n'est pas encore un ZIP autonome contenant toutes les sources du dépôt et ce n'est pas un EXE compilé. Il n'écrase ni ton dossier actuel ni GitHub. Le dossier complet ne sera créé qu'après exécution réussie du programme sur ton PC.

Il s'agit d'une réédition, pas d'une copie octet pour octet du kit précédent. L'ancien programme APPLIQUER_V301.bat n'est pas nécessaire : on fabrique une NOUVELLE copie. Ne mélange pas ce pack et les anciens patchs.

## Utilisation

1. Décompresse tout ce ZIP dans un NOUVEAU dossier, séparé de ton ancien projet.
2. Installe Python 3.12 64 bits avec Tcl/Tk s'il n'est pas déjà disponible. Python sert à reconstruire/ compiler, pas à l'utilisation du binaire final.
3. Double-clique RECONSTRUIRE_COMPLET.bat.
4. Lis le message et tape OUI pour autoriser le téléchargement HTTPS de la base et la création locale. Internet est nécessaire.
5. Attends SOURCE COMPLETE ASSEMBLEE. Le nouveau dossier s'appelle IRMS-emu-pro-3.0.1-complet. Aucun ancien fichier n'est remplacé.
6. Ouvre CE nouveau dossier et double-clique CREER_EXE.bat.
7. Attends TERMINE. L'EXE attendu est IRMS-emu-pro.exe à la racine. Si ECHEC apparaît, ne considère pas un EXE éventuellement présent comme valide.
8. Lance l'EXE, retrouve l'icône près de l'horloge et l'adresse tablette. Le navigateur ne s'ouvre qu'à ta demande.

Ne publie sur GitHub qu'après validation locale. Aucune publication n'est automatisée ici.

Si le téléchargement échoue, le programme affiche l'erreur. Un ZIP GitHub du commit de base peut aussi être fourni avec :

```bat
py -3.12 reconstruire_301.py --archive-base archive-du-commit.zip
```

## Base figée

IRMSCRC/irms-emu-pro, commit 3f53dd8439009a374725c9dc433b6bc1f98d0c8c. Le programme contrôle les empreintes des fichiers de base qu'il transforme et refuse une base différente. Les modules de moteur, stockage, télémétrie et analyses sont conservés à partir de ce dépôt.

## Fonctions du pack

- Icône près de l'horloge, sans grande fenêtre principale ni ouverture automatique du navigateur.
- Petite bulle arrondie/translucide d'URL, copie, masquage après 7 secondes, autres adresses dans le menu. Pas de vrai flou natif Liquid Glass garanti. L'icône du lanceur est une icône système Qt, pas un logo final personnalisé.
- Page Assistant : profil, objectif, constat/hypothèse/exercice, objectif conservé, cache local, bilan exportable.
- Commande de compilation qui place l'EXE à la racine.

## Corrections intégrées à cette réédition après l'audit

- L'objectif général « tours invalides » peut rester disponible même sans référence technique valide.
- Le schéma et la version des plans en cache sont contrôlés avant affichage.
- L'objectif conservé enregistre la date, la référence initiale et le contexte ; un changement de référence est signalé comme constat historique.

## Limites non corrigées / non promises

- Le mélange d'origines ou de pneus dans l'historique suspend encore les objectifs techniques ; aucun filtrage intelligent des tours compatibles n'est ajouté au moteur existant.
- Objectifs et bilans de la page restent dans le navigateur, sans synchronisation PC/iPad. Le bilan est un instantané de profil, pas une séance automatiquement segmentée.
- Aucun chat IA, coaching vocal, contrôle du jeu, validation automatique d'exercice ou mise à jour des réglages du volant.
- Le cache peut être effacé par le navigateur ; il ne remplace pas la base de tours du PC.
- Les tests de ce pack ne valident ni le binaire, ni la compatibilité avec ta version du jeu, ni Safari, ni la latence LAN.
- Le moteur et le lecteur de télémétrie inchangés peuvent avoir leurs propres limites.
- Le téléchargement public GitHub peut échouer si le dépôt n'est plus accessible sans authentification ; le script ne récupère aucun jeton de ton compte.

## Tests

Lire RAPPORT_TESTS.json : seuls les essais explicitement listés ont été exécutés. Le programme de reconstruction et la compilation n'ont pas été exécutés sur le vrai dépôt depuis cet environnement. Le script de compilation prévoit un self-test du serveur/ressources et un test minimal Qt, pas une validation en piste.

## Redistribution

Lire QT_NOTICE_301.txt. Cette livraison est un prototype source à valider, non signé, sans garantie de compatibilité et sans certification juridique des obligations de redistribution de Qt.
