"""Programming page: readiness checklist + which modules can be coded, with a shortcut to the Coding editor."""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QProgressBar, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .. import programming as PR
from . import common as C


class _Sig(QObject):
    p = Signal(float, str)


class ProgrammingPage(QWidget):
    def __init__(self, s, open_module):
        super().__init__()
        self.s = s
        self.open_module = open_module
        w, lay = C.page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.run_btn = C.button("Run readiness check", "primary", self.run)
        lay.addLayout(C.row(C.label("Programming", "h1"), "stretch", self.run_btn))
        lay.addWidget(C.label(
            "Checks the adapter, engine, battery and car network, then tests every module by writing its current coding "
            "back unchanged — this shows which modules accept coding without the manufacturer login. Nothing in the car "
            "is changed. Firmware flashing is not supported (needs a J2534 interface, the maker's files and online login).",
            "muted", True))
        self.bar = QProgressBar()
        self.bar.hide()
        self.status = C.label("", "muted")
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        self.checks = QTableWidget(0, 3)
        self.checks.setHorizontalHeaderLabels(["Check", "Result", "Detail"])
        self.checks.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.checks.verticalHeader().hide()
        self.checks.setMaximumHeight(230)
        lay.addWidget(self.checks)
        self.mods = QTableWidget(0, 4)
        self.mods.setHorizontalHeaderLabels(["Addr", "Module", "Coding", "Detail"])
        self.mods.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.mods.verticalHeader().hide()
        self.mods.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mods.cellDoubleClicked.connect(self._open)
        lay.addWidget(self.mods, 1)
        lay.addWidget(C.label("Double-click a CODABLE module to open its Coding editor (backup is taken before any write).",
                              "muted"))
        self.sig = _Sig()
        self.sig.p.connect(lambda f, m: (self.bar.setValue(int(f * 100)), self.status.setText(m)))

    def run(self):
        s = self.s
        if not s.connected:
            return C.error_box("Connect first (ignition ON, engine OFF).")
        self.run_btn.setEnabled(False)
        self.bar.show()
        was = s.poll_enabled
        s.poll_enabled = False

        def done(res):
            s.poll_enabled = was
            self.run_btn.setEnabled(True)
            self.bar.hide()
            self.status.setText("Ready for coding." if res.ready else "Not ready — fix the red items first.")
            self.render(res)

        def fail(m):
            s.poll_enabled = was
            self.run_btn.setEnabled(True)
            self.bar.hide()
            C.error_box(m)

        C.run_bg(lambda: PR.check(s.elm, s.obd, s.vag, s.family, self.sig.p.emit), done, fail)

    def render(self, res):
        col = {"ok": C.GREEN, "warn": C.YELLOW, "fail": C.RED, "info": C.MUTED}
        word = {"ok": "OK", "warn": "Check", "fail": "Not ready", "info": "Info"}
        self.checks.setRowCount(len(res.checks))
        for i, c in enumerate(res.checks):
            self.checks.setItem(i, 0, QTableWidgetItem(c.name))
            it = QTableWidgetItem(word[c.status])
            it.setForeground(QColor(col[c.status]))
            self.checks.setItem(i, 1, it)
            self.checks.setItem(i, 2, QTableWidgetItem(c.detail))
        vcol = {"codable": C.GREEN, "login": C.ORANGE, "read-only": C.MUTED, "not-supported": C.MUTED}
        vword = {"codable": "CODABLE", "login": "Needs login", "read-only": "Read-only", "not-supported": "No coding"}
        mods = sorted(res.modules, key=lambda m: (m.verdict != "codable", m.address))
        self.mods.setRowCount(len(mods))
        for i, m in enumerate(mods):
            self.mods.setItem(i, 0, QTableWidgetItem(m.address))
            self.mods.setItem(i, 1, QTableWidgetItem(m.name))
            it = QTableWidgetItem(vword.get(m.verdict, m.verdict))
            it.setForeground(QColor(vcol.get(m.verdict, C.MUTED)))
            it.setData(Qt.UserRole, m.verdict)
            self.mods.setItem(i, 2, it)
            self.mods.setItem(i, 3, QTableWidgetItem(m.detail))

    def _open(self, row, _col):
        if self.mods.item(row, 2).data(Qt.UserRole) == "codable":
            self.open_module(self.mods.item(row, 0).text())
