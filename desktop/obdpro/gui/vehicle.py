"""VW Group page: brand/model picker, car diagram with glowing faulty modules, per-module tools."""
from __future__ import annotations

import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGridLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QSplitter, QTabWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import catalog
from ..elm import ELMError, hex_bytes, to_hex
from ..vag import MODULE_BY_ADDR, MODULES, Report, decode_measurement, numeric, patch_number
from . import common as C
from .widgets import CarDiagram, Sparkline


def _hexid(text: str) -> int | None:
    try:
        v = int(text.strip(), 16)
        return v if 0 <= v <= 0xFFFF else None
    except ValueError:
        return None


# =================================================================== Vehicle page
class VehiclePage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        self.reports: dict[str, Report] = {}
        w, lay = C.page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.brand = QComboBox()
        for k, (disp, _col, _m) in catalog.BRANDS.items():
            self.brand.addItem(disp, k)
        self.model = QComboBox()
        self.model.setMinimumWidth(200)
        self.vin = C.label("", "muted")
        self.badge = QLabel()
        self.scan_btn = C.button("Full Scan", "primary", self.scan)
        self.clear_btn = C.button("Clear Faulty Modules", "danger", self.clear_faulty)
        lay.addLayout(C.row(self.badge, C.label("Vehicle", "h1"), self.brand, self.model, "stretch",
                            self.clear_btn, self.scan_btn))
        lay.addLayout(C.row(self.vin, "stretch", C.pill("Electronics", C.YELLOW), C.pill("Powertrain / Chassis", C.ORANGE),
                            C.pill("Safety", C.RED), C.pill("OK", C.GREEN)))
        self.progress = QProgressBar()
        self.progress.hide()
        lay.addWidget(self.progress)
        self.note = C.label("", "muted", True)
        lay.addWidget(self.note)

        split = QSplitter(Qt.Horizontal)
        self.car = CarDiagram()
        self.car.set_reports(MODULES, {})
        self.car.module_clicked.connect(self.open_module)
        split.addWidget(self.car)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Addr", "Module", "Status", "Part number"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.open_module(self.table.item(r, 0).text()))
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.table)
        rl.addWidget(C.label("Double-click a module (or a spot on the car) for faults, live data, coding, "
                             "adaptations, output tests and basic settings.", "muted", True))
        split.addWidget(right)
        split.setSizes([420, 640])
        lay.addWidget(split, 1)

        veh = s.store.get("vehicle", {}) or {}
        self.brand.setCurrentIndex(max(0, self.brand.findData(veh.get("brand", "seat"))))
        self._fill_models(veh.get("model"))
        self.brand.currentIndexChanged.connect(lambda _: self._fill_models(None))
        self.model.currentIndexChanged.connect(lambda _: self._vehicle_changed())
        s.info.connect(self.on_info)
        s.state_changed.connect(lambda *_: self._buttons())
        self._render()

    # ---- vehicle selection
    def _fill_models(self, select):
        key = self.brand.currentData()
        self.model.blockSignals(True)
        self.model.clear()
        for name, body in catalog.BRANDS[key][2]:
            self.model.addItem(name, body)
        if select:
            self.model.setCurrentIndex(max(0, self.model.findText(select)))
        self.model.blockSignals(False)
        self._vehicle_changed()

    def _vehicle_changed(self):
        key = self.brand.currentData()
        disp, col, _ = catalog.BRANDS[key]
        body = self.model.currentData() or "hatch"
        self.car.set_vehicle(col, body, catalog.BODY_ASPECT[body])
        self.badge.setText(disp.upper())
        self.badge.setStyleSheet(f"background: {col}; color: white; border-radius: 8px; padding: 4px 10px;"
                                 f"font-weight: 800; letter-spacing: 1px;")
        self.s.store.set("vehicle", {"brand": key, "model": self.model.currentText()})

    def on_info(self, info: dict):
        vin = info.get("vin")
        if vin:
            self.vin.setText(f"VIN {vin}")
            key = catalog.WMI.get(vin[:3].upper())
            if key and key != self.brand.currentData():
                self.brand.setCurrentIndex(self.brand.findData(key))
        self._buttons()

    def _buttons(self):
        ok = self.s.connected and self.s.vag is not None and self.s.vag.supported
        self.scan_btn.setEnabled(ok)
        self.clear_btn.setEnabled(ok and any(r.faulty for r in self.reports.values()))
        if self.s.connected and self.s.vag is not None and not self.s.vag.supported:
            self.note.setText("Module scan needs CAN 11-bit (2008+ MQB/MLB/MEB). Generic codes are on Diagnose.")
        else:
            self.note.setText("")

    # ---- scan / clear
    def scan(self):
        self.scan_btn.setEnabled(False)
        self.progress.show()
        self.progress.setValue(0)
        vag = self.s.vag
        sig = _Progress()
        sig.step.connect(lambda i, rep: (self.progress.setValue(int(100 * i / len(MODULES))),
                                         self.reports.__setitem__(rep.module.address, rep), self._render()))

        def work():
            for i, m in enumerate(MODULES, 1):
                sig.step.emit(i, vag.report(m))

        def done(_):
            self.progress.hide()
            self._buttons()
            self._render()

        C.run_bg(work, done, lambda m: (self.progress.hide(), self._buttons(), C.error_box(m)))

    def clear_faulty(self):
        faulty = [r for r in self.reports.values() if r.faulty]
        names = "\n".join(f"  {r.module.address} · {r.module.name}" for r in faulty)
        if not C.confirm(self, "Clear faulty modules", f"Clear faults only in:\n{names}\n\nModules without faults "
                                                        f"are not touched. Engine OFF, ignition ON.", "Clear"):
            return
        self.clear_btn.setEnabled(False)
        vag = self.s.vag

        def work():
            errs = []
            for r in faulty:
                try:
                    vag.clear(r.module)
                except ELMError as e:
                    errs.append(str(e))
                self.reports[r.module.address] = vag.report(r.module)
            return errs

        def done(errs):
            self._render()
            self._buttons()
            if errs:
                C.error_box("\n".join(errs))

        C.run_bg(work, done)

    def refresh_module(self, addr: str):
        vag = self.s.vag
        C.run_bg(lambda: vag.report(MODULE_BY_ADDR[addr]),
                 lambda r: (self.reports.__setitem__(addr, r), self._render(), self._buttons()))

    def _render(self):
        self.car.set_reports(MODULES, self.reports)
        reps = [self.reports[m.address] for m in MODULES if m.address in self.reports and self.reports[m.address].present]
        reps.sort(key=lambda r: (not r.faulty, r.module.address))
        self.table.setRowCount(len(reps))
        for i, r in enumerate(reps):
            self.table.setItem(i, 0, QTableWidgetItem(r.module.address))
            self.table.setItem(i, 1, QTableWidgetItem(r.module.name))
            st = QTableWidgetItem(f"{len(r.faults)} fault(s)" if r.faulty else "No faults")
            st.setForeground(QColor(r.module.color if r.faulty else C.GREEN))
            self.table.setItem(i, 2, st)
            self.table.setItem(i, 3, QTableWidgetItem(r.part or ""))

    def open_module(self, addr: str):
        if not self.s.connected:
            return C.error_box("Connect first.")
        m = MODULE_BY_ADDR[addr]
        dlg = ModuleDialog(self, self.s, m, self.reports.get(addr))
        dlg.finished.connect(lambda _: self.refresh_module(addr) if self.s.connected else None)
        dlg.show()


class _Progress(QObject):
    step = Signal(int, object)


# =================================================================== Module dialog
class ModuleDialog(QDialog):
    def __init__(self, parent, s, m, report: Report | None):
        super().__init__(parent)
        self.s, self.m = s, m
        self.setWindowTitle(f"{m.address} · {m.name}")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.addWidget(C.label(f"{m.address} · {m.name}", "h1"))
        tabs = QTabWidget()
        tabs.addTab(FaultsTab(s, m, report), "Faults")
        tabs.addTab(LiveTab(s, m), "Live Data")
        tabs.addTab(CodingTab(s, m), "Coding")
        tabs.addTab(AdaptationTab(s, m), "Adaptations")
        tabs.addTab(OutputTab(s, m), "Output Tests")
        tabs.addTab(BasicTab(s, m), "Basic Settings")
        tabs.addTab(IdentTab(s, m), "Identification")
        lay.addWidget(tabs, 1)
        self.tabs = tabs

    def done(self, r):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "shutdown"):
                w.shutdown()
        super().done(r)


def _tab():
    w = QWidget()
    l = QVBoxLayout(w)
    l.setContentsMargins(4, 12, 4, 4)
    l.setSpacing(10)
    return w, l


# ------------------------------------------------------------------- Faults
class FaultsTab(QWidget):
    def __init__(self, s, m, report):
        super().__init__()
        self.s, self.m = s, m
        _, l = _tab()
        QVBoxLayout(self).addWidget(_)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Code", "State", "Description", "Fault type"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.clear = C.button("Clear This Module", "danger", self.do_clear)
        l.addLayout(C.row(C.button("Refresh", slot=self.refresh), "stretch", self.clear))
        l.addWidget(self.table, 1)
        self.render(report) if report else self.refresh()

    def render(self, r: Report):
        self.table.setRowCount(len(r.faults))
        for i, f in enumerate(r.faults):
            self.table.setItem(i, 0, QTableWidgetItem(f.code))
            st = QTableWidgetItem("Active" if f.active else "Stored")
            st.setForeground(QColor(self.m.color if f.active else C.MUTED))
            self.table.setItem(i, 1, st)
            self.table.setItem(i, 2, QTableWidgetItem(f.description))
            self.table.setItem(i, 3, QTableWidgetItem(f.detail))
        self.clear.setEnabled(r.faulty)

    def refresh(self):
        C.run_bg(lambda: self.s.vag.report(self.m), self.render)

    def do_clear(self):
        if C.confirm(self, "Clear", f"Clear faults in {self.m.name} only?", "Clear"):
            C.run_bg(lambda: (self.s.vag.clear(self.m), self.s.vag.report(self.m))[1], self.render)


# ------------------------------------------------------------------- Live data
class MeasurementDialog(QDialog):
    KINDS = ["number", "hex", "ascii"]

    def __init__(self, parent, d: dict, adaptation: bool = False):
        super().__init__(parent)
        self.d = dict(d)
        self.setWindowTitle("Adaptation" if adaptation else "Measurement")
        f = QFormLayout(self)
        self.name = QLineEdit(d.get("name", ""))
        self.did = QLineEdit(f"{d['did']:04X}" if d.get("did") else "")
        self.kind = QComboBox()
        kinds = self.KINDS + (["toggle"] if adaptation else [])
        self.kinds = kinds
        self.kind.addItems([k.capitalize() for k in kinds])
        self.kind.setCurrentIndex(kinds.index(d.get("kind", "number")))
        self.offset = QSpinBox()
        self.offset.setRange(0, 64)
        self.offset.setValue(d.get("offset", 0))
        self.length = QComboBox()
        self.length.addItems(["1", "2", "4"])
        self.length.setCurrentText(str(d.get("length", 2 if not adaptation else 1)))
        self.signed = QCheckBox("Signed")
        self.signed.setChecked(d.get("signed", False))
        self.scale = QDoubleSpinBox()
        self.scale.setDecimals(6)
        self.scale.setRange(-1e6, 1e6)
        self.scale.setValue(d.get("scale", 1))
        self.add = QDoubleSpinBox()
        self.add.setDecimals(4)
        self.add.setRange(-1e6, 1e6)
        self.add.setValue(d.get("add", 0))
        self.unit = QLineEdit(d.get("unit", ""))
        f.addRow("Name", self.name)
        f.addRow("DID (hex)", self.did)
        f.addRow("Type", self.kind)
        f.addRow("Byte offset", self.offset)
        f.addRow("Length (bytes)", self.length)
        f.addRow("", self.signed)
        f.addRow("Scale (value = raw × scale + offset)", self.scale)
        f.addRow("Offset", self.add)
        f.addRow("Unit", self.unit)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _ok(self):
        did = _hexid(self.did.text())
        if did is None:
            return C.error_box("DID must be hex, e.g. 1000", self)
        self.d.update(did=did, name=self.name.text().strip() or f"DID {did:04X}",
                      kind=self.kinds[self.kind.currentIndex()], offset=self.offset.value(),
                      length=int(self.length.currentText()), signed=self.signed.isChecked(),
                      scale=self.scale.value(), add=self.add.value(), unit=self.unit.text().strip())
        if self.d["kind"] == "toggle":
            self.d["length"] = 1
        self.accept()


class ScanDialog(QDialog):
    """Probe a DID range and pick one."""

    def __init__(self, parent, s, m):
        super().__init__(parent)
        self.s, self.m = s, m
        self.picked = None
        self.setWindowTitle(f"Scan identifiers · {m.name}")
        self.resize(560, 480)
        l = QVBoxLayout(self)
        self.a = QLineEdit("0100")
        self.b = QLineEdit("04FF")
        self.go = C.button("Start", "primary", self.start)
        self.stop_btn = C.button("Stop", slot=lambda: self._stop.set())
        l.addLayout(C.row(C.label("From"), self.a, C.label("To"), self.b, "stretch", self.stop_btn, self.go))
        self.bar = QProgressBar()
        self.info = C.label("", "muted")
        l.addWidget(self.bar)
        l.addWidget(self.info)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._pick)
        l.addWidget(self.list, 1)
        l.addWidget(C.label("Double-click a result to use it.", "muted"))
        self._stop = threading.Event()
        self.sig = _Progress()
        self.sig.step.connect(lambda pct, n: (self.bar.setValue(pct), self.info.setText(f"{n} found")))

    def start(self):
        a, b = _hexid(self.a.text()), _hexid(self.b.text())
        if a is None or b is None or a > b:
            return C.error_box("Enter a valid hex range", self)
        self._stop.clear()
        self.go.setEnabled(False)
        self.list.clear()

        def done(res):
            self.go.setEnabled(True)
            self.bar.setValue(100)
            self.info.setText(f"{len(res)} identifiers respond")
            for did, p in res:
                it = QListWidgetItem(f"{did:04X}    {to_hex(p[:24], ' ')}")
                it.setData(Qt.UserRole, (did, p))
                self.list.addItem(it)

        C.run_bg(lambda: self.s.vag.scan_dids(self.m, a, b, lambda f, n: self.sig.step.emit(int(f * 100), n),
                                              self._stop.is_set), done,
                 lambda e: (self.go.setEnabled(True), C.error_box(e, self)))

    def _pick(self, it):
        self.picked = it.data(Qt.UserRole)
        self.accept()

    def reject(self):
        self._stop.set()
        super().reject()


class _LiveSig(QObject):
    value = Signal(str, str, object)


class LiveTab(QWidget):
    def __init__(self, s, m):
        super().__init__()
        self.s, self.m = s, m
        _, l = _tab()
        QVBoxLayout(self).addWidget(_)
        self.run_btn = C.button("▶ Start", "primary", self.toggle)
        l.addLayout(C.row(C.button("Scan Module…", slot=self.scan), C.button("+ Add", slot=self.add),
                          C.button("Edit", slot=self.edit), C.button("Remove", slot=self.remove),
                          "stretch", self.run_btn))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Measurement", "DID", "Value", "Trend"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        l.addWidget(self.table, 1)
        l.addWidget(C.label("Measurement names and scaling are yours to define — scan the module, then add what "
                            "responds.", "muted", True))
        self.sig = _LiveSig()
        self.sig.value.connect(self._on_value)
        self._stop = threading.Event()
        self._thread = None
        self.render()

    def defs(self):
        return self.s.store.items("measurements", self.m.address)

    def render(self):
        ds = self.defs()
        self.table.setRowCount(len(ds))
        self.sparks = {}
        for i, d in enumerate(ds):
            it = QTableWidgetItem(d["name"])
            it.setData(Qt.UserRole, d)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(f"{d['did']:04X}"))
            v = QTableWidgetItem("…")
            v.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 2, v)
            sp = Sparkline()
            self.sparks[d["id"]] = (i, sp)
            self.table.setCellWidget(i, 3, sp)

    def _on_value(self, did_id, text, num):
        if did_id in self.sparks:
            row, sp = self.sparks[did_id]
            self.table.item(row, 2).setText(text)
            if num is not None:
                sp.push(num)

    def toggle(self):
        if self._thread:
            self.shutdown()
            return
        self._stop.clear()
        self.run_btn.setText("■ Stop")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        vag = self.s.vag
        while not self._stop.is_set():
            ds = self.defs()
            if not ds:
                time.sleep(0.3)
                continue
            try:
                with vag.channel(self.m):
                    t_end = time.monotonic() + 1.0            # release the bus about once a second
                    while not self._stop.is_set() and time.monotonic() < t_end:
                        cache = {}
                        for d in ds:
                            if d["did"] not in cache:
                                try:
                                    cache[d["did"]] = vag.read_did(d["did"])
                                except ELMError:
                                    cache[d["did"]] = []
                            p = cache[d["did"]]
                            self.sig.value.emit(d["id"], decode_measurement(d, p) if p else "—",
                                                numeric(d, p) if p else None)
            except Exception:                                  # noqa: BLE001
                time.sleep(0.5)
            time.sleep(0.02)

    def shutdown(self):
        self._stop.set()
        self._thread = None
        self.run_btn.setText("▶ Start")

    def _save(self, d):
        d["module"] = self.m.address
        self.s.store.upsert("measurements", d)
        self.render()

    def add(self, preset=None):
        dlg = MeasurementDialog(self, preset or {})
        if dlg.exec():
            self._save(dlg.d)

    def edit(self):
        r = self.table.currentRow()
        if r >= 0:
            dlg = MeasurementDialog(self, self.table.item(r, 0).data(Qt.UserRole))
            if dlg.exec():
                self._save(dlg.d)

    def remove(self):
        r = self.table.currentRow()
        if r >= 0:
            self.s.store.delete("measurements", self.table.item(r, 0).data(Qt.UserRole)["id"])
            self.render()

    def scan(self):
        was = self._thread is not None
        self.shutdown()
        dlg = ScanDialog(self, self.s, self.m)
        if dlg.exec() and dlg.picked:
            did, p = dlg.picked
            self.add({"did": did, "kind": "number" if len(p) <= 4 else "hex", "length": min(max(len(p), 1), 2)})
        if was:
            self.toggle()


# ------------------------------------------------------------------- Coding
class CodingTab(QWidget):
    def __init__(self, s, m):
        super().__init__()
        self.s, self.m = s, m
        self.original: list[int] = []
        self.coding: list[int] = []
        self.sel = 0
        _, l = _tab()
        QVBoxLayout(self).addWidget(_)
        self.write_btn = C.button("Write Coding", "primary", self.write)
        self.revert_btn = C.button("Revert", slot=self.revert)
        l.addLayout(C.row(C.button("Read", slot=self.read), "stretch", self.revert_btn, self.write_btn))
        self.hex = QLineEdit()
        self.hex.setStyleSheet("font-family: monospace; font-size: 14px;")
        self.hex.textEdited.connect(self._hex_edited)
        l.addWidget(self.hex)
        mid = QSplitter(Qt.Horizontal)
        self.grid_w = QWidget()
        self.grid = QGridLayout(self.grid_w)
        self.grid.setSpacing(6)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        mid.addWidget(self.grid_w)
        bits_w = QWidget()
        bl = QVBoxLayout(bits_w)
        self.byte_lbl = C.label("Byte —", "h2")
        bl.addWidget(self.byte_lbl)
        self.bits = []
        for b in range(7, -1, -1):
            cb = QCheckBox(f"Bit {b}")
            cb.toggled.connect(lambda on, b=b: self._bit(b, on))
            bl.addWidget(cb)
            self.bits.append((b, cb))
        bl.addWidget(C.button("Save change as One-Tap…", slot=self.save_recipe))
        bl.addStretch(1)
        mid.addWidget(bits_w)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(C.label("One-Tap (double-click to apply)", "h2"))
        self.recipes = QListWidget()
        self.recipes.itemDoubleClicked.connect(self.apply_recipe)
        rl.addWidget(self.recipes)
        rl.addWidget(C.label("Backups (double-click to load)", "h2"))
        self.backups = QListWidget()
        self.backups.itemDoubleClicked.connect(lambda it: self._set(list(it.data(Qt.UserRole)["coding"])))
        rl.addWidget(self.backups)
        mid.addWidget(right)
        mid.setSizes([380, 160, 320])
        l.addWidget(mid, 1)
        self._lists()
        self._refresh_ui()

    def read(self):
        def done(c):
            self.original = list(c)
            self._set(list(c))
        C.run_bg(lambda: self.s.vag.read_coding(self.m), done)

    def _set(self, c):
        self.coding = c
        self.sel = min(self.sel, max(0, len(c) - 1))
        self._refresh_ui()

    def _hex_edited(self, t):
        b = hex_bytes(t)
        if self.original and len(b) == len(self.original):
            self.coding = b
            self._refresh_ui(keep_hex=True)

    def _refresh_ui(self, keep_hex=False):
        if not keep_hex:
            self.hex.setText(to_hex(self.coding))
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, v in enumerate(self.coding):
            b = QPushButton(f"{v:02X}\n{i}")
            diff = i < len(self.original) and self.original[i] != v
            col = C.ACCENT if i == self.sel else (C.ORANGE if diff else C.CARD2)
            b.setStyleSheet(f"background: {QColor(col).darker(160 if i != self.sel else 120).name() if col != C.CARD2 else C.CARD2};"
                            f"border: 1px solid {col}; font-family: monospace; font-weight: 600; padding: 6px;")
            b.clicked.connect(lambda _=False, i=i: self._select(i))
            self.grid.addWidget(b, i // 6, i % 6)
        if self.coding:
            v = self.coding[self.sel]
            self.byte_lbl.setText(f"Byte {self.sel} = {v:02X}")
            for b, cb in self.bits:
                cb.blockSignals(True)
                cb.setChecked(bool(v & (1 << b)))
                changed = self.sel < len(self.original) and (self.original[self.sel] ^ v) & (1 << b)
                cb.setStyleSheet(f"color: {C.ORANGE}" if changed else "")
                cb.blockSignals(False)
        changed = self.coding != self.original and bool(self.coding)
        self.write_btn.setEnabled(changed and self.s.connected)
        self.revert_btn.setEnabled(changed)

    def _select(self, i):
        self.sel = i
        self._refresh_ui()

    def _bit(self, b, on):
        if not self.coding:
            return
        v = self.coding[self.sel]
        self.coding[self.sel] = v | (1 << b) if on else v & ~(1 << b)
        self._refresh_ui()

    def revert(self):
        self._set(list(self.original))

    def write(self):
        if not C.confirm(self, "Write coding", f"{to_hex(self.original)}\n→\n{to_hex(self.coding)}\n\n"
                                               f"Current coding is backed up first.", "Write"):
            return
        self.s.store.prepend("backups", {"module": self.m.address, "vin": self.s.vin or "",
                                         "date": datetime.now().isoformat(timespec="seconds"),
                                         "coding": self.original, "note": "Before change"})
        new = list(self.coding)

        def done(back):
            if back != new:
                C.error_box(f"Verify failed: module reports {to_hex(back)}")
            self.original = list(back)
            self._set(list(back))
            self._lists()

        C.run_bg(lambda: self.s.vag.write_did_verified(self.m, 0x0600, new), done)

    def _lists(self):
        self.recipes.clear()
        for r in self.s.store.items("recipes", self.m.address):
            it = QListWidgetItem(f"{r['name']}    B{r['byte']} &{r['mask']:02X}={r['value'] & r['mask']:02X}")
            it.setData(Qt.UserRole, r)
            self.recipes.addItem(it)
        self.backups.clear()
        for b in self.s.store.items("backups", self.m.address):
            it = QListWidgetItem(f"{b['date']}    {to_hex(b['coding'])}")
            it.setData(Qt.UserRole, b)
            self.backups.addItem(it)

    def save_recipe(self):
        changes = [(i, self.original[i] ^ v, v) for i, v in enumerate(self.coding)
                   if i < len(self.original) and self.original[i] != v]
        if not changes:
            return C.error_box("Change some bits first.")
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "One-Tap", "Name (e.g. Needle sweep):")
        if ok and name.strip():
            for i, mask, v in changes:
                self.s.store.upsert("recipes", {"module": self.m.address,
                                                "name": name.strip() + (f" (B{i})" if len(changes) > 1 else ""),
                                                "byte": i, "mask": mask, "value": v})
            self._lists()

    def apply_recipe(self, it):
        r = it.data(Qt.UserRole)
        if r["byte"] < len(self.coding):
            self.coding[r["byte"]] = (self.coding[r["byte"]] & ~r["mask"]) | (r["value"] & r["mask"])
            self._refresh_ui()


# ------------------------------------------------------------------- Adaptations
class AdaptationTab(QWidget):
    def __init__(self, s, m):
        super().__init__()
        self.s, self.m = s, m
        self.original: list[int] = []
        _, l = _tab()
        QVBoxLayout(self).addWidget(_)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(C.row(C.button("Scan…", slot=self.scan), C.button("+ Add", slot=lambda: self.add()),
                           C.button("Edit", slot=self.edit), C.button("Remove", slot=self.remove)))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self.read())
        ll.addWidget(self.list)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.title = C.label("Select a channel", "h2")
        self.raw = C.label("", "muted")
        self.value_lbl = C.label("", "h2")
        self.edit_num = QDoubleSpinBox()
        self.edit_num.setDecimals(3)
        self.edit_num.setRange(-1e9, 1e9)
        self.edit_toggle = QCheckBox("Enabled")
        self.edit_text = QLineEdit()
        self.write_btn = C.button("Write", "primary", self.write)
        self.hist = QListWidget()
        self.hist.itemDoubleClicked.connect(lambda it: self._load(list(it.data(Qt.UserRole)["coding"])))
        for w in (self.title, self.raw, self.value_lbl, C.label("New value", "muted"), self.edit_num,
                  self.edit_toggle, self.edit_text):
            rl.addWidget(w)
        rl.addLayout(C.row(C.button("Re-read", slot=self.read), "stretch", self.write_btn))
        rl.addWidget(C.label("History (double-click to load, then Write to restore)", "muted"))
        rl.addWidget(self.hist, 1)
        split.addWidget(right)
        split.setSizes([300, 520])
        l.addWidget(split, 1)
        self.render()
        self._mode(None)

    def defs(self):
        return self.s.store.items("adaptations", self.m.address)

    def current(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def render(self):
        self.list.clear()
        for a in self.defs():
            it = QListWidgetItem(f"{a['name']}   ({a['did']:04X} · {a.get('kind', 'number')})")
            it.setData(Qt.UserRole, a)
            self.list.addItem(it)

    def _mode(self, kind):
        self.edit_num.setVisible(kind == "number")
        self.edit_toggle.setVisible(kind == "toggle")
        self.edit_text.setVisible(kind in ("ascii", "hex"))
        self.write_btn.setEnabled(kind is not None and self.s.connected)

    def read(self):
        a = self.current()
        if not a:
            return
        self.title.setText(a["name"])
        self._mode(a.get("kind", "number"))
        self.hist.clear()
        for b in self.s.store.items("backups", f"{self.m.address}/A/{a['did']:04X}"):
            it = QListWidgetItem(f"{b['date']}    {to_hex(b['coding'], ' ')}")
            it.setData(Qt.UserRole, b)
            self.hist.addItem(it)
        C.run_bg(lambda: self.s.vag.read_one(self.m, a["did"]), self._loaded)

    def _loaded(self, p):
        self.original = list(p)
        self._load(list(p))

    def _load(self, p):
        a = self.current()
        if not a:
            return
        self.raw.setText("Raw: " + to_hex(self.original, " "))
        k = a.get("kind", "number")
        if k == "number":
            v = numeric(a, p)
            self.value_lbl.setText(decode_measurement(a, self.original))
            if v is not None:
                self.edit_num.setValue(v)
        elif k == "toggle":
            o = a.get("offset", 0)
            self.value_lbl.setText("On" if o < len(self.original) and self.original[o] else "Off")
            self.edit_toggle.setChecked(o < len(p) and bool(p[o]))
        elif k == "ascii":
            self.value_lbl.setText(decode_measurement(a, self.original))
            self.edit_text.setText(bytes(b for b in p[a.get("offset", 0):] if 0x20 <= b <= 0x7E).decode())
        else:
            self.value_lbl.setText("")
            self.edit_text.setText(to_hex(p))

    def _new_payload(self):
        a, p = self.current(), self.original
        k = a.get("kind", "number")
        o = a.get("offset", 0)
        if k == "number":
            return patch_number(a, p, self.edit_num.value())
        if k == "toggle":
            if o >= len(p):
                return None
            out = list(p)
            out[o] = 1 if self.edit_toggle.isChecked() else 0
            return out
        if k == "ascii":
            raw = list(self.edit_text.text().encode()[:len(p) - o])
            return p[:o] + raw + [0x20] * (len(p) - o - len(raw))
        b = hex_bytes(self.edit_text.text())
        return b if len(b) == len(p) else None

    def write(self):
        a = self.current()
        if not a or not self.original:
            return
        new = self._new_payload()
        if new is None:
            return C.error_box("Value out of range for this channel.")
        if new == self.original:
            return
        if not C.confirm(self, "Write adaptation", f"{a['name']}\n{to_hex(self.original, ' ')}\n→\n{to_hex(new, ' ')}"
                                                   f"\n\nPrevious value is saved to history.", "Write"):
            return
        self.s.store.prepend("backups", {"module": f"{self.m.address}/A/{a['did']:04X}", "vin": self.s.vin or "",
                                         "date": datetime.now().isoformat(timespec="seconds"),
                                         "coding": self.original, "note": a["name"]})

        def done(back):
            if back != new:
                C.error_box(f"Verify failed: module reports {to_hex(back, ' ')}")
            self.read()

        C.run_bg(lambda: self.s.vag.write_did_verified(self.m, a["did"], new), done)

    def add(self, preset=None):
        dlg = MeasurementDialog(self, preset or {"length": 1}, adaptation=True)
        if dlg.exec():
            dlg.d["module"] = self.m.address
            self.s.store.upsert("adaptations", dlg.d)
            self.render()

    def edit(self):
        a = self.current()
        if a:
            dlg = MeasurementDialog(self, a, adaptation=True)
            if dlg.exec():
                self.s.store.upsert("adaptations", dlg.d)
                self.render()

    def remove(self):
        a = self.current()
        if a:
            self.s.store.delete("adaptations", a["id"])
            self.render()

    def scan(self):
        dlg = ScanDialog(self, self.s, self.m)
        if dlg.exec() and dlg.picked:
            did, p = dlg.picked
            kind = "number" if len(p) <= 4 else ("ascii" if all(0x20 <= b <= 0x7E for b in p) else "hex")
            self.add({"did": did, "kind": kind, "length": min(len(p), 4) if len(p) in (1, 2, 4) else 1})


# ------------------------------------------------------------------- Output tests
class OutputDialog(QDialog):
    def __init__(self, parent, t: dict):
        super().__init__(parent)
        self.t = dict(t)
        self.setWindowTitle("Output test")
        f = QFormLayout(self)
        self.name = QLineEdit(t.get("name", ""))
        self.method = QComboBox()
        self.method.addItems(["I/O Control (2F)", "Routine (31)"])
        self.method.setCurrentIndex(0 if t.get("method", "io") == "io" else 1)
        self.ident = QLineEdit(f"{t['id']:04X}" if t.get("id") else "")
        self.data = QLineEdit(t.get("data", ""))
        self.dur = QSpinBox()
        self.dur.setRange(1, 120)
        self.dur.setValue(int(t.get("duration", 10)))
        self.preview = C.label("", "muted")
        for w in (self.method, self.ident, self.data):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.textChanged).connect(self._pv)
        f.addRow("Name", self.name)
        f.addRow("Method", self.method)
        f.addRow("DID / Routine ID (hex)", self.ident)
        f.addRow("Control data (hex, optional)", self.data)
        f.addRow("Auto-stop (s)", self.dur)
        f.addRow(self.preview)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._pv()

    def _pv(self):
        i = self.ident.text().upper() or "????"
        d = self.data.text().upper().replace(" ", "")
        self.preview.setText(f"Start: 2F{i}03{d}   Stop: 2F{i}00" if self.method.currentIndex() == 0
                             else f"Start: 3101{i}{d}   Stop: 3102{i}")

    def _ok(self):
        i = _hexid(self.ident.text())
        if i is None or not self.name.text().strip():
            return C.error_box("Name and hex identifier required.", self)
        self.t.update(name=self.name.text().strip(), method="io" if self.method.currentIndex() == 0 else "routine",
                      id=i, data=to_hex(hex_bytes(self.data.text())), duration=self.dur.value())
        self.accept()


class _Status(QObject):
    text = Signal(str)
    upd = Signal(object)


class OutputTab(QWidget):
    def __init__(self, s, m):
        super().__init__()
        self.s, self.m = s, m
        _, l = _tab()
        QVBoxLayout(self).addWidget(_)
        self.start_btn = C.button("▶ Start", "primary", self.start)
        self.stop_btn = C.button("■ Stop", "danger", self.stop)
        l.addLayout(C.row(C.button("+ Add", slot=lambda: self.add()), C.button("Edit", slot=self.edit),
                          C.button("Remove", slot=self.remove), "stretch", self.stop_btn, self.start_btn))
        self.list = QListWidget()
        l.addWidget(self.list, 1)
        self.status = C.label("", "h2")
        l.addWidget(self.status)
        self.sig = _Status()
        self.sig.text.connect(lambda t: self.status.setText("⚡ " + t))
        self._stop = threading.Event()
        self._running = False
        self.render()
        self._buttons()

    def render(self):
        self.list.clear()
        for t in self.s.store.items("output_tests", self.m.address):
            kind = "2F" if t["method"] == "io" else "31"
            it = QListWidgetItem(f"{t['name']}    {kind} {t['id']:04X} {t.get('data', '')}  · {t['duration']}s")
            it.setData(Qt.UserRole, t)
            self.list.addItem(it)

    def _buttons(self):
        self.start_btn.setEnabled(not self._running and self.s.connected)
        self.stop_btn.setEnabled(self._running)
        self.status.setStyleSheet(f"color: {C.YELLOW}")

    def start(self):
        it = self.list.currentItem()
        if not it:
            return
        t = it.data(Qt.UserRole)
        self._stop.clear()
        self._running = True
        self._buttons()

        def done(_):
            self._running = False
            self.status.setText(f"Finished: {t['name']}")
            self.status.setStyleSheet(f"color: {C.GREEN}")
            self.start_btn.setEnabled(self.s.connected)
            self.stop_btn.setEnabled(False)

        def fail(m):
            self._running = False
            self._buttons()
            self.status.setText("")
            C.error_box(m)

        C.run_bg(lambda: self.s.vag.run_output_test(self.m, t, self._stop.is_set, self.sig.text.emit), done, fail)

    def stop(self):
        self._stop.set()

    def shutdown(self):
        self._stop.set()

    def add(self, preset=None):
        dlg = OutputDialog(self, preset or {})
        if dlg.exec():
            dlg.t["module"] = self.m.address
            self.s.store.upsert("output_tests", dlg.t)
            self.render()

    def edit(self):
        it = self.list.currentItem()
        if it:
            dlg = OutputDialog(self, it.data(Qt.UserRole))
            if dlg.exec():
                self.s.store.upsert("output_tests", dlg.t)
                self.render()

    def remove(self):
        it = self.list.currentItem()
        if it:
            self.s.store.delete("output_tests", it.data(Qt.UserRole)["id"])
            self.render()


# ------------------------------------------------------------------- Basic settings
class BasicDialog(QDialog):
    def __init__(self, parent, s, m, b: dict):
        super().__init__(parent)
        self.b = dict(b)
        self.setWindowTitle("Basic setting")
        f = QFormLayout(self)
        self.name = QLineEdit(b.get("name", ""))
        self.rid = QLineEdit(f"{b['routine']:04X}" if b.get("routine") else "")
        self.data = QLineEdit(b.get("data", ""))
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 600)
        self.timeout.setValue(int(b.get("timeout", 60)))
        self.cond = QPlainTextEdit(b.get("conditions", ""))
        self.cond.setFixedHeight(60)
        self.done_on = QCheckBox("Detect completion")
        self.done_on.setChecked(b.get("done_offset") is not None)
        self.done_off = QSpinBox()
        self.done_off.setRange(0, 32)
        self.done_off.setValue(b.get("done_offset") or 0)
        self.done_val = QLineEdit(f"{b.get('done_value', 0):02X}")
        self.fail_val = QLineEdit(f"{b['fail_value']:02X}" if b.get("fail_value") is not None else "")
        self.watch = QListWidget()
        self.watch.setFixedHeight(90)
        for meas in s.store.items("measurements", m.address):
            it = QListWidgetItem(meas["name"])
            it.setData(Qt.UserRole, meas["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if meas["id"] in b.get("watch", []) else Qt.Unchecked)
            self.watch.addItem(it)
        f.addRow("Name", self.name)
        f.addRow("Routine ID (hex)", self.rid)
        f.addRow("Start data (hex, optional)", self.data)
        f.addRow("Timeout (s)", self.timeout)
        f.addRow("Conditions", self.cond)
        f.addRow(self.done_on)
        f.addRow("Result byte", self.done_off)
        f.addRow("Done when = (hex)", self.done_val)
        f.addRow("Failed when = (hex, optional)", self.fail_val)
        f.addRow("Watch live values", self.watch)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _ok(self):
        r = _hexid(self.rid.text())
        if r is None or not self.name.text().strip():
            return C.error_box("Name and hex routine ID required.", self)
        watch = [self.watch.item(i).data(Qt.UserRole) for i in range(self.watch.count())
                 if self.watch.item(i).checkState() == Qt.Checked]
        self.b.update(name=self.name.text().strip(), routine=r, data=to_hex(hex_bytes(self.data.text())),
                      timeout=self.timeout.value(), conditions=self.cond.toPlainText().strip(), watch=watch,
                      done_offset=self.done_off.value() if self.done_on.isChecked() else None,
                      done_value=int(self.done_val.text() or "0", 16),
                      fail_value=int(self.fail_val.text(), 16) if self.done_on.isChecked() and self.fail_val.text()
                      else None)
        self.accept()


class BasicTab(QWidget):
    PHASE = {"starting": ("Starting routine…", C.ACCENT), "running": ("Running — keep conditions stable", C.ACCENT),
             "stopping": ("Stopping…", C.YELLOW), "done": ("Completed successfully", C.GREEN),
             "failed": ("Routine reported failure", C.RED), "stopped": ("Stopped", C.MUTED),
             "timedOut": ("Timed out", C.RED)}

    def __init__(self, s, m):
        super().__init__()
        self.s, self.m = s, m
        _, l = _tab()
        QVBoxLayout(self).addWidget(_)
        self.start_btn = C.button("▶ Start", "primary", self.start)
        self.stop_btn = C.button("■ Stop", "danger", lambda: self._stop.set())
        l.addLayout(C.row(C.button("+ Add", slot=lambda: self.edit(new=True)), C.button("Edit", slot=self.edit),
                          C.button("Remove", slot=self.remove), "stretch", self.stop_btn, self.start_btn))
        self.list = QListWidget()
        self.list.setFixedHeight(130)
        self.list.currentItemChanged.connect(lambda *_: self._show_conditions())
        l.addWidget(self.list)
        self.cond = C.label("", "muted", True)
        l.addWidget(self.cond)
        self.phase = C.label("Ready", "h2")
        self.bar = QProgressBar()
        self.elapsed = C.label("", "muted")
        self.result = C.label("", "")
        self.result.setStyleSheet("font-family: monospace;")
        self.watch = QTableWidget(0, 2)
        self.watch.setHorizontalHeaderLabels(["Live value", ""])
        self.watch.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.watch.verticalHeader().hide()
        l.addWidget(C.card(self.phase, self.bar, C.row(self.elapsed, "stretch", self.result)))
        l.addWidget(self.watch, 1)
        self.sig = _Status()
        self.sig.upd.connect(self._update)
        self._stop = threading.Event()
        self._running = False
        self.current_b = None
        self.render()
        self._buttons()

    def render(self):
        self.list.clear()
        for b in self.s.store.items("basic_settings", self.m.address):
            it = QListWidgetItem(f"{b['name']}    routine {b['routine']:04X} {b.get('data', '')}")
            it.setData(Qt.UserRole, b)
            self.list.addItem(it)

    def _show_conditions(self):
        it = self.list.currentItem()
        b = it.data(Qt.UserRole) if it else None
        self.cond.setText(f"☑ {b['conditions']}" if b and b.get("conditions") else "")

    def _buttons(self):
        self.start_btn.setEnabled(not self._running and self.s.connected)
        self.stop_btn.setEnabled(self._running)

    def start(self):
        it = self.list.currentItem()
        if not it:
            return
        b = it.data(Qt.UserRole)
        if b.get("conditions") and not C.confirm(self, b["name"], f"Conditions:\n{b['conditions']}", "Start"):
            return
        self.current_b = b
        watch_defs = [d for d in self.s.store.items("measurements", self.m.address) if d["id"] in b.get("watch", [])]
        self.watch.setRowCount(len(watch_defs))
        self._watch_rows = {}
        for i, d in enumerate(watch_defs):
            self.watch.setItem(i, 0, QTableWidgetItem(d["name"]))
            self.watch.setItem(i, 1, QTableWidgetItem("—"))
            self._watch_rows[d["id"]] = i
        self._stop.clear()
        self._running = True
        self._buttons()
        self._update({"phase": "starting", "elapsed": 0, "result": ""})

        def done(final):
            self._running = False
            self._update({"phase": final})
            self._buttons()

        def fail(msg):
            self._running = False
            self.phase.setText(msg)
            self.phase.setStyleSheet(f"color: {C.RED}")
            self._buttons()

        C.run_bg(lambda: self.s.vag.run_basic_setting(self.m, b, self._stop.is_set,
                                                      lambda **k: self.sig.upd.emit(k), watch_defs), done, fail)

    def _update(self, k: dict):
        if "phase" in k:
            text, col = self.PHASE.get(k["phase"], (k["phase"], C.TEXT))
            self.phase.setText(text)
            self.phase.setStyleSheet(f"color: {col}")
            if k["phase"] == "done":
                self.bar.setValue(100)
        if "elapsed" in k and self.current_b:
            self.elapsed.setText(f"{k['elapsed']:.0f} s")
            self.bar.setValue(int(100 * min(1, k["elapsed"] / max(1, self.current_b.get("timeout", 60)))))
        if "result" in k:
            self.result.setText(f"Result: {k['result']}" if k["result"] else "")
        for wid, val in k.get("watch", {}).items():
            if wid in self._watch_rows:
                self.watch.item(self._watch_rows[wid], 1).setText(val)

    def shutdown(self):
        self._stop.set()

    def edit(self, new=False):
        it = self.list.currentItem()
        b = {} if new or not it else it.data(Qt.UserRole)
        dlg = BasicDialog(self, self.s, self.m, b)
        if dlg.exec():
            dlg.b["module"] = self.m.address
            self.s.store.upsert("basic_settings", dlg.b)
            self.render()

    def remove(self):
        it = self.list.currentItem()
        if it:
            self.s.store.delete("basic_settings", it.data(Qt.UserRole)["id"])
            self.render()


# ------------------------------------------------------------------- Identification
class IdentTab(QWidget):
    def __init__(self, s, m):
        super().__init__()
        _, l = _tab()
        QVBoxLayout(self).addWidget(_)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Field", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        l.addWidget(self.table, 1)

        def done(rows):
            self.table.setRowCount(len(rows))
            for i, (k, v) in enumerate(rows):
                self.table.setItem(i, 0, QTableWidgetItem(k))
                self.table.setItem(i, 1, QTableWidgetItem(v))

        C.run_bg(lambda: s.vag.identification(m), done)
