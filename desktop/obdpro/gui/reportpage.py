"""Report page: one-click full scan → HTML report shown in-app, saved, printable."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QProgressBar, QSplitter, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import Qt

from .. import report
from . import common as C


class _Sig(QObject):
    progress = Signal(int, str)


class ReportPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        self.path = None
        w, lay = C.page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.run_btn = C.button("Run Full Scan", "primary", self.run)
        self.open_btn = C.button("Open in Browser / Print", slot=self.open_browser)
        self.open_btn.setEnabled(False)
        self.pdf_btn = C.button("Save PDF", slot=self.save_pdf)
        self.pdf_btn.setEnabled(False)
        lay.addLayout(C.row(C.label("Vehicle Report", "h1"), "stretch", self.pdf_btn, self.open_btn, self.run_btn))
        lay.addWidget(C.label("Scans every module: identification, part numbers, software, coding, faults, readiness, "
                              "odometer, live snapshot. Reports are saved and can be printed or shared as PDF.",
                              "muted", True))
        self.bar = QProgressBar()
        self.bar.hide()
        self.status = C.label("", "muted")
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        split = QSplitter(Qt.Horizontal)
        self.history = QListWidget()
        self.history.setMaximumWidth(260)
        self.history.currentItemChanged.connect(self._load)
        split.addWidget(self.history)
        self.view = QWebEngineView()
        self.view.setHtml("<body style='background:#0f1012;color:#8e8e93;font-family:sans-serif;padding:30px'>"
                          "Run a full scan, or pick a saved report on the left.</body>")
        split.addWidget(self.view)
        split.setSizes([220, 900])
        lay.addWidget(split, 1)
        self.sig = _Sig()
        self.sig.progress.connect(lambda p, m: (self.bar.setValue(p), self.status.setText(m)))
        self._refresh_history()

    def _dir(self):
        d = self.s.store.logs_dir() / "reports"
        d.mkdir(exist_ok=True)
        return d

    def _refresh_history(self):
        self.history.clear()
        for f in sorted(self._dir().glob("*.html"), reverse=True):
            it = QListWidgetItem(f.stem.replace("report_", "").replace("_", " "))
            it.setData(Qt.UserRole, str(f))
            self.history.addItem(it)

    def _load(self, it, _prev=None):
        if not it:
            return
        self.path = it.data(Qt.UserRole)
        self.view.load(QUrl.fromLocalFile(self.path))
        self.open_btn.setEnabled(True)
        self.pdf_btn.setEnabled(True)

    def run(self):
        if not self.s.connected:
            return C.error_box("Connect first.")
        self.run_btn.setEnabled(False)
        self.bar.show()
        self.bar.setValue(0)
        was = self.s.poll_enabled
        self.s.poll_enabled = False

        def done(r):
            self.s.poll_enabled = was
            self.run_btn.setEnabled(True)
            self.bar.hide()
            from .. import features as F
            for m in r["modules"]:
                if m["present"]:
                    F.record_faults(self.s.store, r.get("vin"), m["address"], [(c, st) for c, st, _d, _t in m["faults"]],
                                    "report")
            name = f"report_{datetime.now():%Y-%m-%d_%H%M}_{(r.get('vin') or 'car')[-6:]}"
            html_path = self._dir() / f"{name}.html"
            html_path.write_text(report.to_html(r), encoding="utf-8")
            (self._dir() / f"{name}.json").write_text(json.dumps(r, indent=1, default=str))
            self.status.setText(f"Saved {html_path}")
            self._refresh_history()
            self.history.setCurrentRow(0)

        def fail(m):
            self.s.poll_enabled = was
            self.run_btn.setEnabled(True)
            self.bar.hide()
            C.error_box(m)

        C.run_bg(lambda: report.build(self.s.elm, self.sig.progress.emit), done, fail)

    def save_pdf(self):
        if not self.path:
            return
        out = self.path[:-5] + ".pdf"
        self.view.page().pdfPrintingFinished.connect(
            lambda p, ok: self.status.setText(f"PDF saved: {p}" if ok else "PDF export failed"))
        self.view.page().printToPdf(out)

    def open_browser(self):
        if self.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))
