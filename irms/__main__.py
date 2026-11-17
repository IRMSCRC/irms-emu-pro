"""Point d'entree : ``python -m irms``."""
import argparse
import os
import sys
import threading
import time
import webbrowser

from . import APP_NAME, __version__


def default_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "IRMS-emu-pro")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "irms-emu-pro")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m irms",
        description="%s %s - télémétrie et coaching pour Assetto Corsa EVO." % (APP_NAME, __version__))
    parser.add_argument("command", nargs="?", default="run", choices=["run", "demo", "doctor", "version"],
                        help="run : se connecter au jeu (défaut) ; demo : données simulées ; "
                             "doctor : diagnostic de connexion ; version")
    parser.add_argument("--port", type=int, default=8765, help="port du serveur local (défaut : 8765)")
    parser.add_argument("--lan", action="store_true",
                        help="autoriser les appareils du réseau local (iPad) en lecture seule")
    parser.add_argument("--lan-write", action="store_true",
                        help="avec --lan : autoriser aussi les modifications depuis le réseau local")
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("--data", default=None, help="dossier des données (défaut : dossier utilisateur)")
    parser.add_argument("--dump", default=None, metavar="FICHIER",
                        help="avec doctor : écrire une capture mémoire anonymisée dans FICHIER")
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print("%s %s" % (APP_NAME, __version__))
        return 0
    if args.command == "doctor":
        from . import doctor
        return doctor.run(args.dump)

    from .engine import Engine, seed_demo
    from .server import App, make_server
    from .storage import Storage

    data_dir = args.data or default_data_dir()
    demo = args.command == "demo"
    if demo:
        from .simulator import DemoSource
        path = os.path.join(data_dir, "demo.sqlite")
        if not os.path.isdir(data_dir):
            os.makedirs(data_dir)
        for suffix in ("", "-journal", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
        storage = Storage(path)
        print("Préparation des données de démonstration…")
        seed_demo(storage)
        source = DemoSource("Démo GT3", seed=2)
    else:
        from .evo_reader import EvoSource
        storage = Storage(os.path.join(data_dir, "irms.sqlite"))
        source = EvoSource()

    engine = Engine(storage, source)
    app = App(engine, lan=args.lan, lan_write=args.lan_write, port=args.port)
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    try:
        server = make_server(app, host)
    except OSError as exc:
        print("Impossible d'ouvrir le port %d : %s" % (args.port, exc))
        print("Une autre copie d'IRMS est peut-être déjà lancée. Ferme-la, ou choisis un autre port avec --port.")
        return 2
    engine.start()
    url = "http://127.0.0.1:%d/" % args.port
    print("")
    print("  %s %s%s" % (APP_NAME, __version__, "  (mode démo)" if demo else ""))
    print("  Sur ce PC      : %s" % url)
    if args.lan:
        for address in app.addresses:
            print("  Sur l'iPad     : http://%s:%d/?vue=ipad" % (address, args.port))
        if not app.addresses:
            print("  Adresse réseau introuvable : vérifie que le PC est connecté au Wi-Fi ou au réseau.")
    print("  Données        : %s" % data_dir)
    if not demo and sys.platform != "win32":
        print("  Remarque       : Assetto Corsa EVO n'est lisible que sous Windows. Essaie « demo ».")
    print("  Pour arrêter   : Ctrl+C ou ferme cette fenêtre.")
    print("")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        server.server_close()
        storage.close()
        time.sleep(0.05)
    return 0


if __name__ == "__main__":
    sys.exit(main())
