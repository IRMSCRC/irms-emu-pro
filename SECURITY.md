# Sécurité

## Modèle de sécurité

IRMS ému pro est un serveur web **local**. Il n'a ni compte, ni mot de passe, ni chiffrement : il est conçu pour un PC personnel et un réseau domestique de confiance.

- Par défaut, il n'écoute que sur `127.0.0.1` : seul ce PC peut l'ouvrir.
- Avec `--lan` (fichier `DEMARRER_IPAD.bat`), il écoute sur le réseau local. Les autres appareils peuvent **lire** (direct, tours, conseils) mais toute modification ou suppression est refusée.
- Avec `--lan-write`, les appareils du réseau peuvent aussi modifier. À n'utiliser que sur un réseau où tu fais confiance à tous les appareils.
- L'en-tête `Host` est contrôlé (protection contre le DNS rebinding), l'origine des requêtes d'écriture aussi, et les écritures exigent `Content-Type: application/json` (un formulaire d'un autre site ne peut pas en envoyer).
- L'interface ne charge aucune ressource externe ; une politique de sécurité du contenu l'impose.
- L'application lit la mémoire partagée du jeu en lecture seule. Elle n'écrit rien dans le jeu et ne modifie aucun de ses fichiers.

Ne redirige jamais le port d'IRMS vers Internet et n'utilise pas `--lan` sur un Wi-Fi public.

## Données personnelles

Rien n'est envoyé sur Internet. Le nom du pilote publié par le jeu n'est jamais enregistré, ni exporté, ni inclus dans le rapport de diagnostic. La capture produite par `doctor --dump` efface les champs du nom à leur emplacement connu ; si la disposition mémoire du jeu a changé, l'outil prévient qu'il faut vérifier le fichier avant de le partager.

## Signaler une faille

N'ouvre pas de signalement public pour une faille. Utilise l'onglet **Security and quality** du dépôt (nommé **Security** sur certaines versions de GitHub), puis **Report a vulnerability** (signalement privé GitHub). Décris le scénario, la version d'IRMS et, si possible, une façon de reproduire. Une réponse est donnée dès que possible ; ce projet est maintenu bénévolement.

## Versions suivies

Seule la dernière version publiée reçoit des correctifs.
