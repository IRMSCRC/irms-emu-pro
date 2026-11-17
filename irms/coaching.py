"""Conseils de pilotage : des faits mesures, une hypothese, un exercice.

Chaque carte suit la meme structure pour rester honnete :

* ``observation`` : ce que disent les chiffres (jamais une supposition) ;
* ``hypothesis`` : l'explication la plus probable, presentee comme telle ;
* ``exercise`` : une consigne concrete a essayer sur quelques tours.

La cible n'est pas un pilote ideal : c'est le meilleur passage du pilote
lui-meme dans chaque virage, avec la meme voiture, sur le meme circuit.
"""
from .analysis import mean, stdev

RECENT = 10
MIN_VALID = 3


def fmt_time(ms):
    if ms is None:
        return "—"
    ms = int(round(ms))
    return "%d:%06.3f" % (ms // 60000, (ms % 60000) / 1000.0)


def _num(value, digits=0):
    text = ("%." + str(digits) + "f") % value
    return text.replace(".", ",")


def _metres(index, step):
    return None if index is None else index * step


def _avg(rows, key, step=None):
    values = [r[key] for r in rows if r.get(key) is not None]
    if not values:
        return None
    value = mean(values)
    return value * step if step else value


def corner_card(corner, target, rows, losses, step, pedals, prev_name=None):
    """Construit la carte d'un virage. ``rows`` : mesures des tours recents."""
    n = len(rows)
    threshold = max(0.05, 0.01 * target["time"])
    lossy = [r for r, loss in zip(rows, losses) if loss > threshold] or rows
    frequency = sum(1 for loss in losses if loss > threshold)
    mean_loss = mean(losses)
    worst = max(losses)
    share = frequency / float(n)
    if share >= 0.6:
        pattern = "récurrent"
    elif share <= 0.3 and worst >= 0.25:
        pattern = "ponctuel"
    else:
        pattern = "variable"
    name = corner["name"]
    apex = corner["apex"] * step

    def rel(index):
        """Distance par rapport a la corde (negative = avant)."""
        return None if index is None else index * step - apex

    t_brake = rel(target["brake_on"])
    y_brake = _avg(lossy, "brake_on", step)
    y_brake = None if y_brake is None else y_brake - apex
    t_gas = rel(target["gas_on"])
    y_gas = _avg(lossy, "gas_on", step)
    y_gas = None if y_gas is None else y_gas - apex
    t_full = rel(target["full_on"])
    y_full = _avg(lossy, "full_on", step)
    y_full = None if y_full is None else y_full - apex
    d_brake = None if t_brake is None or y_brake is None else y_brake - t_brake
    d_gas = None if t_gas is None or y_gas is None else y_gas - t_gas
    d_full = None if t_full is None or y_full is None else y_full - t_full
    d_min = _avg(lossy, "min_speed") - target["min_speed"]
    d_exit = _avg(lossy, "exit_speed") - target["exit_speed"]
    d_coast = _avg(lossy, "coast") - target["coast"]
    lifts = _avg(lossy, "lifts") - target["lifts"]
    brake_points = [r["brake_on"] * step for r in rows if r["brake_on"] is not None]
    spread = stdev(brake_points) if len(brake_points) >= 3 else 0.0
    d_peak = _avg(lossy, "brake_peak") - target["brake_peak"]
    d_entry = _avg(lossy, "seg_entry_speed") - target["seg_entry_speed"]
    full_missing = (target["full_on"] is not None
                    and sum(1 for r in lossy if r["full_on"] is None) * 2 > len(lossy))

    causes = []
    if prev_name and d_entry <= -3.0:
        causes.append((-d_entry / 3.0, "carry"))
    if d_brake is not None and d_brake <= -6.0:
        causes.append((-d_brake / 6.0, "early_brake"))
    if d_brake is not None and d_brake >= 5.0 and (d_min <= -2.0 or d_exit <= -2.0):
        causes.append((d_brake / 5.0 + 0.5, "late_brake"))
    if d_min <= -2.5:
        causes.append((-d_min / 2.5, "over_slow"))
    if d_gas is not None and d_gas >= 6.0:
        causes.append((d_gas / 6.0, "late_gas"))
    elif full_missing:
        causes.append((2.0, "slow_gas"))
    elif d_full is not None and d_full >= 12.0:
        causes.append((d_full / 12.0, "slow_gas"))
    if lifts >= 0.4:
        causes.append((1.0 + lifts, "lift"))
    if d_coast >= 0.2:
        causes.append((d_coast / 0.2, "coast"))
    if spread >= 10.0:
        causes.append((spread / 10.0, "unstable"))
    if not causes and d_exit <= -3.0:
        causes.append((1.0, "slow_exit"))
    causes.sort(reverse=True)
    cause = causes[0][1] if causes else "diffuse"

    where = "%s (%s, %s)" % (name, corner["dir"], corner["kind"])
    travel = (" Avec un pédalier à capteur de position, repère la course de la pédale (pas la force) : "
              "vise toujours la même butée du pied." if pedals == "position" else
              " Avec une cellule de charge, vise la même pression maximale à chaque passage.")
    texts = {
        "early_brake": (
            "Freinage trop tôt",
            "Tu commences à freiner %s m plus tôt que lors de ton meilleur passage, pour une vitesse à la corde "
            "%s." % (_num(-(d_brake or 0)), "équivalente" if d_min > -2.0 else "plus basse de %s km/h" % _num(-d_min)),
            "Tu arrives probablement en roue libre ou tu relâches les freins avant le point de braquage : "
            "la voiture est déjà ralentie bien avant la corde.",
            "Prends un repère fixe (panneau, vibreur, changement de bitume) et recule ton freinage de 5 m par "
            "tour, sans changer ta vitesse à la corde. Arrête dès que tu élargis en sortie." + travel),
        "late_brake": (
            "Freinage trop tardif",
            "Tu freines %s m plus tard que ton meilleur passage, mais ta vitesse à la corde baisse de %s km/h "
            "et ta sortie de %s km/h." % (_num(d_brake or 0), _num(-d_min), _num(-d_exit)),
            "Le freinage tardif te fait probablement manquer le point de corde : le temps gagné à l'entrée est "
            "reperdu, et plus encore, à la sortie.",
            "Avance ton freinage de 5 à 10 m et concentre-toi sur la vitesse de sortie. Le bon repère est celui "
            "qui te laisse remettre les gaz tôt, pas celui qui freine le plus tard."),
        "over_slow": (
            "Vitesse à la corde trop basse",
            "Ta vitesse minimale est %s km/h plus basse que lors de ton meilleur passage (%s contre %s km/h)."
            % (_num(-d_min, 1), _num(_avg(lossy, "min_speed")), _num(target["min_speed"])),
            "Tu ralentis probablement plus que nécessaire : freinage maintenu trop longtemps ou trop fort "
            "en fin de zone.",
            "Garde le même point de freinage, mais relâche les freins plus progressivement et un peu plus tôt. "
            "Vise +2 km/h à la corde par série de trois tours."),
        "late_gas": (
            "Reprise des gaz tardive",
            "Tu remets les gaz %s m plus tard que lors de ton meilleur passage ; ta vitesse de sortie perd "
            "%s km/h." % (_num(d_gas or 0), _num(max(0.0, -d_exit))),
            "Tu attends probablement que la voiture soit droite avant d'accélérer, ou ta trajectoire t'oblige "
            "à patienter (corde prise trop tôt).",
            "Cherche le moment où tu commences à débraquer : c'est là que les gaz doivent revenir, "
            "progressivement. Si la voiture élargit, retarde légèrement ton point de corde plutôt que les gaz."),
        "carry": (
            "Pénalisé par la sortie de %s" % (prev_name or "du virage précédent"),
            "Tu abordes ce tronçon %s km/h moins vite que lors de ton meilleur passage."
            % _num(-d_entry),
            "La perte vient probablement de la sortie de %s, qui se prolonge ici : ce virage n'est pas "
            "forcément en cause." % (prev_name or "du virage précédent"),
            "Travaille d'abord la sortie de %s. Réévalue ce virage ensuite."
            % (prev_name or "du virage précédent")),
        "slow_gas": (
            "Montée en gaz hésitante",
            ("Tu n'atteins pas le plein gaz avant la fin du tronçon, alors que ton meilleur passage y parvient "
             "%s m après la corde ; ta vitesse de sortie perd %s km/h."
             % (_num(t_full or 0), _num(max(0.0, -d_exit)))) if full_missing else
            "Tu atteins le plein gaz %s m plus tard que lors de ton meilleur passage." % _num(d_full or 0),
            "L'accélération est probablement dosée trop prudemment une fois la corde passée.",
            "Une fois les gaz repris, pousse la pédale de façon continue jusqu'au fond en débraquant. "
            "Un seul mouvement, sans palier."),
        "lift": (
            "Gaz repris trop tôt, puis relâchés",
            "Tu relâches l'accélérateur en sortie sur la plupart des tours concernés (en moyenne %s fois par "
            "passage), ce que tu ne fais pas sur ton meilleur passage." % _num(_avg(lossy, "lifts"), 1),
            "Tu accélères probablement avant que la voiture soit bien placée, puis tu dois corriger.",
            "Attends un instant de plus avant de reprendre les gaz, puis ne les relâche plus. "
            "Une reprise un peu plus tardive mais définitive est plus rapide qu'une reprise corrigée."),
        "coast": (
            "Trop de roue libre",
            "Tu passes %s s de plus sans frein ni gaz que lors de ton meilleur passage." % _num(d_coast, 2),
            "Il y a probablement un temps mort entre la fin du freinage et la reprise des gaz.",
            "Enchaîne : fin de freinage progressive jusqu'à la corde, puis gaz immédiatement. "
            "À aucun moment les deux pieds ne doivent être au repos dans ce virage."),
        "unstable": (
            "Repère de freinage instable",
            "Ton point de freinage varie de ±%s m d'un tour à l'autre." % _num(spread),
            "Tu n'as probablement pas de repère visuel fixe pour ce freinage.",
            "Choisis un repère précis et tiens-le cinq tours de suite, même s'il est prudent. "
            "Ne le recule qu'une fois régulier." + travel),
        "slow_exit": (
            "Sortie lente",
            "Ta vitesse de sortie est %s km/h plus basse que lors de ton meilleur passage." % _num(-d_exit, 1),
            "La perte se construit probablement sur l'ensemble du virage (trajectoire) plus que sur un geste précis.",
            "Compare ta trajectoire à celle de ton meilleur tour sur le plan : cherche une corde un peu plus "
            "tardive pour ouvrir la sortie."),
        "diffuse": (
            "Perte de temps diffuse",
            "Tu perds du temps ici sans écart net sur le freinage, la vitesse à la corde ou la reprise des gaz.",
            "La perte vient probablement de petits écarts cumulés ou de la trajectoire, que ces mesures ne voient pas.",
            "Refais ce virage en te concentrant sur un seul élément à la fois : d'abord le point de freinage, "
            "puis la corde, puis la sortie."),
    }
    title, observation, hypothesis, exercise = texts[cause]
    if mean_loss >= 0.20:
        severity = "prioritaire"
    elif mean_loss >= 0.08:
        severity = "à travailler"
    else:
        severity = "à surveiller"
    if pattern == "ponctuel":
        severity = "à surveiller"
    evidence = []

    def add(label, you, goal, unit, digits=0):
        if you is not None and goal is not None:
            evidence.append({"label": label, "you": round(you, digits + 1), "target": round(goal, digits + 1),
                             "unit": unit, "kind": "value"})

    def add_rel(label, you, goal):
        """Position par rapport a la corde ; ``None`` cote pilote = jamais atteint."""
        if goal is not None:
            evidence.append({"label": label, "you": None if you is None else round(you, 1),
                             "target": round(goal, 1), "unit": "m", "kind": "rel"})

    if y_brake is not None:
        add_rel("Début du freinage", y_brake, t_brake)
    add("Vitesse à la corde", _avg(lossy, "min_speed"), target["min_speed"], "km/h")
    if y_gas is not None:
        add_rel("Reprise des gaz", y_gas, t_gas)
    if cause == "slow_gas" or "slow_gas" in [c[1] for c in causes[:3]]:
        add_rel("Plein gaz", None if full_missing else y_full, t_full)
    add("Vitesse de sortie", _avg(lossy, "exit_speed"), target["exit_speed"], "km/h")
    if abs(d_peak) >= 0.08 and target["brake_peak"] > 0:
        add("Frein maximal", 100 * _avg(lossy, "brake_peak"), 100 * target["brake_peak"], "%")
    confidence = "élevée" if n >= 8 and share >= 0.6 else "moyenne" if n >= 5 else "faible"
    plural = "s" if frequency > 1 else ""
    if pattern == "ponctuel":
        lead = ("Dans %s, tu es régulier sauf sur %d tour%s sur %d, où tu perds jusqu'à %s s par rapport à ton "
                "meilleur passage. Sur ce%s tour%s," % (where, frequency, plural, n, _num(worst, 2),
                                                         "s" if frequency > 1 else "", plural))
        observation = observation[0].lower() + observation[1:]
        exercise = "Erreur isolée : inutile de changer ta technique. " + exercise
    else:
        lead = ("Sur tes %d derniers tours valides, tu perds en moyenne %s s dans %s par rapport à ton meilleur "
                "passage (%d tour%s sur %d)." % (n, _num(mean_loss, 2), where, frequency, plural, n))
    return {
        "id": "corner-%d" % corner["index"],
        "corner": corner["index"],
        "where": where,
        "title": "%s : %s" % (name, title.lower()),
        "cause": cause,
        "also": [c[1] for c in causes[1:3]],
        "severity": severity,
        "pattern": pattern,
        "gain_s": round(mean_loss, 3),
        "worst_s": round(worst, 3),
        "frequency": [frequency, n],
        "observation": lead + " " + observation,
        "hypothesis": hypothesis,
        "exercise": exercise,
        "entry_delta": round(d_entry, 1),
        "evidence": evidence,
        "confidence": confidence,
        "focus": [corner["seg_start"] * step, corner["seg_end"] * step],
    }


def global_cards(laps, valid_times, best_ms, theoretical_ms, weak_names):
    cards = []
    total = len(laps)
    invalid = total - len(valid_times)
    if total >= 5 and invalid / float(total) >= 0.3:
        cards.append({
            "id": "invalid", "corner": None, "severity": "prioritaire", "pattern": "global",
            "title": "Trop de tours invalides",
            "observation": "%d de tes %d tours ne sont pas valides (limites de piste, stands, interruption)."
                           % (invalid, total),
            "hypothesis": "Tu roules probablement au-dessus de ta marge de sécurité actuelle.",
            "exercise": "Roule cinq tours à 95 % : aucun écart de piste, même au prix de quelques dixièmes. "
                        "La vitesse revient ensuite d'elle-même.",
            "evidence": [], "confidence": "élevée", "gain_s": None, "focus": None})
    recent = valid_times[-RECENT:]
    if len(recent) >= 5:
        spread = stdev(recent)
        avg = mean(recent)
        if spread / avg >= 0.005:
            cards.append({
                "id": "consistency", "corner": None, "severity": "à travailler", "pattern": "global",
                "title": "Régularité à construire",
                "observation": "Tes %d derniers tours valides varient de ±%s s autour de %s."
                               % (len(recent), _num(spread / 1000.0, 2), fmt_time(avg)),
                "hypothesis": "Tes repères changent probablement d'un tour à l'autre.",
                "exercise": "Fais une série de cinq tours en visant le même temps à trois dixièmes près, "
                            "sans chercher le record. Fixe un repère de freinage par virage.",
                "evidence": [], "confidence": "moyenne", "gain_s": None, "focus": None})
    if best_ms and theoretical_ms and best_ms - theoretical_ms >= 300:
        cards.append({
            "id": "ideal", "corner": None, "severity": "à surveiller", "pattern": "global",
            "title": "Ton meilleur tour est déjà en toi",
            "observation": "En assemblant tes meilleurs passages dans chaque virage, tu obtiens %s, soit %s s "
                           "de mieux que ton record (%s)." % (fmt_time(theoretical_ms),
                                                             _num((best_ms - theoretical_ms) / 1000.0, 2),
                                                             fmt_time(best_ms)),
            "hypothesis": "Ce temps n'exige rien de nouveau : seulement de reproduire dans un même tour ce que "
                          "tu as déjà réussi séparément.",
            "exercise": "Travaille d'abord %s, puis enchaîne des tours complets."
                        % (", ".join(weak_names[:2]) if weak_names else "les virages où tu es le moins régulier"),
            "evidence": [], "confidence": "moyenne", "gain_s": round((best_ms - theoretical_ms) / 1000.0, 3),
            "focus": None})
    return cards
