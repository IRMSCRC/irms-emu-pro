"""Faux Assetto Corsa EVO pour Windows : essayer toute la chaine sans le jeu.

Ce script cree les trois zones de memoire partagee du jeu et y publie des
tours simules. IRMS, lance normalement dans une autre fenetre, les lit
exactement comme s'il s'agissait du jeu.

    Fenetre 1 :  py -3 tools\\fake_evo.py
    Fenetre 2 :  py -3 -m irms run --data essai

Options : --car "Démo Roadster Cup", --legacy (anciens noms de zones),
--speed 4 (temps accelere). Ne jamais le lancer pendant que le vrai jeu
tourne. Les tours enregistres ainsi sont fictifs : utilise --data pour ne
pas les meler a tes vrais tours.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Publie une fausse télémétrie EVO (Windows).")
    parser.add_argument("--car", default="Démo GT3")
    parser.add_argument("--legacy", action="store_true", help="utilise les anciens noms Local\\acpmf_*")
    parser.add_argument("--speed", type=float, default=1.0, help="facteur d'accélération du temps")
    parser.add_argument("--seconds", type=float, default=0.0, help="durée (0 = jusqu'à Ctrl+C)")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Ce script ne fonctionne que sous Windows (mémoire partagée nommée).")
        return 1
    from irms.evo_fake import FakeMaps
    from irms.simulator import CARS, DemoSource, encode_pages

    if args.car not in CARS:
        print("Voiture inconnue. Choix : %s" % ", ".join(sorted(CARS)))
        return 1
    source = DemoSource(args.car, speed=args.speed)
    print("Faux jeu en marche (%s). Lance IRMS dans une autre fenêtre. Ctrl+C pour arrêter." % args.car)
    end = time.monotonic() + args.seconds if args.seconds > 0 else None
    with FakeMaps(legacy_names=args.legacy) as maps:
        try:
            while end is None or time.monotonic() < end:
                frame = source.poll()
                for key, page in zip(("physics", "graphics", "static"), encode_pages(frame)):
                    maps.write(key, page)
                time.sleep(0.003)
        except KeyboardInterrupt:
            pass
    print("Arrêté.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
