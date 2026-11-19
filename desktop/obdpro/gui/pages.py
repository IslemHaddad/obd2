"""Connect, Live, Diagnose and Logs pages."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QMenu, QScrollArea, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QWidget,
                               QCheckBox, QPlainTextEdit, QTabWidget, QApplication)

from .. import pids
from ..transport import list_serial_ports, scan_ble
from . import common as C
from .widgets import GaugeTile


# =================================================================== Connect
class ConnectPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        w, lay = C.page()
        root = QScrollArea()
        root.setWidgetResizable(True)
        root.setWidget(w)
        from PySide6.QtWidgets import QVBoxLayout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        lay.addWidget(C.label("Connect", "h1"))
        self.status = C.label("Not connected", "h2")
        self.detail = C.label("", "muted", wrap=True)
        self.disc = C.button("Disconnect", "danger", s.disconnect)
        self.disc.hide()
        self.last_btn = C.button("⚡ Connect to Last Adapter", "primary", s.connect_last)
        from .. import features as F
        self.auto = QCheckBox("Connect automatically when the app starts")
        self.auto.setChecked(bool(F.setting(s.store, "autoconnect")))
        self.auto.toggled.connect(lambda v: F.set_setting(s.store, "autoconnect", v))
        self.recon = QCheckBox("Reconnect automatically if the link drops")
        self.recon.setChecked(bool(F.setting(s.store, "auto_reconnect")))
        self.recon.toggled.connect(lambda v: F.set_setting(s.store, "auto_reconnect", v))
        lay.addWidget(C.card(C.row(self.status, "stretch", self.disc, self.last_btn), self.detail,
                             C.row(self.auto, self.recon, "stretch")))
        self._update_last()

        # My adapters
        self.my = QListWidget()
        self.my.setFixedHeight(120)
        self.my.itemDoubleClicked.connect(lambda it: s.connect_saved(it.data(Qt.UserRole)))
        rename = C.button("Rename", slot=self._rename_adapter)
        forget = C.button("Forget", slot=self._forget_adapter)
        go_my = C.button("Connect", "primary", lambda: self.my.currentItem() and s.connect_saved(
            self.my.currentItem().data(Qt.UserRole)))
        lay.addWidget(C.card(C.row(C.label("My adapters", "h2"), "stretch", rename, forget, go_my),
                             C.label("Every adapter you've used, with its chip type and the voltage correction the app "
                                     "learned for it. Double-click to connect.", "muted", True), self.my))
        self._fill_adapters()

        # USB / serial / Bluetooth classic
        self.ports = QComboBox()
        self.ports.setMinimumWidth(320)
        self.ports.setEditable(True)
        self.baud = QComboBox()
        self.baud.addItems(["38400", "9600", "115200", "230400", "500000"])
        refresh = C.button("Refresh", slot=self.refresh_ports)
        go_serial = C.button("Connect", "primary", self.connect_serial)
        lay.addWidget(C.card(
            C.label("USB cable / Bluetooth (classic)", "h2"),
            C.label("USB adapters appear as /dev/ttyUSB0 or COM3. Classic Bluetooth adapters (most Konnwei KW902/KW903 "
                    "on PC): pair once, then bind:  sudo rfcomm bind 0 <adapter MAC>  → /dev/rfcomm0.", "muted", True),
            C.row(self.ports, self.baud, refresh, "stretch", go_serial)))

        # BLE
        self.ble = QListWidget()
        self.ble.setFixedHeight(130)
        self.ble_btn = C.button("Scan", slot=self.scan_ble)
        go_ble = C.button("Connect", "primary", self.connect_ble)
        self.ble.itemDoubleClicked.connect(lambda _: self.connect_ble())
        lay.addWidget(C.card(C.row(C.label("Bluetooth LE", "h2"), "stretch", self.ble_btn, go_ble), self.ble))

        # Wi-Fi
        st = s.store.get("settings", {}) or {}
        self.host = QLineEdit(st.get("host", "192.168.0.10"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(st.get("port", 35000)))
        go_tcp = C.button("Connect", "primary", self.connect_tcp)
        lay.addWidget(C.card(C.label("Wi-Fi", "h2"), C.row(C.label("Host"), self.host, C.label("Port"), self.port,
                                                         "stretch", go_tcp)))

        # Demo
        lay.addWidget(C.card(C.row(C.label("Demo car (simulated, with faults)", "h2"), "stretch",
                                   C.button("Demo SEAT", slot=lambda: s.connect("sim", "Demo SEAT Leon")),
                                   C.button("Demo Hyundai Grand i10", slot=lambda: s.connect("sim", "hyundai")),
                                   C.button("Demo Renault Clio", slot=lambda: s.connect("sim", "renault")))))
        lay.addStretch(1)
        s.state_changed.connect(self.on_state)
        self.refresh_ports()

    def _fill_adapters(self):
        from .. import adapters as AD
        self.my.clear()
        for a in AD.all_adapters(self.s.store):
            off = a.get("volt_offset")
            extra = f" · voltmeter {off:+.1f} V (corrected)" if off is not None and abs(off) >= 0.2 else ""
            it = QListWidgetItem(f"{a['name']}  —  {a['chip']}{extra}\n      {a['summary']}")
            it.setData(Qt.UserRole, a)
            self.my.addItem(it)

    def _rename_adapter(self):
        from PySide6.QtWidgets import QInputDialog
        from .. import adapters as AD
        it = self.my.currentItem()
        if not it:
            return
        a = it.data(Qt.UserRole)
        name, ok = QInputDialog.getText(self, "Rename adapter", "Name:", text=a["name"])
        if ok and name.strip():
            items = self.s.store.get("adapters") or []
            for x in items:
                if x["key"] == a["key"]:
                    x["name"] = name.strip()
            self.s.store.set("adapters", items)
            self._fill_adapters()

    def _forget_adapter(self):
        from .. import adapters as AD
        it = self.my.currentItem()
        if it:
            AD.forget(self.s.store, it.data(Qt.UserRole)["key"])
            self._fill_adapters()

    def _update_last(self):
        lc = self.s.last_connection
        if lc:
            kind, arg = lc
            name = {"ble": "Bluetooth LE", "serial": "Serial", "tcp": "Wi-Fi", "sim": "Demo"}.get(kind, kind)
            self.last_btn.setText(f"⚡ Reconnect · {name} {arg if kind != 'serial' else arg[0]}")
        self.last_btn.setVisible(bool(lc) and self.s.state not in ("connected", "connecting", "reconnecting"))

    def refresh_ports(self):
        self.ports.clear()
        for dev, desc in list_serial_ports():
            self.ports.addItem(desc, dev)
        if not self.ports.count():
            self.ports.addItem("/dev/rfcomm0", "/dev/rfcomm0")

    def connect_serial(self):
        dev = self.ports.currentData() or self.ports.currentText().split(" ")[0]
        self.s.connect("serial", (dev, int(self.baud.currentText())))

    def scan_ble(self):
        self.ble_btn.setEnabled(False)
        self.ble_btn.setText("Scanning…")
        self.ble.clear()

        def done(res):
            self.ble_btn.setEnabled(True)
            self.ble_btn.setText("Scan")
            for addr, name, rssi in res:
                it = QListWidgetItem(f"{name}    {addr}" + (f"    {rssi} dBm" if rssi > -100 else ""))
                it.setData(Qt.UserRole, addr)
                self.ble.addItem(it)
            if not res:
                self.ble.addItem("No BLE devices found")
            else:
                self.ble.setCurrentRow(0)
            st = self.s.store.get("settings", {}) or {}
            for i in range(self.ble.count()):
                if self.ble.item(i).data(Qt.UserRole) == st.get("ble"):
                    self.ble.setCurrentRow(i)

        def fail(m):
            self.ble_btn.setEnabled(True)
            self.ble_btn.setText("Scan")
            C.error_box(f"Bluetooth scan failed: {m}")

        C.run_bg(scan_ble, done, fail)

    def connect_ble(self):
        it = self.ble.currentItem()
        if it and it.data(Qt.UserRole):
            st = self.s.store.get("settings", {}) or {}
            st["ble"] = it.data(Qt.UserRole)
            self.s.store.set("settings", st)
            self.s.connect("ble", it.data(Qt.UserRole))

    def connect_tcp(self):
        st = self.s.store.get("settings", {}) or {}
        st.update(host=self.host.text().strip(), port=self.port.value())
        self.s.store.set("settings", st)
        self.s.connect("tcp", (self.host.text().strip(), self.port.value()))

    def on_state(self, state, detail):
        colors = {"connected": C.GREEN, "failed": C.RED, "connecting": C.YELLOW, "reconnecting": C.YELLOW}
        text = {"idle": "Not connected", "connecting": "Connecting…", "connected": "Connected",
                "failed": "Connection failed", "reconnecting": "Reconnecting…"}[state]
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {colors.get(state, C.MUTED)}")
        self.detail.setText(detail)
        self.disc.setVisible(state in ("connected", "connecting", "reconnecting"))
        self._update_last()
        if state == "connected":
            self._fill_adapters()
            if self.s.elm:
                self.detail.setText(f"{detail}\nAdapter: {self.s.elm.profile.chip} — {self.s.elm.profile.summary}")


# =================================================================== Live
STYLES = ["ring", "arc", "bar", "number", "graph"]


class TileDialog(QDialog):
    def __init__(self, parent, supported: set[int], tile: dict | None = None, store=None):
        super().__init__(parent)
        from .. import features as F
        self.setWindowTitle("Gauge")
        f = QFormLayout(self)
        self.pid = QComboBox()
        self.pid.setMinimumWidth(320)
        for p in pids.ALL:
            if not supported or p.id in supported:
                self.pid.addItem(f"{p.name}  (01{p.id:02X})", ("pid", p.id))
        vag_defs = list(F.VAG_PRESETS)
        if store is not None:
            for m in store.get("measurements") or []:
                if m.get("kind", "number") == "number" and all((m["module"], m["did"]) != (d["module"], d["did"])
                                                                 for d in vag_defs):
                    vag_defs.append(dict(m, min=m.get("min", 0), max=m.get("max", 255)))
        for d in vag_defs:
            self.pid.addItem(f"SEAT · {d['name']}  ({d['module']}/{int(d['did']):04X})", ("vag", d))
        self.style = QComboBox()
        self.style.addItems([s.capitalize() for s in STYLES])
        self.warn_on = QCheckBox("Warn above")
        self.warn = QDoubleSpinBox()
        self.warn.setRange(-1e6, 1e6)
        if tile:
            for i in range(self.pid.count()):
                kind, val = self.pid.itemData(i)
                if (kind == "pid" and tile.get("pid") == val) or (kind == "vag" and tile.get("vag") and
                                                                   (val["module"], val["did"]) ==
                                                                   (tile["vag"]["module"], tile["vag"]["did"])):
                    self.pid.setCurrentIndex(i)
            self.style.setCurrentIndex(STYLES.index(tile.get("style", "ring")))
            if tile.get("warn") is not None:
                self.warn_on.setChecked(True)
                self.warn.setValue(tile["warn"])
        f.addRow("Sensor", self.pid)
        f.addRow("Style", self.style)
        f.addRow(self.warn_on, self.warn)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def result_tile(self) -> dict:
        kind, val = self.pid.currentData()
        t = {"style": STYLES[self.style.currentIndex()],
             "warn": self.warn.value() if self.warn_on.isChecked() else None}
        t["pid" if kind == "pid" else "vag"] = val
        return t


class LivePage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        w, lay = C.page()
        from PySide6.QtWidgets import QVBoxLayout
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.rate = C.pill("0.0 Hz", C.ACCENT)
        self.batt = C.pill("— V", C.GREEN)
        self.rec = C.button("● Record CSV", slot=self.toggle_rec)
        add = C.button("+ Add Gauge", "primary", self.add_tile)
        reset = C.button("Reset Layout", slot=self.reset)
        lay.addLayout(C.row(C.label("Live Data", "h1"), self.rate, self.batt, "stretch", reset, self.rec, add))
        lay.addWidget(C.label("Click a gauge to edit it. Right-click for style, order and remove.", "muted"))
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(14)
        self.grid.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.grid_host)
        lay.addWidget(sc, 1)
        self.tiles: list[GaugeTile] = []
        self.rebuild()
        s.values.connect(self.on_values)
        s.rate.connect(lambda r: self.rate.setText(f"{r:.1f} Hz"))
        s.battery.connect(lambda v: self.batt.setText(f"{v:.1f} V"))

    def rebuild(self):
        for t in self.tiles:
            t.setParent(None)
            t.deleteLater()
        self.tiles = []
        from .. import features as F
        for cfg in self.s.tiles:
            p = pids.BY_ID.get(cfg["pid"]) if cfg.get("pid") is not None else (
                F.vpid_from(cfg["vag"]) if cfg.get("vag") else None)
            if not p:
                continue
            t = GaugeTile(p, cfg.get("style", "ring"), cfg.get("warn"))
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.customContextMenuRequested.connect(lambda pos, tile=t, c=cfg: self.menu(tile, c, pos))
            t.clicked.connect(lambda c=cfg: self.edit(c))
            self.tiles.append(t)
        self.relayout()

    def relayout(self):
        while self.grid.count():
            self.grid.takeAt(0)
        cols = max(1, min(4, self.width() // 280))
        for i, t in enumerate(self.tiles):
            self.grid.addWidget(t, i // cols, i % cols)
            t.setMinimumHeight(230 if t.style in ("ring", "arc") else 170)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def on_values(self, vals: dict):
        for t in self.tiles:
            if t.pid.id in vals and isinstance(vals[t.pid.id], (int, float)):
                t.set_value(vals[t.pid.id])

    def menu(self, tile, cfg, pos):
        m = QMenu(self)
        sm = m.addMenu("Style")
        for st in STYLES:
            a = QAction(st.capitalize(), sm, checkable=True, checked=cfg.get("style") == st)
            a.triggered.connect(lambda _=False, st=st: self._update(cfg, style=st))
            sm.addAction(a)
        m.addAction("Edit…", lambda: self.edit(cfg))
        m.addAction("Move earlier", lambda: self._move(cfg, -1))
        m.addAction("Move later", lambda: self._move(cfg, 1))
        m.addSeparator()
        m.addAction("Remove", lambda: self._remove(cfg))
        m.exec(tile.mapToGlobal(pos))

    def _update(self, cfg, **kw):
        if "pid" in kw:
            cfg.pop("vag", None)
        if "vag" in kw:
            cfg.pop("pid", None)
        cfg.update(kw)
        self.s.save_tiles()
        self.rebuild()

    def _move(self, cfg, d):
        i = self.s.tiles.index(cfg)
        j = max(0, min(len(self.s.tiles) - 1, i + d))
        self.s.tiles[i], self.s.tiles[j] = self.s.tiles[j], self.s.tiles[i]
        self.s.save_tiles()
        self.rebuild()

    def _remove(self, cfg):
        self.s.tiles.remove(cfg)
        self.s.save_tiles()
        self.rebuild()

    def edit(self, cfg):
        d = TileDialog(self, self.s.supported, cfg, self.s.store)
        if d.exec():
            self._update(cfg, **d.result_tile())

    def add_tile(self):
        d = TileDialog(self, self.s.supported, None, self.s.store)
        if d.exec():
            self.s.tiles.append(d.result_tile())
            self.s.save_tiles()
            self.rebuild()

    def reset(self):
        from .session import DEFAULT_TILES
        self.s.tiles = [dict(t) for t in DEFAULT_TILES]
        self.s.save_tiles()
        self.rebuild()

    def toggle_rec(self):
        if self.s.logging:
            self.s.stop_logging()
            self.rec.setText("● Record CSV")
            self.rec.setObjectName("")
        else:
            if not self.s.connected:
                return C.error_box("Connect first.")
            self.s.start_logging()
            self.rec.setText(f"■ Stop  ({self.s.log_path.name})")
            self.rec.setObjectName("danger")
        self.rec.style().unpolish(self.rec)
        self.rec.style().polish(self.rec)


# =================================================================== Diagnose (generic OBD-II)
class DiagnosePage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        self.reports = []
        w, lay = C.page()
        from PySide6.QtWidgets import QVBoxLayout
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.scan_btn = C.button("Scan", "primary", self.scan)
        self.clear_sel = C.button("Clear Selected Module", "danger", self.clear_selected)
        self.clear_all = C.button("Clear Faulty Modules", "danger", self.clear_faulty)
        self.mil = C.label("", "h2")
        lay.addLayout(C.row(C.label("Diagnose", "h1"), "stretch", self.clear_sel, self.clear_all, self.scan_btn))
        lay.addWidget(C.label("Generic OBD-II emissions codes, read and cleared per module. Healthy modules are never "
                              "touched. For SEAT/VW body, ABS, airbag… use the Vehicle page.", "muted", True))
        lay.addWidget(self.mil)
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Module / Code", "Type", "Description"])
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.setColumnWidth(0, 220)
        self.tree.setAlternatingRowColors(True)
        split.addWidget(self.tree)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.ready = QTableWidget(0, 2)
        self.ready.setHorizontalHeaderLabels(["Readiness monitor", "Status"])
        self.ready.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ready.verticalHeader().hide()
        self.freeze = QTableWidget(0, 2)
        self.freeze.setHorizontalHeaderLabels(["Freeze frame", "Value"])
        self.freeze.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.freeze.verticalHeader().hide()
        self.monitors = QTableWidget(0, 3)
        self.monitors.setHorizontalHeaderLabels(["On-board monitor (Mode 06)", "Value / range", "Result"])
        self.monitors.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.monitors.verticalHeader().hide()
        rl.addWidget(self.ready)
        rl.addWidget(self.freeze)
        rl.addWidget(self.monitors)
        split.addWidget(right)
        split.setSizes([700, 380])
        lay.addWidget(split, 1)
        self._busy(False)

    def _busy(self, b):
        on = self.s.connected and not b
        self.scan_btn.setEnabled(on)
        self.clear_sel.setEnabled(on and bool(self.reports))
        self.clear_all.setEnabled(on and any(r.faulty for r in self.reports))
        self.scan_btn.setText("Scanning…" if b else "Scan")

    def scan(self):
        if not self.s.connected:
            return
        self._busy(True)
        o = self.s.obd

        def work():
            from ..obd import ModuleReport
            with self.s.elm.lock:
                from .. import features as F
                ecus = o.discover_ecus()
                reps = [ModuleReport(e, o.dtcs_for(e)) for e in ecus]
                for rp in reps:
                    F.record_faults(self.s.store, self.s.vin, "OBD:" + rp.ecu.name,
                                    [(d.code, d.kind) for d in rp.dtcs])
                return reps, o.readiness(), o.freeze_frame(self.s.supported), o.monitor_tests()

        def done(r):
            self.reports, ready, freeze, monitors = r
            self.render(ready, freeze, monitors)
            self._busy(False)

        C.run_bg(work, done, lambda m: (self._busy(False), C.error_box(m)))

    def render(self, ready, freeze, monitors=()):
        self.tree.clear()
        for rep in sorted(self.reports, key=lambda r: not r.faulty):
            top = QTreeWidgetItem([rep.ecu.name, f"{len(rep.dtcs)} code(s)" if rep.faulty else "No faults — skipped",
                                   rep.ecu.request if rep.ecu.request != "*" else ""])
            top.setData(0, Qt.UserRole, rep)
            top.setForeground(1, C.QColor(C.ORANGE if rep.faulty else C.GREEN))
            for d in rep.dtcs:
                ch = QTreeWidgetItem([d.code, d.kind, d.description])
                ch.setForeground(1, C.QColor({"Stored": C.RED, "Pending": C.YELLOW}.get(d.kind, "#BF5AF2")))
                top.addChild(ch)
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)
        if ready:
            self.mil.setText(f"Check Engine light {'ON' if ready.mil_on else 'OFF'} · {ready.dtc_count} confirmed code(s)")
            self.mil.setStyleSheet(f"color: {C.ORANGE if ready.mil_on else C.GREEN}")
            mons = [m for m in ready.monitors if m[1]]
            self.ready.setRowCount(len(mons))
            for i, (n, _sup, comp) in enumerate(mons):
                self.ready.setItem(i, 0, QTableWidgetItem(n))
                it = QTableWidgetItem("Complete" if comp else "Incomplete")
                it.setForeground(C.QColor(C.GREEN if comp else C.YELLOW))
                self.ready.setItem(i, 1, it)
        self.freeze.setRowCount(len(freeze))
        for i, (k, v) in enumerate(sorted(freeze.items())):
            p = pids.BY_ID[k]
            self.freeze.setItem(i, 0, QTableWidgetItem(p.name))
            self.freeze.setItem(i, 1, QTableWidgetItem(f"{v:.1f} {p.unit}"))
        self.monitors.setRowCount(len(monitors))
        for i, t in enumerate(monitors):
            self.monitors.setItem(i, 0, QTableWidgetItem(t.name))
            self.monitors.setItem(i, 1, QTableWidgetItem(
                f"{t.value:g} {t.unit}  ({t.low:g}–{t.high:g})".strip()))
            it = QTableWidgetItem("Pass" if t.passed else "Fail")
            it.setForeground(C.QColor(C.GREEN if t.passed else C.RED))
            self.monitors.setItem(i, 2, it)

    def _clear(self, reps):
        names = ", ".join(r.ecu.name for r in reps)
        if not reps or not C.confirm(self, "Clear codes", f"Clear codes in: {names}?\n\nEngine OFF, ignition ON. "
                                                           f"Other modules are not touched.", "Clear"):
            return
        self._busy(True)
        o = self.s.obd

        def work():
            from .. import features as F
            with self.s.elm.lock:
                for r in reps:
                    o.clear_for(r.ecu)
                    F.record_clear(self.s.store, self.s.vin, "OBD:" + r.ecu.name)
        C.run_bg(work, lambda _: self.scan(), lambda m: (self._busy(False), C.error_box(m)))

    def clear_selected(self):
        it = self.tree.currentItem()
        while it and it.parent():
            it = it.parent()
        if it:
            self._clear([it.data(0, Qt.UserRole)])

    def clear_faulty(self):
        self._clear([r for r in self.reports if r.faulty])


# =================================================================== Logs
class _LogSig(QObject):
    line = Signal(str)


class LogsPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        w, lay = C.page()
        from PySide6.QtWidgets import QVBoxLayout
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        from ..elm import TRAFFIC
        self.traffic = TRAFFIC
        lay.addLayout(C.row(C.label("Logs", "h1"), "stretch",
                            C.button("Copy Adapter Log", slot=self.copy_log),
                            C.button("Open Log File", slot=lambda: self._open(str(TRAFFIC.path))),
                            C.button("Open Recordings Folder", "primary",
                                     slot=lambda: self._open(str(self.s.store.logs_dir())))))
        tabs = QTabWidget()
        # adapter traffic
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(3000)
        self.console.setStyleSheet("font-family: 'JetBrains Mono', 'DejaVu Sans Mono', monospace; font-size: 12px;")
        self.console.setPlainText("\n".join(TRAFFIC.tail))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter (e.g. 1902, 14FF, ERROR, TIMEOUT)…")
        self.filter.textChanged.connect(self._refilter)
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(0, 8, 0, 0)
        cl.addWidget(C.label(f"Every command sent to the adapter and its raw reply · saved to {TRAFFIC.path}", "muted"))
        cl.addWidget(self.filter)
        cl.addWidget(self.console, 1)
        tabs.addTab(cw, "Adapter log")
        # CSV recordings
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.UserRole))))
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.setContentsMargins(0, 8, 0, 0)
        rl.addWidget(C.label(f"Live-data CSV recordings in {s.store.logs_dir()} · double-click to open", "muted"))
        rl.addWidget(self.list, 1)
        tabs.addTab(rw, "Recordings")
        lay.addWidget(tabs, 1)
        self.sig = _LogSig()
        self.sig.line.connect(self._append)
        TRAFFIC.listeners.append(self.sig.line.emit)
        self.refresh()

    def _match(self, line):
        f = self.filter.text().strip().upper()
        return not f or f in line.upper()

    def _append(self, line):
        if self._match(line):
            self.console.appendPlainText(line)

    def _refilter(self):
        self.console.setPlainText("\n".join(l for l in self.traffic.tail if self._match(l)))
        self.console.moveCursor(self.console.textCursor().End)

    def copy_log(self):
        QApplication.clipboard().setText("\n".join(self.traffic.tail[-400:]))

    def refresh(self):
        self.list.clear()
        for f in sorted(self.s.store.logs_dir().glob("*.csv"), reverse=True):
            it = QListWidgetItem(f"{f.name}    {f.stat().st_size / 1024:.1f} KB")
            it.setData(Qt.UserRole, str(f))
            self.list.addItem(it)

    def _open(self, path):
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", path])

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)
