"""Fault history and Trips & Battery pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .. import features as F
from ..vag import MODULE_BY_ADDR
from . import common as C


def _table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().hide()
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setAlternatingRowColors(True)
    return t


def _mod_name(m: str) -> str:
    if m.startswith("OBD:"):
        return m[4:] + " (OBD-II)"
    mod = MODULE_BY_ADDR.get(m)
    return f"{m} · {mod.name}" if mod else m


class HistoryPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        w, lay = C.page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        lay.addLayout(C.row(C.label("Fault History", "h1"), "stretch", C.button("Refresh", slot=self.refresh)))
        lay.addWidget(C.label("Every scan is remembered: when each code first appeared, last seen, how often, and "
                              "whether it came back after you cleared it.", "muted", True))
        self.table = _table(["Module", "Code", "Last state", "First seen", "Last seen", "Times seen", "Cleared",
                             "Came back"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        rows = F.summarize_history(self.s.store)
        self.table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            vals = [_mod_name(e["module"]), e["code"], e["state"], e["first"].replace("T", " "),
                    e["last"].replace("T", " "), str(e["seen"]), str(e["cleared"]), "YES" if e["returned"] else ""]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 7 and e["returned"]:
                    it.setForeground(QColor(C.RED))
                if j == 2:
                    it.setForeground(QColor({"Active": C.RED, "Stored": C.YELLOW}.get(v, C.MUTED)))
                self.table.setItem(i, j, it)

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)


class TripsPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        w, lay = C.page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        lay.addWidget(C.label("Trips & Battery", "h1"))
        self.batt = C.label("", "")
        self.batt.setTextFormat(Qt.RichText)
        lay.addWidget(C.card(C.label("Battery health", "h2"), self.batt))
        self.crank = _table(["Engine start", "Resting V", "Lowest while starting"])
        self.crank.setMaximumHeight(170)
        self.crank.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.crank)
        self.current = C.label("", "muted")
        lay.addLayout(C.row(C.label("Trips", "h2"), "stretch", self.current))
        lay.addWidget(C.label("Recorded automatically while connected. A trip ends after the engine is off for 60 s "
                              "or you disconnect. Fuel use is not available: this car reports neither fuel rate nor "
                              "air-flow.", "muted", True))
        self.trips = _table(["Start", "Duration", "Distance", "Avg speed", "Max speed", "Max rpm", "Idle",
                             "Full throttle", "Harsh brakes", "Max coolant", "Max oil"])
        self.trips.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.trips, 1)
        s.trip_saved.connect(lambda _t: self.refresh())
        s.battery.connect(lambda _v: self._battery())
        from PySide6.QtCore import QTimer
        t = QTimer(self)
        t.timeout.connect(self._live)
        t.start(1000)
        self.refresh()

    def _battery(self):
        rows = self.s.batt.verdict()
        col = {"ok": C.GREEN, "warn": C.YELLOW, "bad": C.RED}
        word = {"ok": "OK", "warn": "Low", "bad": "Check"}
        if not rows:
            self.batt.setText(f"<span style='color:{C.MUTED}'>Connect with the engine off, then start the engine "
                              f"to measure resting and starting voltage.</span>")
            return
        self.batt.setText("<br>".join(f"{k}: <b>{v}</b> <span style='color:{col[st]}'>● {word[st]}</span>"
                                      for k, v, st in rows))

    def _live(self):
        tr = self.s.trips.trip
        if tr:
            self.current.setText(f"Recording: {tr.duration_s / 60:.0f} min · {tr.distance_km:.1f} km · "
                                 f"max {tr.max_speed:.0f} km/h")
        else:
            self.current.setText("")

    def refresh(self):
        self._battery()
        hist = list(reversed(self.s.store.get("battery") or []))
        self.crank.setRowCount(len(hist))
        for i, h in enumerate(hist):
            for j, v in enumerate((h["date"].replace("T", " "), f"{h['rest']:.2f} V" if h.get("rest") else "—",
                                   f"{h['crank_min']:.2f} V")):
                self.crank.setItem(i, j, QTableWidgetItem(v))
        trips = list(reversed(self.s.store.get("trips") or []))
        self.trips.setRowCount(len(trips))
        for i, t in enumerate(trips):
            dist = (t["odo_end"] - t["odo_start"]) if t.get("odo_start") and t.get("odo_end") and \
                t["odo_end"] > t["odo_start"] else t["distance_km"]
            vals = [t["start"].replace("T", " "), f"{t['duration_s'] / 60:.0f} min", f"{dist:.1f} km",
                    f"{t.get('avg_speed', 0):.0f} km/h", f"{t['max_speed']:.0f} km/h", f"{t['max_rpm']:.0f}",
                    f"{t['idle_s'] / 60:.0f} min", str(t["full_throttle"]), str(t["harsh_brakes"]),
                    f"{t['max_coolant']:.0f} °C" if t.get("max_coolant") is not None else "—",
                    f"{t['max_oil']:.0f} °C" if t.get("max_oil") is not None else "—"]
            for j, v in enumerate(vals):
                self.trips.setItem(i, j, QTableWidgetItem(v))

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)
