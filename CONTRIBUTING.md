# Contribuer à IRMS ému pro

Merci de ton intérêt. Toutes les contributions sont utiles : un rapport de compatibilité, une correction de texte, une idée, du code.

## Signaler une incompatibilité avec le jeu

Assetto Corsa EVO est en accès anticipé : sa mémoire partagée peut changer d'une version à l'autre. Si IRMS affiche « Données incohérentes » ou n'enregistre plus :

1. Lance le jeu et entre en piste.
2. Double-clique sur `DIAGNOSTIC_EVO.bat` (ou `python -m irms doctor --dump irms-diagnostic.json`).
3. Ouvre un signalement « Compatibilité EVO » et joins le fichier `irms-diagnostic.json`.

La capture efface le nom du pilote. Si la disposition a changé, ouvre le fichier et cherche ton nom avant de l'envoyer.

## Signaler un bug

Ouvre un signalement « Bug » avec : ce que tu as fait, ce que tu attendais, ce qui s'est passé, et le rapport de l'onglet Diagnostic (bouton « Copier le rapport »).

## Proposer du code

### Préparer l'environnement

Il suffit de Python 3.9 ou plus récent. Il n'y a rien à installer.

```
git clone https://github.com/<ton-compte>/irms-emu-pro.git
cd irms-emu-pro
python -m irms demo
python -m unittest discover -s tests -t .
```

Sous Windows, `tools/fake_evo.py` publie de fausses zones mémoire : lance-le dans une fenêtre, puis `python -m irms run --data essai` dans une autre, pour essayer toute la chaîne sans le jeu.

### Règles du projet

- **Aucune dépendance.** Python : bibliothèque standard uniquement. Interface : HTML, CSS et JavaScript simples, sans étape de compilation, sans ressource externe.
- **Compatibilité.** Le code Python doit fonctionner de Python 3.9 à la version actuelle. Le JavaScript doit fonctionner sur Safari 15 (iPad ancien) : pas de syntaxe plus récente.
- **Honnêteté des données.** Une valeur douteuse ne doit jamais être affichée comme sûre. En cas de doute, on suspend l'enregistrement et on explique pourquoi.
- **Lecture seule.** Rien n'est écrit dans la mémoire ou les fichiers du jeu.
- **Vie privée.** Aucune donnée personnelle n'est enregistrée ni exportée ; aucun appel réseau sortant.
- **Tests.** Toute correction arrive avec un test qui échouait avant. La suite doit passer sous Windows et Linux.
- **Langue.** L'interface et la documentation sont en français, à la deuxième personne du singulier. Les identifiants du code sont en anglais.
- **Licences.** Ne copie pas de code venant d'un projet sous licence GPL ou AGPL : il ne pourrait pas être redistribué sous la licence MIT de ce projet. S'inspirer d'une documentation publique est permis ; cite alors la source dans `THIRD_PARTY_NOTICES.md`.
- `irms/evo_structs.py` est généré : ne le modifie pas à la main, relance `tools/gen_structs.py` (voir `docs/CONNECTEUR_EVO.md`).

### Envoyer une proposition

1. Crée une branche à partir de `main`.
2. Fais des commits courts, avec un message qui dit ce qui change et pourquoi.
3. Vérifie que `python -m unittest discover -s tests -t .` passe.
4. Ouvre une pull request en décrivant le changement et la façon dont tu l'as vérifié. Ajoute une ligne au `CHANGELOG.md`.

## Pistes de contribution

- Vérification sur les nouvelles versions du jeu, sur d'autres volants et pédaliers.
- Secteurs officiels du circuit, comparaison avec un tour importé d'un autre pilote.
- Traduction de l'interface.
- Essais sur tablette.

En contribuant, tu acceptes que ta contribution soit publiée sous la licence MIT du projet.
