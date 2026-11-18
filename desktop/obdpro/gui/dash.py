"""Car-style dashboard: big speedometer + tachometer with a centre info strip. F11 / button = full screen."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from .. import features as F
from . import common as C

RPM, SPEED, COOLANT, IAT, THROTTLE, LOAD = 0x0C, 0x0D, 0x05, 0x0F, 0x11, 0x04
OIL = F.vpid_from(F.VAG_PRESETS[0]).id


class Dial(QWidget):
    """Cluster-style dial with smooth needle, numbered scale, red zone and digital readout."""

    def __init__(self, title: str, unit: str, maxv: float, major: float, red_from: float | None = None,
                 label_div: float = 1, accent: str = "#FF3B30"):
        super().__init__()
        self.title, self.unit, self.maxv, self.major = title, unit, maxv, major
        self.red_from, self.label_div, self.accent = red_from, label_div, QColor(accent)
        self.target = 0.0
        self.shown = 0.0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(300, 300)
        t = QTimer(self)
        t.timeout.connect(self._anim)
        t.start(16)

    def set_value(self, v):
        self.target = max(0.0, min(self.maxv, float(v)))

    def _anim(self):
        d = self.target - self.shown
        if abs(d) > self.maxv * 0.0005:
            self.shown += d * 0.18
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 10
        c = QPointF(self.width() / 2, self.height() / 2)
        R = side / 2
        start, sweep = 225.0, 270.0           # degrees, clockwise from start
        ang = lambda v: math.radians(start - sweep * v / self.maxv)

        # bezel + face
        face = QRadialGradient(c, R)
        face.setColorAt(0, QColor("#1b1d22"))
        face.setColorAt(0.85, QColor("#0d0e11"))
        face.setColorAt(1, QColor("#050506"))
        p.setPen(QPen(QColor(255, 255, 255, 28), 2))
        p.setBrush(face)
        p.drawEllipse(c, R, R)

        # glow arc up to value
        arc = QRectF(c.x() - R * 0.86, c.y() - R * 0.86, R * 1.72, R * 1.72)
        frac = self.shown / self.maxv
        if frac > 0:
            g = QConicalGradient(c, start)
            g.setColorAt(0, self.accent.darker(200))
            g.setColorAt(sweep / 360 * frac, self.accent)
            glow = QColor(self.accent)
            glow.setAlpha(55)
            p.setPen(QPen(glow, R * 0.12, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(arc, int(start * 16), int(-sweep * frac * 16))
            p.setPen(QPen(self.accent, R * 0.025, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(arc, int(start * 16), int(-sweep * frac * 16))

        # red zone
        if self.red_from:
            rz = QRectF(c.x() - R * 0.9, c.y() - R * 0.9, R * 1.8, R * 1.8)
            p.setPen(QPen(QColor("#FF3B30"), R * 0.045, Qt.SolidLine, Qt.FlatCap))
            a0 = start - sweep * self.red_from / self.maxv
            p.drawArc(rz, int(a0 * 16), int(-(sweep * (1 - self.red_from / self.maxv)) * 16))

        # ticks + numbers
        f = QFont(self.font())
        f.setPointSizeF(max(8, R * 0.075))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        minor = self.major / 5
        n = int(self.maxv / minor + 0.5)
        for i in range(n + 1):
            v = i * minor
            a = ang(v)
            is_major = i % 5 == 0
            r1 = R * (0.80 if is_major else 0.85)
            r2 = R * 0.92
            col = QColor("#FF3B30") if self.red_from and v >= self.red_from else QColor("#E5E5EA")
            p.setPen(QPen(col, R * (0.018 if is_major else 0.008)))
            p.drawLine(QPointF(c.x() + math.cos(a) * r1, c.y() - math.sin(a) * r1),
                       QPointF(c.x() + math.cos(a) * r2, c.y() - math.sin(a) * r2))
            if is_major:
                rt = R * 0.66
                txt = f"{v / self.label_div:g}"
                p.setPen(col)
                p.drawText(QRectF(c.x() + math.cos(a) * rt - 30, c.y() - math.sin(a) * rt - 14, 60, 28),
                           Qt.AlignCenter, txt)

        # needle
        a = ang(self.shown)
        tip = QPointF(c.x() + math.cos(a) * R * 0.86, c.y() - math.sin(a) * R * 0.86)
        tail = QPointF(c.x() - math.cos(a) * R * 0.12, c.y() + math.sin(a) * R * 0.12)
        p.setPen(QPen(QColor(255, 59, 48, 90), R * 0.05, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(tail, tip)
        p.setPen(QPen(QColor("#FF453A"), R * 0.02, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(tail, tip)
        hub = QRadialGradient(c, R * 0.09)
        hub.setColorAt(0, QColor("#3a3b40"))
        hub.setColorAt(1, QColor("#111"))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(hub)
        p.drawEllipse(c, R * 0.08, R * 0.08)

        # digital readout + title
        f.setPointSizeF(R * 0.17)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(c.x() - R, c.y() + R * 0.22, 2 * R, R * 0.3), Qt.AlignCenter, f"{self.target:.0f}")
        f.setPointSizeF(R * 0.06)
        f.setWeight(QFont.Medium)
        p.setFont(f)
        p.setPen(QColor(C.MUTED))
        p.drawText(QRectF(c.x() - R, c.y() + R * 0.52, 2 * R, R * 0.12), Qt.AlignCenter, self.unit)
        p.drawText(QRectF(c.x() - R, c.y() - R * 0.42, 2 * R, R * 0.12), Qt.AlignCenter, self.title.upper())


class InfoCell(QWidget):
    def __init__(self, title, unit, lo, hi, warn=None):
        super().__init__()
        self.title, self.unit, self.lo, self.hi, self.warn = title, unit, lo, hi, warn
        self.value = None
        self.setMinimumSize(150, 74)

    def set_value(self, v):
        self.value = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        hot = self.warn is not None and self.value is not None and self.value >= self.warn
        p.setPen(QPen(QColor(C.RED if hot else "#2a2b30"), 1.5))
        p.setBrush(QColor("#121316"))
        p.drawRoundedRect(r, 12, 12)
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C.MUTED))
        p.drawText(r.adjusted(12, 8, -8, 0), Qt.AlignLeft | Qt.AlignTop, self.title.upper())
        f.setPointSizeF(19)
        p.setFont(f)
        p.setPen(QColor(C.RED if hot else "#FFFFFF"))
        txt = "—" if self.value is None else (f"{self.value:.1f}" if abs(self.value) < 100 and self.unit == "V"
                                              else f"{self.value:.0f}")
        p.drawText(r.adjusted(12, 22, -8, -14), Qt.AlignLeft | Qt.AlignVCenter, f"{txt} {self.unit}")
        if self.value is not None:
            frac = max(0.0, min(1.0, (self.value - self.lo) / ((self.hi - self.lo) or 1)))
            bar = QRectF(r.left() + 12, r.bottom() - 10, (r.width() - 24), 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#2a2b30"))
            p.drawRoundedRect(bar, 2, 2)
            bar.setWidth(bar.width() * frac)
            p.setBrush(QColor(C.RED if hot else C.ACCENT))
            p.drawRoundedRect(bar, 2, 2)


class DashPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        self.setStyleSheet("background: #07080a;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 14)
        self.full_btn = C.button("⛶ Full screen (F11)", slot=self.toggle_full)
        self.status = C.label("", "muted")
        outer.addLayout(C.row(C.label("Dashboard", "h1"), self.status, "stretch", self.full_btn))
        body = QHBoxLayout()
        body.setSpacing(18)
        self.speed = Dial("Speed", "km/h", 220, 20, accent="#0A84FF")
        self.rpm = Dial("RPM ×1000", "rpm", 7000, 1000, red_from=6000, label_div=1000, accent="#FF3B30")
        mid = QVBoxLayout()
        mid.setSpacing(10)
        self.cells = {
            OIL: InfoCell("Oil", "°C", 40, 150, warn=float(F.setting(s.store, "alert_oil"))),
            COOLANT: InfoCell("Coolant", "°C", 40, 130, warn=float(F.setting(s.store, "alert_coolant"))),
            IAT: InfoCell("Intake air", "°C", 0, 90),
            "volts": InfoCell("Battery", "V", 11, 15.5),
            THROTTLE: InfoCell("Throttle", "%", 0, 100),
            LOAD: InfoCell("Engine load", "%", 0, 100),
        }
        mid.addStretch(1)
        for c in self.cells.values():
            mid.addWidget(c)
        mid.addStretch(1)
        body.addWidget(self.speed, 5)
        body.addLayout(mid, 2)
        body.addWidget(self.rpm, 5)
        outer.addLayout(body, 1)
        s.values.connect(self.on_values)
        s.battery.connect(lambda v: self.cells["volts"].set_value(v))
        s.rate.connect(lambda r: self.status.setText(f"   {r:.1f} updates/s"))
        self._full = False

    def on_values(self, v):
        if not self.isVisible():
            return
        if SPEED in v:
            self.speed.set_value(v[SPEED])
        if RPM in v:
            self.rpm.set_value(v[RPM])
        for k, cell in self.cells.items():
            if k in v:
                cell.set_value(v[k])

    def showEvent(self, e):
        # ask the poller for oil temp + load while this page is visible
        self.s.extra_vag = [F.VAG_PRESETS[0]]
        self.s.extra_pids = [LOAD]
        super().showEvent(e)

    def hideEvent(self, e):
        self.s.extra_vag = []
        self.s.extra_pids = []
        super().hideEvent(e)

    def toggle_full(self):
        w = self.window()
        if self._full:
            w.showNormal()
            w.sidebar.show()
        else:
            w.sidebar.hide()
            w.showFullScreen()
        self._full = not self._full
        self.full_btn.setText("⛶ Exit full screen (F11)" if self._full else "⛶ Full screen (F11)")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_F11, Qt.Key_Escape) and (self._full or e.key() == Qt.Key_F11):
            self.toggle_full()
        else:
            super().keyPressEvent(e)
