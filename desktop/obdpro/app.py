"""OBD Pro desktop — main window."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget, QLabel

from .gui import common as C
from .gui.pages import ConnectPage, DiagnosePage, LivePage, LogsPage
from .gui.session import Session
from .gui.vehicle import VehiclePage
from .gui.power import PowerPage
from .gui.reportpage import ReportPage
from .gui.history import HistoryPage, TripsPage
from .gui.dash import DashPage
from .gui.speaker import SpeakerPage
from .gui.programming_page import ProgrammingPage
from .store import Store


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OBD Pro")
        self.resize(1280, 820)
        self.store = Store()
        self.s = Session(self.store)
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QWidget()
        self.sidebar = side
        side.setFixedWidth(200)
        side.setStyleSheet("background: #0B0C0E;")
        from PySide6.QtWidgets import QVBoxLayout
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 18, 0, 12)
        brand = QLabel("  ◉  OBD Pro")
        brand.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {C.TEXT}; padding: 0 0 10px 6px;")
        sl.addWidget(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for t in ("⚡  Connect", "🎛  Dashboard", "◔  Live Data", "⚠  Diagnose", "🚗  Vehicle", "📋  Report", "🕘  Fault History", "🛣  Trips & Battery", "🏁  Power Run", "🔊  Speaker Test", "🛠  Programming", "▤  Logs"):
            self.nav.addItem(t)
        sl.addWidget(self.nav, 1)
        self.conn = QLabel("  ● Offline")
        self.conn.setStyleSheet(f"color: {C.MUTED}; padding: 8px 14px;")
        sl.addWidget(self.conn)
        h.addWidget(side)
        self.stack = QStackedWidget()
        self.pages = [ConnectPage(self.s), DashPage(self.s), LivePage(self.s), DiagnosePage(self.s), VehiclePage(self.s),
                      ReportPage(self.s), HistoryPage(self.s), TripsPage(self.s), PowerPage(self.s),
                      SpeakerPage(self.s), None, LogsPage(self.s)]
        vp = next(p for p in self.pages if p.__class__.__name__ == "VehiclePage")
        self.pages[self.pages.index(None)] = ProgrammingPage(self.s, lambda addr: vp.open_module(addr))
        for p in self.pages:
            self.stack.addWidget(p)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.nav.currentRowChanged.connect(self._page)
        self.nav.setCurrentRow(0)
        self.s.state_changed.connect(self._state)
        # alert toast
        from PySide6.QtCore import QTimer
        self.toast = QLabel(self)
        self.toast.hide()
        self.toast.setWordWrap(True)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)
        self.s.alert.connect(self._alert)
        from . import features as F
        if F.setting(self.store, "autoconnect") and self.s.last_connection:
            QTimer.singleShot(600, self.s.connect_last)

    def _alert(self, level, text):
        col = C.RED if level == "bad" else C.YELLOW
        self.toast.setText(f"⚠  {text}")
        self.toast.setStyleSheet(f"background: #2a1416; color: {col}; border: 1px solid {col}; border-radius: 12px;"
                                 f"padding: 12px 16px; font-size: 14px; font-weight: 600;")
        self.toast.setFixedWidth(min(520, self.width() - 260))
        self.toast.adjustSize()
        self.toast.move(self.width() - self.toast.width() - 24, 20)
        self.toast.raise_()
        self.toast.show()
        QApplication.beep()
        self._toast_timer.start(8000)

    def _page(self, i):
        self.stack.setCurrentIndex(i)
        self.s.poll_enabled = i in (0, 1, 2, 7, 8)        # only poll live PIDs when visible → bus free for diagnostics

    def _state(self, st, _d):
        col = {"connected": C.GREEN, "connecting": C.YELLOW, "reconnecting": C.YELLOW, "failed": C.RED}.get(st, C.MUTED)
        txt = {"connected": "Connected", "connecting": "Connecting…", "reconnecting": "Reconnecting…",
               "failed": "Failed"}.get(st, "Offline")
        self.conn.setText(f"  ● {txt}")
        self.conn.setStyleSheet(f"color: {col}; padding: 8px 14px; font-weight: 600;")
        if st == "connected" and self.stack.currentIndex() == 0:
            self.nav.setCurrentRow(1)

    def closeEvent(self, e):
        self.s.disconnect()
        super().closeEvent(e)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("OBD Pro")
    C.apply_theme(app)
    from pathlib import Path
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.png"))))
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
