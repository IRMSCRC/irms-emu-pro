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
            raise RuntimeError("IRMS est déjà lancé. Retrouve son icône près de l’horloge, éventuellement dans les icônes masquées.")
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
            for path in ("/", "/style.css", "/app.js", "/api/status", "/assistant.html", "/assistant.css", "/assistant.js", "/api/assistant"):
                with opener.open(runtime.pc_url() + path.lstrip("/"), timeout=10) as response:
                    if response.status != 200 or not response.read():
                        raise RuntimeError("Ressource embarquée invalide : " + path)
            logging.info("SELF TEST OK : serveur et ressources web")
            return 0
        finally:
            runtime.stop()


def run_window(log_directory):
    from irms.desktop import run_desktop
    run_desktop(Runtime, log_directory)


def main():
    log_directory = configure_logging()
    if "--ui-smoke-test" in sys.argv:
        try:
            from PySide6.QtWidgets import QApplication, QWidget
            app = QApplication.instance() or QApplication([])
            widget = QWidget()
            widget.show()
            app.processEvents()
            widget.close()
            logging.info("QT SMOKE TEST OK")
            return 0
        except Exception:
            logging.exception("QT SMOKE TEST FAILED")
            return 1
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
