"""Lanceur Windows natif pour le depot IRMSCRC/irms-emu-pro.

Lance directement Engine/Storage/App dans ce processus, sans .bat ni cmd.
Necessite le paquet irms present pendant la compilation. Aucune modification
aux modules de telemetrie ou au serveur existant n'est requise.
"""
import ctypes
import ipaddress
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser


def data_directory():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "IRMS-emu-pro"


def configure_logging():
    directory = data_directory() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[RotatingFileHandler(
            str(directory / "lanceur.log"), maxBytes=1500000, backupCount=3,
            encoding="utf-8")],
        format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
    )
    # En mode windowed, PyInstaller peut fournir stdout/stderr = None.
    # Les rares print du moteur doivent rester inoffensifs et consultables.
    if sys.stdout is None or sys.stderr is None:
        console_log = open(str(directory / "sorties.log"), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = console_log
        if sys.stderr is None:
            sys.stderr = console_log
    return directory


class SingleInstance:
    def __init__(self):
        self.handle = None
        self.kernel = None
        if sys.platform != "win32":
            return
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        handle = kernel.CreateMutexW(None, False, "Local\\IRMS_emu_pro_desktop_launcher")
        last_error = ctypes.get_last_error()
        if not handle:
            raise OSError(last_error, "Impossible de créer le verrou du lanceur.")
        if last_error == 183:
            kernel.CloseHandle(handle)
            raise RuntimeError("IRMS est déjà lancé. Retrouve sa fenêtre avant de le relancer.")
        self.kernel = kernel
        self.handle = handle

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def ipv4_candidates(addresses):
    result = []
    for item in addresses:
        try:
            address = ipaddress.ip_address(item)
        except ValueError:
            continue
        if address.version != 4 or address.is_loopback or address.is_unspecified or address.is_multicast:
            continue
        if address.is_link_local:
            continue
        text = str(address)
        if text not in result:
            result.append(text)
    return result


class Runtime:
    def __init__(self, port=8765, directory=None):
        self.lock = threading.RLock()
        self.directory = Path(directory) if directory is not None else data_directory()
        self.port = port
        self.storage = None
        self.source = None
        self.engine = None
        self.app = None
        self.server = None
        self.http_thread = None
        self.http_failed = None
        self.started = False

    def start(self, demo=False, lan=True):
        # Le verrou evite qu'une fermeture pendant le demarrage laisse un serveur orphelin.
        with self.lock:
            from irms.storage import Storage
            from irms.engine import Engine
            from irms.server import App, make_server
            self.directory.mkdir(parents=True, exist_ok=True)
            try:
                database = "launcher-selftest.sqlite" if demo else "irms.sqlite"
                self.storage = Storage(str(self.directory / database))
                if demo:
                    from irms.simulator import DemoSource
                    self.source = DemoSource("Démo GT3", seed=2)
                else:
                    from irms.evo_reader import EvoSource
                    self.source = EvoSource()
                self.engine = Engine(self.storage, self.source)
                self.app = App(self.engine, lan=lan, lan_write=False, port=self.port)
                self.server = make_server(self.app, "0.0.0.0" if lan else "127.0.0.1")
                self.port = self.server.server_address[1]
                self.app.port = self.port
                self.engine.start()
                def serve():
                    try:
                        self.server.serve_forever(poll_interval=0.2)
                    except Exception as exc:
                        self.http_failed = str(exc)
                        logging.exception("Serveur HTTP interrompu")
                self.http_thread = threading.Thread(target=serve, name="IRMS-HTTP", daemon=True)
                self.http_thread.start()
                self.started = True
                logging.info("Serveur demarre port=%s lan=%s", self.port, lan)
                return self.addresses()
            except Exception:
                logging.exception("Echec du demarrage")
                self._stop_locked()
                raise

    def addresses(self):
        with self.lock:
            if self.app is None:
                return []
            from irms.server import lan_addresses
            addresses = ipv4_candidates(lan_addresses())
            self.app.addresses = addresses
            self.app.hosts.update(addresses)
            return ["http://%s:%d/" % (a, self.port) for a in addresses]

    def pc_url(self):
        return "http://127.0.0.1:%d/" % self.port

    def status(self):
        if self.http_failed:
            return "Serveur arrêté : " + self.http_failed
        if self.source is None:
            return "Démarrage du serveur…"
        state = self.source.state
        return state.get("message") or "Serveur disponible — en attente d’Assetto Corsa EVO."

    def stop(self):
        with self.lock:
            self._stop_locked()

    def _stop_locked(self):
        if self.server is not None:
            try:
                if self.http_thread is not None and self.http_thread.is_alive():
                    self.server.shutdown()
                self.server.server_close()
            except Exception:
                logging.exception("Erreur fermeture HTTP")
        if self.http_thread is not None and self.http_thread.is_alive():
            self.http_thread.join(timeout=3)
        if self.engine is not None:
            try:
                self.engine.stop()
            except Exception:
                logging.exception("Erreur arret moteur")
        elif self.source is not None:
            try:
                self.source.close()
            except Exception:
                logging.exception("Erreur fermeture source")
        if self.storage is not None:
            try:
                self.storage.close()
            except Exception:
                logging.exception("Erreur fermeture base")
        self.storage = self.source = self.engine = self.app = self.server = self.http_thread = None
        self.started = False


def self_test():
    # Test du vrai serveur et des ressources embarquees, mais pas du jeu reel.
    with tempfile.TemporaryDirectory(prefix="irms-exe-test-") as directory:
        runtime = Runtime(port=0, directory=directory)
        try:
            runtime.start(demo=True, lan=False)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for path in ("/", "/style.css", "/app.js", "/api/status"):
                with opener.open(runtime.pc_url() + path.lstrip("/"), timeout=10) as response:
                    if response.status != 200 or not response.read():
                        raise RuntimeError("Ressource embarquée invalide : " + path)
            logging.info("SELF TEST OK : serveur et ressources web")
            return 0
        finally:
            runtime.stop()


def run_window(log_directory):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from irms import APP_NAME, __version__

    window = tk.Tk()
    window.title("%s %s" % (APP_NAME, __version__))
    window.geometry("640x450")
    window.minsize(600, 430)
    window.configure(bg="#edf1f8")
    style = ttk.Style(window)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("TFrame", background="#edf1f8")
    style.configure("TLabel", background="#edf1f8", foreground="#28364c", font=("Segoe UI", 10))
    style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
    style.configure("Small.TLabel", font=("Segoe UI", 9))
    style.configure("TButton", font=("Segoe UI", 10), padding=7)
    frame = ttk.Frame(window, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
    ttk.Label(frame, text="Adresse à ouvrir dans Safari sur ta tablette", style="Small.TLabel").pack(anchor="w", pady=(4, 18))
    selected = tk.StringVar(value="Démarrage…")
    address_box = ttk.Combobox(frame, textvariable=selected, state="readonly", font=("Segoe UI", 12))
    address_box.pack(fill="x", pady=(0, 12))
    status = tk.StringVar(value="Démarrage du serveur local…")
    ttk.Label(frame, textvariable=status, wraplength=550).pack(anchor="w", fill="x", pady=(0, 8))
    ttk.Label(frame, text="PC et tablette sur le même réseau privé. Interface complète en lecture seule sur tablette.\nNe ferme pas cette fenêtre pendant l’utilisation.", style="Small.TLabel", wraplength=550).pack(anchor="w", pady=(0, 14))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    runtime = Runtime()
    events = queue.Queue()
    state = {"ready": False, "closing": False, "urls": [], "last_status": ""}

    def report_error(exc, value, tb):
        logging.error("Erreur interface", exc_info=(exc, value, tb))
        messagebox.showerror("IRMS", "Une erreur est survenue. Consulte les journaux du lanceur.", parent=window)
    window.report_callback_exception = report_error

    def update_addresses(urls):
        previous = selected.get()
        state["urls"] = urls
        address_box["values"] = urls
        selected.set(previous if previous in urls else urls[0] if urls else "Aucune IPv4 locale détectée")
        copy_button.configure(state="normal" if urls else "disabled")

    def copy_address():
        if selected.get() in state["urls"]:
            window.clipboard_clear()
            window.clipboard_append(selected.get())
            status.set("Adresse copiée. Ouvre-la dans Safari sur ta tablette.")

    def refresh_addresses():
        if not state["ready"]:
            return
        def task():
            try:
                events.put(("addresses", runtime.addresses()))
            except Exception as exc:
                logging.exception("Actualisation des adresses")
                events.put(("refresh_error", str(exc)))
        threading.Thread(target=task, name="IRMS-IP", daemon=True).start()

    def open_pc():
        if state["ready"]:
            webbrowser.open(runtime.pc_url())

    def show_logs():
        if sys.platform == "win32":
            os.startfile(str(log_directory))

    def show_licenses():
        dialog = tk.Toplevel(window)
        dialog.title("IRMS — Licences")
        dialog.geometry("700x500")
        content = tk.Text(dialog, wrap="word", font=("Segoe UI", 10))
        content.pack(fill="both", expand=True, padx=12, pady=12)
        base = Path(__file__).resolve().parent
        blocks = []
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            path = base / "licenses" / name
            if not path.exists():
                path = base / name
            if path.exists():
                blocks.append(name + "\n" + path.read_text(encoding="utf-8-sig", errors="replace"))
        content.insert("1.0", "\n\n".join(blocks) or "Consulte les licences incluses dans le dépôt source IRMS.")
        content.configure(state="disabled")

    def close():
        if state["closing"]:
            return
        state["closing"] = True
        status.set("Arrêt du serveur et fermeture des données…")
        for button in (copy_button, pc_button, refresh_button, quit_button):
            button.configure(state="disabled")
        def shutdown():
            runtime.stop()
            events.put(("closed", None))
        threading.Thread(target=shutdown, name="IRMS-Arret", daemon=True).start()

    copy_button = ttk.Button(buttons, text="Copier l’adresse", command=copy_address, state="disabled")
    copy_button.pack(side="left", padx=(0, 8))
    pc_button = ttk.Button(buttons, text="Ouvrir sur ce PC", command=open_pc, state="disabled")
    pc_button.pack(side="left", padx=(0, 8))
    refresh_button = ttk.Button(buttons, text="Actualiser", command=refresh_addresses, state="disabled")
    refresh_button.pack(side="left")
    bottom = ttk.Frame(frame)
    bottom.pack(fill="x", pady=(18, 0))
    ttk.Button(bottom, text="Journaux", command=show_logs).pack(side="left")
    ttk.Button(bottom, text="Licences", command=show_licenses).pack(side="left", padx=8)
    quit_button = ttk.Button(bottom, text="Arrêter et quitter", command=close)
    quit_button.pack(side="right")
    ttk.Label(frame, text="Plusieurs adresses ? Choisis celle du Wi-Fi/Ethernet actif, pas du VPN.", style="Small.TLabel", wraplength=550).pack(anchor="w", pady=(13, 0))
    window.protocol("WM_DELETE_WINDOW", close)

    def boot():
        try:
            events.put(("ready", runtime.start()))
        except Exception as exc:
            events.put(("failed", str(exc)))
    threading.Thread(target=boot, name="IRMS-Demarrage", daemon=True).start()

    def drain():
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "closed":
                    window.destroy()
                    return
                if state["closing"]:
                    continue
                if kind == "ready":
                    state["ready"] = True
                    update_addresses(payload)
                    for button in (pc_button, refresh_button):
                        button.configure(state="normal")
                elif kind == "addresses":
                    update_addresses(payload)
                elif kind == "refresh_error":
                    status.set("Impossible d’actualiser les adresses : " + payload)
                elif kind == "failed":
                    state["ready"] = False
                    selected.set("Serveur non démarré")
                    status.set("Échec : " + payload)
                    messagebox.showerror(
                        "IRMS — démarrage impossible",
                        "Le serveur n’a pas pu démarrer.\n\n" + payload +
                        "\n\nSi le port 8765 est occupé, ferme l’ancienne application ou son .bat.\nLes journaux sont disponibles avec le bouton Journaux.",
                        parent=window,
                    )
        except queue.Empty:
            pass
        if state["ready"] and not state["closing"]:
            message = runtime.status()
            if message != state["last_status"]:
                state["last_status"] = message
                status.set(message)
        window.after(250, drain)
    window.after(100, drain)
    try:
        window.mainloop()
    finally:
        runtime.stop()


def main():
    log_directory = configure_logging()
    if "--self-test" in sys.argv:
        try:
            return self_test()
        except Exception:
            logging.exception("SELF TEST FAILED")
            return 1
    if sys.platform != "win32":
        logging.error("Le lanceur distribue est destine a Windows.")
        return 1
    instance = None
    try:
        instance = SingleInstance()
        run_window(log_directory)
        return 0
    except Exception as exc:
        logging.exception("Echec du lanceur")
        try:
            import tkinter as tk
            from tkinter import messagebox
            popup = tk.Tk()
            popup.withdraw()
            messagebox.showerror("IRMS ému pro", str(exc), parent=popup)
            popup.destroy()
        except Exception:
            pass
        return 1
    finally:
        if instance is not None:
            instance.close()


if __name__ == "__main__":
    sys.exit(main())
