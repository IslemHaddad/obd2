"""Power Run: estimate power/torque from a full-throttle pull in one gear.

Physics only:  P = m · v · dv/dt   (power that accelerates the car's mass)
               T = P / ω_engine,   ω_engine = 2π · rpm / 60
The only external input is the vehicle mass the user types in. Aerodynamic drag, rolling resistance
and drivetrain losses are NOT added, so the result is the power left over for acceleration
(lower than the factory crank rating).
"""
from __future__ import annotations

import csv
import math
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QVBoxLayout, QWidget

from . import common as C

RPM, SPEED, THROTTLE = 0x0C, 0x0D, 0x11
PS_PER_KW = 1 / 0.73549875        # unit conversion (1 PS = 0.73549875 kW)


G = 9.81            # gravity, m/s²
RHO = 1.225         # air density at ~15 °C, kg/m³


def analyse(samples: list[tuple[float, float, float, float]], mass: float, min_throttle: float = 80.0,
            window: float = 0.8, cda: float = 0.65, crr: float = 0.012, drivetrain: float = 0.13):
    """samples: (t, rpm, speed_kmh, throttle%). Returns list of (rpm, kW, Nm) points + peaks.

    Estimates CRANK power by adding back the power the engine spends on aerodynamic drag
    (½·ρ·CdA·v³), rolling resistance (Crr·m·g·v) and drivetrain loss, on top of the power that
    accelerates the car's mass (m·v·a). cda≈0.65 and crr≈0.012 suit a small hatch; drivetrain≈0.13
    is a typical FWD manual loss. Still approximate, but lands near the factory rating."""
    pts = [s for s in samples if s[3] >= min_throttle and s[2] > 15 and s[1] >= 1200]
    if len(pts) < 8:
        return [], None, None
    out = []
    for i, (t, rpm, _v, _th) in enumerate(pts):
        win = [p for p in pts if abs(p[0] - t) <= window / 2]
        if len(win) < 4:
            continue
        # least-squares slope of speed vs time in the window (speed PID is whole km/h → smooth it)
        mt = sum(p[0] for p in win) / len(win)
        mv = sum(p[2] for p in win) / len(win)
        den = sum((p[0] - mt) ** 2 for p in win)
        if den <= 0:
            continue
        slope_kmh_s = sum((p[0] - mt) * (p[2] - mv) for p in win) / den
        v = mv / 3.6
        a = slope_kmh_s / 3.6
        if a <= 0 or rpm < 500:
            continue
        p_accel = mass * v * a                          # power into accelerating the mass
        p_drag = 0.5 * RHO * cda * v ** 3               # aerodynamic drag
        p_roll = crr * mass * G * v                     # rolling resistance
        p_w = (p_accel + p_drag + p_roll) / (1 - drivetrain)   # → crank power
        torque = p_w / (2 * math.pi * rpm / 60)
        out.append((rpm, p_w / 1000, torque))
    out.sort()
    if not out:
        return [], None, None
    # bin by 250 rpm and average → clean curve
    bins: dict[int, list] = {}
    for rpm, kw, nm in out:
        bins.setdefault(int(rpm // 250) * 250, []).append((kw, nm))
    curve = [(b + 125, sum(k for k, _ in v) / len(v), sum(n for _, n in v) / len(v)) for b, v in sorted(bins.items())]
    pk = max(curve, key=lambda c: c[1])
    tq = max(curve, key=lambda c: c[2])
    return curve, pk, tq


class Chart(QWidget):
    def __init__(self):
        super().__init__()
        self.curve = []
        self.setMinimumHeight(320)

    def set_curve(self, c):
        self.curve = c
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(56, 20, -60, -36)
        p.fillRect(self.rect(), QColor(C.CARD))
        p.setPen(QColor(C.MUTED))
        if not self.curve:
            p.drawText(self.rect(), Qt.AlignCenter, "No run yet — do a full-throttle pull in 2nd or 3rd gear")
            return
        rpms = [c[0] for c in self.curve]
        x0, x1 = min(rpms), max(rpms)
        kmax = max(c[1] for c in self.curve) * 1.15
        nmax = max(c[2] for c in self.curve) * 1.15
        sx = lambda rpm: r.left() + (rpm - x0) / max(1, x1 - x0) * r.width()
        p.setPen(QPen(QColor("#2A2B30"), 1))
        for i in range(6):
            y = r.top() + r.height() * i / 5
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        f = QFont(self.font())
        f.setPointSize(9)
        p.setFont(f)
        p.setPen(QColor(C.MUTED))
        for i in range(6):
            rpm = x0 + (x1 - x0) * i / 5
            p.drawText(QPointF(sx(rpm) - 16, r.bottom() + 18), f"{rpm:.0f}")
            y = r.bottom() - r.height() * i / 5
            p.drawText(QPointF(r.left() - 50, y + 4), f"{kmax * PS_PER_KW * i / 5:.0f} PS")
            p.drawText(QPointF(r.right() + 6, y + 4), f"{nmax * i / 5:.0f} Nm")
        for idx, col, mx in ((1, C.RED, kmax), (2, C.ACCENT, nmax)):
            path = QPainterPath()
            for j, c in enumerate(self.curve):
                pt = QPointF(sx(c[0]), r.bottom() - c[idx] / mx * r.height())
                path.moveTo(pt) if j == 0 else path.lineTo(pt)
            p.setPen(QPen(QColor(col), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
        p.setPen(QColor(C.RED))
        p.drawText(QPointF(r.left() + 8, r.top() + 14), "● Power")
        p.setPen(QColor(C.ACCENT))
        p.drawText(QPointF(r.left() + 80, r.top() + 14), "● Torque")


class PowerPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        self.samples: list[tuple[float, float, float, float]] = []
        self.recording = False
        w, lay = C.page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        st = s.store.get("settings", {}) or {}
        self.mass = QSpinBox()
        self.mass.setRange(0, 5000)
        self.mass.setSuffix(" kg")
        self.mass.setValue(int(st.get("mass", 0)))
        self.mass.setSpecialValueText("enter weight")
        self.mass.valueChanged.connect(self._save_mass)
        self.btn = C.button("● Start Recording", "primary", self.toggle)
        self.live = C.label("", "muted")
        lay.addLayout(C.row(C.label("Power Run", "h1"), "stretch", C.label("Car weight incl. driver"), self.mass, self.btn))
        lay.addWidget(C.label(
            "Safely, on a closed or empty straight road: pick 2nd or 3rd gear, start recording, go FULL throttle "
            "from ~1500 rpm to near the limiter, then stop recording. Estimated crank power — adds back aero drag, "
            "rolling resistance and drivetrain loss. 2nd gear is most accurate; still an estimate, not a bench dyno.",
            "muted", True))
        self.peaks = C.label("", "h2")
        lay.addWidget(C.card(C.row(self.peaks, "stretch", self.live)))
        self.chart = Chart()
        lay.addWidget(self.chart, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["rpm", "kW", "PS", "Nm"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMaximumHeight(200)
        lay.addWidget(self.table)
        s.values.connect(self.on_values)

    def _save_mass(self, v):
        st = self.s.store.get("settings", {}) or {}
        st["mass"] = v
        self.s.store.set("settings", st)

    def toggle(self):
        if self.recording:
            self.recording = False
            self.s.override_ids = None
            self.btn.setText("● Start Recording")
            self.btn.setObjectName("primary")
            self.btn.style().unpolish(self.btn)
            self.btn.style().polish(self.btn)
            self.compute()
            return
        if not self.s.connected:
            return C.error_box("Connect first.")
        if self.mass.value() <= 0:
            return C.error_box("Enter the car's weight including driver (kg) first.")
        self.samples = []
        self.s.override_ids = [RPM, SPEED, THROTTLE]     # 3 PIDs in one request → highest sample rate
        self.recording = True
        self.btn.setText("■ Stop & Calculate")
        self.btn.setObjectName("danger")
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def on_values(self, vals):
        if not self.recording or RPM not in vals or SPEED not in vals:
            return
        th = vals.get(THROTTLE, 100.0)
        self.samples.append((vals["_t"], vals[RPM], vals[SPEED], th))
        self.live.setText(f"{len(self.samples)} samples · {vals[RPM]:.0f} rpm · {vals[SPEED]:.0f} km/h · "
                          f"throttle {th:.0f}%")

    def compute(self):
        from .. import catalog
        veh = self.s.store.get("vehicle", {}) or {}
        cda = catalog.cda_for(veh.get("brand", "seat"), veh.get("model", ""))
        curve, pk, tq = analyse(self.samples, float(self.mass.value()), cda=cda)
        self.chart.set_curve(curve)
        self.table.setRowCount(len(curve))
        for i, (rpm, kw, nm) in enumerate(curve):
            for j, v in enumerate((f"{rpm:.0f}", f"{kw:.1f}", f"{kw * PS_PER_KW:.1f}", f"{nm:.0f}")):
                self.table.setItem(i, j, QTableWidgetItem(v))
        if not curve:
            self.peaks.setText("Not enough full-throttle data — hold ≥80% throttle in one gear for a few seconds.")
            return
        self.peaks.setText(f"Peak {pk[1]:.1f} kW ({pk[1] * PS_PER_KW:.0f} PS) @ {pk[0]:.0f} rpm   ·   "
                           f"Peak {tq[2]:.0f} Nm @ {tq[0]:.0f} rpm")
        path = self.s.store.logs_dir() / f"powerrun_{datetime.now():%Y%m%d_%H%M%S}.csv"
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "rpm", "speed_kmh", "throttle_pct"])
            w.writerows(self.samples)
        self.live.setText(f"Raw samples saved: {path.name}")

    def showEvent(self, e):
        self.s.poll_enabled = True
        super().showEvent(e)
