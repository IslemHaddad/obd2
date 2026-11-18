"""Custom-painted widgets: gauge tiles, sparkline, top-view car with glowing module hotspots."""
from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPainterPath, QPen, \
    QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import common as C


class GaugeTile(QWidget):
    """style: ring | arc | bar | number | graph."""
    clicked = Signal()

    def __init__(self, pid, style: str = "ring", warn: float | None = None, accent: str = C.ACCENT):
        super().__init__()
        self.pid, self.style, self.warn, self.accent = pid, style, warn, accent
        self.value: float | None = None
        self.history: deque[float] = deque(maxlen=120)
        self.setMinimumSize(200, 170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_value(self, v: float | None):
        self.value = v
        if v is not None:
            self.history.append(v)
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def _frac(self):
        if self.value is None:
            return 0.0
        lo, hi = self.pid.min, self.pid.max
        return max(0.0, min(1.0, (self.value - lo) / ((hi - lo) or 1)))

    def _text(self):
        v = self.value
        if v is None:
            return "—"
        return f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}"

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        warn = self.warn is not None and self.value is not None and self.value >= self.warn
        tint = QColor(C.RED if warn else self.accent)
        # card
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#202127"))
        g.setColorAt(1, QColor("#17181C"))
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, 18, 18)
        # title
        p.setPen(QColor(C.MUTED))
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        f.setBold(True)
        p.setFont(f)
        p.drawText(r.adjusted(16, 12, -16, 0), Qt.AlignLeft | Qt.AlignTop, self.pid.name + ("  ⚠" if warn else ""))
        body = r.adjusted(16, 34, -16, -14)
        getattr(self, "_paint_" + self.style, self._paint_ring)(p, body, tint)

    def _readout(self, p, rect, size, align=Qt.AlignCenter, gap=1.05):
        f = QFont(self.font())
        f.setPointSizeF(size)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor(C.TEXT))
        p.drawText(rect, align, self._text())
        f.setPointSizeF(max(8, size * 0.32))
        f.setWeight(QFont.Medium)
        p.setFont(f)
        p.setPen(QColor(C.MUTED))
        unit_rect = QRectF(rect)
        unit_rect.translate(0, size * gap)
        p.drawText(unit_rect, align, self.pid.unit)

    def _arc(self, p, body, tint, start, span):
        d = min(body.width(), body.height())
        sq = QRectF(body.center().x() - d / 2, body.center().y() - d / 2, d, d).adjusted(8, 8, -8, -8)
        w = max(8, d * 0.075)
        p.setPen(QPen(QColor(tint.red(), tint.green(), tint.blue(), 40), w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(sq, int(start * 16), int(-span * 16))
        if self._frac() > 0:
            grad = QConicalGradient(sq.center(), start)
            grad.setColorAt(0, tint.lighter(140))
            grad.setColorAt(span / 360.0, tint)
            glow = QColor(tint)
            glow.setAlpha(60)
            p.setPen(QPen(glow, w * 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(sq, int(start * 16), int(-span * self._frac() * 16))
            p.setPen(QPen(QBrush(tint), w, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(sq, int(start * 16), int(-span * self._frac() * 16))
        return sq, d

    def _paint_ring(self, p, body, tint):
        sq, d = self._arc(p, body, tint, 90, 360)
        rr = QRectF(sq)
        rr.translate(0, -d * 0.08)
        self._readout(p, rr, max(14, d * 0.14))

    def _paint_arc(self, p, body, tint):
        sq, d = self._arc(p, body, tint, 225, 270)
        c = sq.center()
        rad = sq.width() / 2
        p.setPen(QPen(QColor(C.MUTED), 2))
        for i in range(11):
            a = math.radians(225 - 27 * i)
            inner = rad - (d * 0.12 if i % 5 == 0 else d * 0.08)
            p.drawLine(QPointF(c.x() + math.cos(a) * inner, c.y() - math.sin(a) * inner),
                       QPointF(c.x() + math.cos(a) * (rad - d * 0.05), c.y() - math.sin(a) * (rad - d * 0.05)))
        a = math.radians(225 - 270 * self._frac())
        p.setPen(QPen(tint, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(c, QPointF(c.x() + math.cos(a) * rad * 0.72, c.y() - math.sin(a) * rad * 0.72))
        p.setBrush(tint)
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, 6, 6)
        rr = QRectF(sq)
        rr.translate(0, d * 0.22)
        self._readout(p, rr, max(14, d * 0.12))

    def _paint_bar(self, p, body, tint):
        rr = QRectF(body.left(), body.top(), body.width(), body.height() - 30)
        self._readout(p, rr, max(16, body.height() * 0.22), Qt.AlignLeft | Qt.AlignVCenter)
        bar = QRectF(body.left(), body.bottom() - 12, body.width(), 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(tint.red(), tint.green(), tint.blue(), 40))
        p.drawRoundedRect(bar, 5, 5)
        fill = QRectF(bar)
        fill.setWidth(max(10, bar.width() * self._frac()))
        g = QLinearGradient(fill.topLeft(), fill.topRight())
        g.setColorAt(0, tint.darker(130))
        g.setColorAt(1, tint)
        p.setBrush(g)
        p.drawRoundedRect(fill, 5, 5)

    def _paint_number(self, p, body, tint):
        self._readout(p, body.adjusted(0, -10, 0, -10), max(18, body.height() * 0.32), Qt.AlignLeft | Qt.AlignVCenter)

    def _paint_graph(self, p, body, tint):
        top = QRectF(body.left(), body.top(), body.width(), 40)
        self._readout(p, top, 18, Qt.AlignLeft | Qt.AlignTop, gap=1.7)
        area = QRectF(body.left(), body.top() + 56, body.width(), body.height() - 56)
        paint_sparkline(p, area, list(self.history), self.pid.min, self.pid.max, tint)


def paint_sparkline(p, area: QRectF, vals, lo, hi, tint: QColor):
    if len(vals) < 2:
        return
    rng = (hi - lo) or 1
    dx = area.width() / (len(vals) - 1)
    path = QPainterPath()
    for i, v in enumerate(vals):
        y = area.bottom() - area.height() * max(0.0, min(1.0, (v - lo) / rng))
        pt = QPointF(area.left() + i * dx, y)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    fill = QPainterPath(path)
    fill.lineTo(area.right(), area.bottom())
    fill.lineTo(area.left(), area.bottom())
    fill.closeSubpath()
    g = QLinearGradient(area.topLeft(), area.bottomLeft())
    c1 = QColor(tint)
    c1.setAlpha(90)
    c2 = QColor(tint)
    c2.setAlpha(0)
    g.setColorAt(0, c1)
    g.setColorAt(1, c2)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(fill)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(tint, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)


class Sparkline(QWidget):
    def __init__(self, color=C.ACCENT):
        super().__init__()
        self.vals: deque[float] = deque(maxlen=120)
        self.color = QColor(color)
        self.setFixedSize(110, 28)

    def push(self, v):
        self.vals.append(v)
        self.update()

    def paintEvent(self, _):
        if len(self.vals) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lo, hi = min(self.vals), max(self.vals)
        paint_sparkline(p, QRectF(self.rect()).adjusted(1, 2, -1, -2), list(self.vals), lo, max(hi, lo + 1), self.color)


class CarDiagram(QWidget):
    """Top view, front at top. Hotspots: grey = not scanned, green = OK, glowing = faulty."""
    module_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.color = QColor("#DB1F29")
        self.aspect = 2.2
        self.body = "hatch"
        self.reports: dict = {}          # address -> Report
        self.modules: list = []
        self.phase = 0.0
        self._spots: dict[str, QPointF] = {}
        self.setMinimumSize(260, 480)
        self.setMouseTracking(True)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)

    def _tick(self):
        if any(r.faulty for r in self.reports.values()):
            self.phase = (self.phase + 0.033 / 1.2) % 1.0
            self.update()

    def set_vehicle(self, color: str, body: str, aspect: float):
        self.color, self.body, self.aspect = QColor(color), body, aspect
        self.update()

    def set_reports(self, modules, reports: dict):
        self.modules, self.reports = modules, reports
        self.update()

    def mousePressEvent(self, e):
        for addr, pt in self._spots.items():
            if (pt - e.position()).manhattanLength() < 26:
                self.module_clicked.emit(addr)
                return

    def mouseMoveEvent(self, e):
        hit = next((a for a, pt in self._spots.items() if (pt - e.position()).manhattanLength() < 26), None)
        self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor)
        if hit:
            m = next(m for m in self.modules if m.address == hit)
            r = self.reports.get(hit)
            extra = f" — {len(r.faults)} fault(s)" if r and r.faulty else (" — OK" if r else "")
            self.setToolTip(f"{m.address} · {m.name}{extra}")

    def paintEvent(self, _):
        from ..carart import spec as SP
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        H = self.height() - 20
        h = min(H, (self.width() - 40) * self.aspect)
        w = h / self.aspect
        x0, y0 = (self.width() - w) / 2, (self.height() - h) / 2
        sx, sy = w / SP.TOP_W, h / SP.TOP_H

        def path(cmds):
            q = QPainterPath()
            for c in cmds:
                if c[0] == "M":
                    q.moveTo(x0 + c[1] * sx, y0 + c[2] * sy)
                elif c[0] == "L":
                    q.lineTo(x0 + c[1] * sx, y0 + c[2] * sy)
                elif c[0] == "C":
                    q.cubicTo(x0 + c[1] * sx, y0 + c[2] * sy, x0 + c[3] * sx, y0 + c[4] * sy, x0 + c[5] * sx, y0 + c[6] * sy)
                else:
                    q.closeSubpath()
            return q

        T = SP.TOP
        # glow
        glow = QRadialGradient(QPointF(x0 + w / 2, y0 + h / 2), h * 0.6)
        gc = QColor(self.color)
        gc.setAlpha(55)
        glow.setColorAt(0, gc)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawRect(QRectF(x0 - w * 0.6, y0 - 20, w * 2.2, h + 40))
        p.setBrush(QColor(10, 10, 12))
        for x, y, ww, hh in T["wheels"]:
            p.drawRoundedRect(QRectF(x0 + x * sx, y0 + y * sy, ww * sx, hh * sy), 6, 6)
        g = QLinearGradient(QPointF(x0, 0), QPointF(x0 + w, 0))
        g.setColorAt(0, self.color.darker(150))
        g.setColorAt(0.5, self.color.lighter(120))
        g.setColorAt(1, self.color.darker(150))
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.drawPath(path(T["body"]))
        p.setPen(Qt.NoPen)
        p.setBrush(self.color.darker(115))
        p.drawPath(path(T["mirror_l"]))
        p.drawPath(path(T["mirror_r"]))
        p.setBrush(QColor(14, 16, 20))
        p.drawPath(path(T["windscreen"]))
        p.drawPath(path(T["rear_glass"]))
        p.setBrush(QColor(20, 22, 26))
        p.drawPath(path(T["roof"]))
        pg = QLinearGradient(0, y0 + 400 * sy, 0, y0 + 560 * sy)
        pg.setColorAt(0, QColor(70, 80, 95))
        pg.setColorAt(1, QColor(20, 24, 30))
        p.setBrush(pg)
        p.drawPath(path(T["panorama"]))
        p.setBrush(QColor(240, 250, 255))
        p.drawPath(path(T["headlight_l"]))
        p.drawPath(path(T["headlight_r"]))
        p.setBrush(QColor(C.RED))
        p.drawPath(path(T["taillight"]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1.5))
        p.drawPath(path(T["bonnet_l"]))
        p.drawPath(path(T["bonnet_r"]))
        # hotspots
        self._spots.clear()
        for m in self.modules:
            r = self.reports.get(m.address)
            if r is not None and not r.present:
                continue
            c = QPointF(x0 + m.x * w, y0 + m.y * h)
            self._spots[m.address] = c
            if r is not None and r.faulty:
                col = QColor(m.color)
                # pulse ring
                rad = 14 + 14 * self.phase
                ring = QColor(col)
                ring.setAlphaF(max(0.0, 0.9 * (1 - self.phase)))
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(ring, 2))
                p.drawEllipse(c, rad, rad)
                # glow
                rg = QRadialGradient(c, 30)
                gcol = QColor(col)
                gcol.setAlpha(150)
                rg.setColorAt(0, gcol)
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(rg)
                p.drawEllipse(c, 30, 30)
                p.setBrush(col)
                p.drawEllipse(c, 13, 13)
                p.setPen(QColor("black"))
                f = QFont(self.font())
                f.setBold(True)
                f.setPointSize(12)
                p.setFont(f)
                p.drawText(QRectF(c.x() - 13, c.y() - 13, 26, 26), Qt.AlignCenter, "!")
            elif r is not None:
                p.setPen(Qt.NoPen)
                rg = QRadialGradient(c, 10)
                rg.setColorAt(0, QColor(C.GREEN))
                rg.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(rg)
                p.drawEllipse(c, 10, 10)
                p.setBrush(QColor(C.GREEN))
                p.drawEllipse(c, 4.5, 4.5)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 90))
                p.drawEllipse(c, 3.5, 3.5)
