# Méthode de coaching

Ce document explique comment IRMS passe des données aux conseils, pour que chacun puisse juger de leur valeur et les améliorer.

## Principe

La cible n'est pas un pilote idéal. C'est **ton meilleur passage dans chaque virage**, avec la même voiture, sur le même circuit. Les conseils te rapprochent donc de ce que tu as déjà réussi ; ils ne disent pas ce qu'un pilote plus rapide ferait.

Chaque conseil a trois parties, volontairement séparées :

- **Constat** : ce que mesurent les données. Jamais une supposition.
- **Hypothèse** : l'explication la plus probable, présentée comme telle. Elle se vérifie au volant.
- **Exercice** : une seule consigne concrète, à essayer sur quelques tours.

## Étapes du calcul

### 1. Mise à distance égale

Chaque tour est reprojeté sur une grille régulière de distance (un point tous les 2 m environ, entre 300 et 3000 points par tour). Deux tours se comparent alors point par point.

### 2. Tour de référence

Par défaut, le tour de référence est ton meilleur tour valide. Tu peux en choisir un autre dans l'onglet Tours. Tant qu'il n'existe aucun tour valide, le meilleur tour disponible sert de référence provisoire.

### 3. Détection des virages

Sur le tour de référence, la courbure de la trajectoire est calculée à partir de la position de la voiture. Un point appartient à un virage si le rayon est inférieur à 250 m, ou inférieur à 700 m avec une accélération latérale supérieure à 6 m/s² environ. Les zones voisines de même sens sont réunies ; celles de moins de 15 m ou de moins de 15° sont ignorées. Sans position, l'angle du volant remplace la courbure.

La corde est le point de vitesse minimale du virage (ou le point le plus serré si le virage se prend sans ralentir). Le type du virage dépend de cette vitesse : lent (moins de 110 km/h), moyen, rapide (170 km/h et plus), épingle (120° et plus, à moins de 110 km/h).

Chaque virage reçoit un **tronçon** : il commence avant le freinage du virage et finit avant le freinage du suivant. La somme des tronçons couvre tout le tour.

### 4. Mesures par virage

Pour chaque tour valide et chaque tronçon :

| Mesure | Définition |
| --- | --- |
| Début du freinage | Premier point où le frein dépasse 8 %, pour le freinage principal avant la corde. |
| Frein maximal | Plus forte valeur de frein pendant ce freinage. |
| Vitesse à la corde | Vitesse minimale. |
| Reprise des gaz | Premier point où l'accélérateur dépasse 20 % et y reste sur 8 m. |
| Plein gaz | Premier point à 95 % ou plus après la reprise. |
| Levers de pied | Baisses de plus de 30 points de l'accélérateur après la reprise, sans freinage dans les 40 m qui suivent. |
| Roue libre | Temps passé sans gaz ni frein (moins de 5 % chacun). |
| Vitesse de sortie | Vitesse 60 m après la fin du virage. |
| Temps du tronçon | Durée entre l'entrée et la sortie du tronçon. |

Les positions sont affichées en mètres par rapport à la corde (« 84 m avant la corde »).

### 5. Choix de la cible et calcul de la perte

Pour chaque virage, la cible est le tour valide dont le temps de tronçon est le plus court, parmi tes 30 derniers tours valides (plus ton record et le tour de référence). La perte d'un tour est son temps de tronçon moins celui de la cible. Le **meilleur tour théorique** est la somme des meilleurs tronçons ; il n'est jamais affiché plus lent que ton record.

Les conseils portent sur tes 10 derniers tours valides (3 au minimum). Un virage donne lieu à une carte si la perte moyenne atteint 0,08 s, ou si une erreur ponctuelle coûte au moins 0,3 s. Six cartes de virage au plus sont affichées, classées par temps perdu. Les virages où la perte moyenne reste sous 0,04 s sont listés comme points forts.

### 6. Régularité de l'erreur

Un tour « perd » dans un virage si sa perte dépasse 0,05 s ou 1 % du temps du tronçon.

| Étiquette | Condition | Sens |
| --- | --- | --- |
| récurrent | perte sur 60 % des tours ou plus | Habitude à corriger. |
| ponctuel | perte sur 30 % des tours ou moins, dont une d'au moins 0,25 s | Erreur isolée : inutile de changer de technique. |
| variable | entre les deux | Repères pas encore stables. |

La priorité dépend de la perte moyenne : « prioritaire » à partir de 0,20 s, « à travailler » à partir de 0,08 s, « à surveiller » en dessous. Une erreur ponctuelle reste toujours « à surveiller ».

### 7. Recherche de la cause

Les mesures des tours qui perdent sont comparées à celles de la cible. La cause retenue est celle dont l'écart est le plus marqué :

| Cause | Condition |
| --- | --- |
| Perte héritée du virage précédent | Vitesse d'entrée du tronçon inférieure d'au moins 3 km/h. |
| Freinage trop tôt | Début du freinage au moins 6 m plus tôt. |
| Freinage trop tardif | Début au moins 5 m plus tard, avec une vitesse à la corde ou de sortie en baisse d'au moins 2 km/h. |
| Vitesse à la corde trop basse | Au moins 2,5 km/h de moins. |
| Reprise des gaz tardive | Au moins 6 m plus tard. |
| Montée en gaz hésitante | Plein gaz non atteint dans le tronçon, ou atteint au moins 12 m plus tard. |
| Lever de pied en sortie | 0,4 lever de pied de plus en moyenne. |
| Roue libre | Au moins 0,2 s de roue libre en plus. |
| Freinage irrégulier | Écart-type du point de freinage d'au moins 10 m. |
| Sortie lente | Aucune des causes ci-dessus, mais au moins 3 km/h de moins en sortie. |

Si aucune cause ne ressort, la carte le dit (« perte diffuse ») au lieu d'en inventer une.

Quand la perte d'un virage se retrouve dans le suivant (vitesse d'entrée plus basse), elle est rattachée au premier virage : c'est là qu'il faut travailler.

### 8. Conseils généraux

- **Trop de tours invalides** : 30 % ou plus de tours non valides sur au moins 5 tours.
- **Régularité à construire** : écart-type des 10 derniers tours valides d'au moins 0,5 % du temps moyen.
- **Ton meilleur tour est déjà en toi** : meilleur tour théorique plus rapide que le record d'au moins 0,3 s.

### 9. Confiance

« Élevée » avec au moins 8 tours et une erreur récurrente, « moyenne » avec au moins 5 tours, « faible » sinon.

## Adaptation au pédalier

Le réglage « Ton pédalier de frein » change le texte des exercices de freinage :

- **Capteur de position** (pédalier d'origine, par exemple Fanatec CSL Pedals sans cellule de charge) : le repère est la course de la pédale, pas la force.
- **Cellule de charge** : le repère est la pression maximale.

## Aide en direct

L'écran Direct utilise les mêmes virages. La consigne dépend de la position sur le tour par rapport au tour de référence :

| Consigne | Condition |
| --- | --- |
| Accélère | Freinage de référence à plus de 200 m (50 m en sortie du virage précédent). |
| Prépare le freinage | Freinage de référence dans moins de 200 m. |
| Freine | Dans la zone de freinage de la référence. |
| Vise la corde | Entre la fin du freinage et la reprise des gaz de la référence. |
| Sans freiner | Virage que la référence prend sans freiner, à moins de 120 m de la corde. |

L'écart affiché est le temps du tour en cours moins celui du tour de référence au même endroit de la piste.

## Limites

- Les seuils ci-dessus ont été réglés sur des tours simulés. Ils demandent à être confrontés à de vrais tours ; les retours sont bienvenus.
- La méthode ne voit pas la trajectoire en largeur (corde manquée, sortie trop large) : la position sert au plan, pas encore à l'analyse de ligne.
- Elle ne tient pas compte de l'usure des pneus, du carburant ni de la météo : compare des tours faits dans des conditions proches.
- Un conseil reste une hypothèse. Si un exercice dégrade ta sortie de virage, reviens en arrière.

Le code correspondant est dans `irms/analysis.py` et `irms/coaching.py` ; les cas attendus sont décrits dans `tests/test_analysis.py`.
