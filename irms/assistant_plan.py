"""Plan explicable issu des cartes existantes. Pas de modele distant."""

def build_plan(overview, coaching, pedals="position"):
    laps = overview.get("laps") or []
    origins = sorted({str(lap["source"]) for lap in laps if lap.get("source")})
    compounds = sorted({str((lap.get("conditions") or {})["compound"]) for lap in laps
                        if lap.get("valid") and (lap.get("conditions") or {}).get("compound")})
    warnings = ["Même voiture et circuit ne garantissent pas les mêmes réglages, pneus ou conditions. Un écart ne prouve pas sa cause."]
    demo = origins == ["demo"]
    if demo: warnings.insert(0, "DÉMONSTRATION : mesures simulées, pas ton pilotage réel.")
    cards = coaching.get("cards") or []
    focus = next((card for card in cards if card.get("id") == "invalid"), None)
    blocked = len(origins) > 1 or len(compounds) > 1 or bool(overview.get("ref_provisional"))
    if len(origins) > 1: warnings.append("Origines multiples : suggestions techniques suspendues.")
    if len(compounds) > 1: warnings.append("Pneus différents dans l'historique : suggestions techniques suspendues.")
    if focus is None and coaching.get("ready") and not blocked:
        choices = [card for card in cards if card.get("corner") is not None and card.get("pattern") == "récurrent"]
        choices.sort(key=lambda card: float(card.get("gain_s") or 0), reverse=True)
        focus = choices[0] if choices else next((card for card in cards if card.get("id") == "consistency"), None)
    if focus:
        focus = {key: focus.get(key) for key in ("id", "title", "observation", "hypothesis", "exercise", "confidence", "frequency", "pattern")}
        focus["validation"] = "Compare le même tronçon après quelques tours valides, sans modifier un second paramètre. Aucun gain n'est garanti."
    else: warnings.append("Pas de priorité suffisamment établie : accumule des tours valides et comparables.")
    return {"version":"3.0.1", "combo":overview.get("combo"), "demo":demo,
            "reference":{"lap_id":overview.get("ref_lap_id"), "provisional":bool(overview.get("ref_provisional"))},
            "context":{"origins":origins,"compounds":compounds}, "warnings":warnings, "focus":focus,
            "stats":overview.get("stats") or {}, "best_ms":overview.get("best_ms"),
            "recent_laps":[lap for lap in laps if lap.get("valid")][-10:],
            "pedal_note":"Le signal de frein est une commande en %, pas une force du pied étalonnée par IRMS."}
