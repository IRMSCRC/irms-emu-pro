"""IRMS 3.0.1 : bulle mobile, position conservee et reduction dans la barre des taches.
Syntaxe et calcul de position verifies ; interface Windows reelle non executee ici.
"""
import logging
import os
import queue
import threading
import webbrowser


def fit_position(x, y, width, height, areas):
    """areas contient des rectangles (x, y, largeur, hauteur), hors barre des taches."""
    if not areas:
        return x, y
    def overlap(area):
        ax, ay, aw, ah = area
        return max(0, min(x + width, ax + aw) - max(x, ax)) * max(0, min(y + height, ay + ah) - max(y, ay))
    target = max(areas, key=overlap)
    if overlap(target) == 0:
        target = areas[0]
    ax, ay, aw, ah = target
    return (max(ax, min(x, ax + max(0, aw - width))),
            max(ay, min(y, ay + max(0, ah - height))))


def run_desktop(runtime_factory, log_directory):
    from PySide6.QtCore import Qt, QTimer, QSettings
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QStyle, QMenu, QWidget,
                                  QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("IRMS ému pro")
    if not QSystemTrayIcon.isSystemTrayAvailable():
        raise RuntimeError("La zone de notification Windows est indisponible.")
    settings = QSettings("IRMS", "emu-pro-desktop")
    icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    app.setWindowIcon(icon)
    runtime = runtime_factory()
    events = queue.Queue()
    state = {"ready": False, "closing": False, "urls": [], "refreshing": False}
    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    menu.setStyleSheet("QMenu{background:#f0f3f8;color:#213048;padding:8px;border:1px solid #c9d4e3;border-radius:12px;font:10pt 'Segoe UI';}QMenu::item{padding:8px 16px;border-radius:7px;}QMenu::item:selected{background:#d5e6ff;}")
    heading_action = menu.addAction("IRMS ému pro · 3.0.1"); heading_action.setEnabled(False)
    show_action = menu.addAction("Afficher la bulle")
    assistant = menu.addAction("Ouvrir l’assistant")
    direct = menu.addAction("Ouvrir la télémétrie")
    copy_action = menu.addAction("Copier l’adresse tablette")
    alternatives = menu.addMenu("Autres adresses réseau")
    reset_action = menu.addAction("Replacer la bulle sur cet écran")
    menu.addSeparator()
    diagnostic = menu.addAction("Diagnostic")
    logs = menu.addAction("Journaux")
    menu.addSeparator()
    quit_action = menu.addAction("Arrêter et quitter")
    tray.setContextMenu(menu)

    class Bubble(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
            self.setWindowTitle("IRMS ému pro · Tablette")
            self.setWindowIcon(icon)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setFixedWidth(450)
            self.positioned = False
            self.save_timer = QTimer(self)
            self.save_timer.setSingleShot(True)
            self.save_timer.timeout.connect(self.save_position)
        def areas(self):
            return [(s.availableGeometry().x(), s.availableGeometry().y(),
                     s.availableGeometry().width(), s.availableGeometry().height()) for s in app.screens()]
        def save_position(self):
            if self.positioned and not self.isMinimized() and self.isVisible():
                settings.setValue("bubble_x", self.x())
                settings.setValue("bubble_y", self.y())
                settings.sync()
        def place(self, reset=False):
            self.adjustSize()
            screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
            if screen is None:
                return
            area = screen.availableGeometry()
            x = area.right() - self.width() - 15
            y = area.bottom() - self.height() - 15
            if not reset:
                try:
                    x = int(settings.value("bubble_x", x))
                    y = int(settings.value("bubble_y", y))
                except (TypeError, ValueError):
                    pass
            x, y = fit_position(x, y, self.width(), self.height(), self.areas())
            self.move(x, y)
            self.positioned = True
        def moveEvent(self, event):
            super().moveEvent(event)
            if self.positioned and not self.isMinimized():
                self.save_timer.start(300)
        def closeEvent(self, event):
            if state["closing"]:
                event.accept()
            else:
                event.ignore()
                self.save_position()
                self.showMinimized()

    bubble = Bubble()

    class DragTitle(QLabel):
        def __init__(self, text):
            super().__init__(text)
            self.offset = None
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.setToolTip("Maintiens le clic gauche ici pour déplacer la bulle")
        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                handle = bubble.windowHandle()
                if handle is not None and handle.startSystemMove():
                    event.accept()
                    return
                self.offset = event.globalPosition().toPoint() - bubble.frameGeometry().topLeft()
                event.accept()
            else:
                super().mousePressEvent(event)
        def mouseMoveEvent(self, event):
            if self.offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                bubble.move(event.globalPosition().toPoint() - self.offset)
                event.accept()
            else:
                super().mouseMoveEvent(event)
        def mouseReleaseEvent(self, event):
            self.offset = None
            bubble.save_position()
            super().mouseReleaseEvent(event)

    outer = QVBoxLayout(bubble); outer.setContentsMargins(8, 8, 8, 8)
    panel = QWidget(); panel.setObjectName("panel"); outer.addWidget(panel)
    panel.setStyleSheet("#panel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(249,251,255,248),stop:1 rgba(225,233,245,248));border:1px solid white;border-radius:20px;}QLabel{color:#243247;background:transparent;border:none;font:10pt 'Segoe UI';}QPushButton{color:#245598;background:#f5f8fe;border:1px solid #cbd6e5;border-radius:9px;padding:8px;font:10pt 'Segoe UI';}")
    layout = QVBoxLayout(panel); layout.setContentsMargins(20, 16, 20, 16)
    title_row = QHBoxLayout()
    title = DragTitle("IRMS ému pro · Tablette")
    title.setStyleSheet("font:600 11pt 'Segoe UI';")
    title_row.addWidget(title, 1)
    more_button = QPushButton("Menu"); title_row.addWidget(more_button)
    layout.addLayout(title_row)
    address_label = QLabel("Démarrage du serveur…")
    address_label.setWordWrap(True); address_label.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(address_label)
    hint = QLabel("Déplace-moi par mon titre. Réduire me garde dans la barre des tâches.")
    hint.setWordWrap(True); layout.addWidget(hint)
    buttons = QHBoxLayout(); buttons.addStretch()
    copy_button = QPushButton("Copier l’adresse")
    reduce_button = QPushButton("Réduire")
    buttons.addWidget(copy_button); buttons.addWidget(reduce_button); layout.addLayout(buttons)

    def update_label():
        urls = state["urls"]
        address_label.setText((urls[0] + "\nMême réseau privé que ce PC. Ouvre cette adresse dans Safari.") if urls else
                              ("Aucune IPv4 locale détectée. Vérifie le Wi-Fi ou Ethernet." if state["ready"] else "Démarrage du serveur…"))
        copy_button.setEnabled(bool(urls))
    def show_bubble(reset=False):
        if state["closing"]:
            return
        update_label()
        if not bubble.positioned or reset:
            bubble.place(reset=reset)
        else:
            x, y = fit_position(bubble.x(), bubble.y(), bubble.width(), bubble.height(), bubble.areas())
            bubble.move(x, y)
        bubble.showNormal()
        bubble.raise_()
    def copy_address():
        if state["urls"]:
            app.clipboard().setText(state["urls"][0])
    def reduce():
        bubble.save_position()
        bubble.showMinimized()
    def update_addresses(urls):
        state["urls"] = urls
        update_label()
        tray.setToolTip(("IRMS ému pro 3.0.1\n" + (urls[0] if urls else "Aucune IPv4 locale"))[:127])
        alternatives.clear()
        for url in urls:
            action = alternatives.addAction(url)
            action.triggered.connect(lambda checked=False, value=url: app.clipboard().setText(value))
        alternatives.setEnabled(bool(urls)); copy_action.setEnabled(bool(urls))
    def open_page(path):
        if state["ready"] and not state["closing"]:
            webbrowser.open(runtime.pc_url() + path)
    def close():
        if state["closing"]:
            return
        bubble.save_position()
        state["closing"] = True
        bubble.hide()
        for action in (show_action, assistant, direct, copy_action, reset_action, diagnostic, quit_action):
            action.setEnabled(False)
        tray.setToolTip("IRMS · Fermeture des données…")
        def stop():
            try:
                runtime.stop()
            finally:
                events.put(("closed", None))
        threading.Thread(target=stop, name="IRMS-Stop", daemon=True).start()
    def boot():
        try:
            events.put(("ready", runtime.start()))
        except Exception as exc:
            logging.exception("Démarrage"); events.put(("error", str(exc)))
    def refresh():
        if not state["ready"] or state["closing"] or state["refreshing"]:
            return
        state["refreshing"] = True
        def task():
            try:
                events.put(("addresses", runtime.addresses()))
            except Exception:
                logging.exception("Actualisation réseau"); events.put(("refresh_done", None))
        threading.Thread(target=task, name="IRMS-IP", daemon=True).start()
    def drain():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "closed":
                    tray.hide(); app.quit(); return
                if state["closing"]:
                    continue
                if kind == "ready":
                    state["ready"] = True; update_addresses(value)
                    for action in (assistant, direct, diagnostic):
                        action.setEnabled(True)
                    show_bubble()
                elif kind == "addresses":
                    state["refreshing"] = False; update_addresses(value)
                elif kind == "refresh_done":
                    state["refreshing"] = False
                elif kind == "error":
                    QMessageBox.critical(bubble, "IRMS · Démarrage impossible", value); close()
        except queue.Empty:
            pass
        if state["ready"] and not state["closing"] and runtime.http_failed:
            QMessageBox.critical(bubble, "IRMS · Serveur arrêté", runtime.http_failed); close()
    show_action.triggered.connect(lambda: show_bubble())
    reset_action.triggered.connect(lambda: show_bubble(reset=True))
    more_button.clicked.connect(lambda: menu.popup(more_button.mapToGlobal(more_button.rect().bottomLeft())))
    assistant.triggered.connect(lambda: open_page("assistant.html"))
    direct.triggered.connect(lambda: open_page(""))
    diagnostic.triggered.connect(lambda: open_page("#diagnostic"))
    copy_action.triggered.connect(copy_address); copy_button.clicked.connect(copy_address)
    reduce_button.clicked.connect(reduce)
    logs.triggered.connect(lambda: os.startfile(str(log_directory)))
    quit_action.triggered.connect(close)
    tray.activated.connect(lambda reason: show_bubble() if reason in
        (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
    for action in (assistant, direct, copy_action, diagnostic):
        action.setEnabled(False)
    tray.setToolTip("IRMS ému pro · Démarrage"); tray.show()
    poll = QTimer(); poll.timeout.connect(drain); poll.start(150)
    network = QTimer(); network.timeout.connect(refresh); network.start(15000)
    threading.Thread(target=boot, name="IRMS-Start", daemon=True).start()
    try:
        app.exec()
    finally:
        bubble.save_position(); bubble.save_timer.stop()
        poll.stop(); network.stop(); tray.hide(); bubble.hide(); runtime.stop()
