"""Render the car art spec to PNGs for review (PySide6, offscreen)."""
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(__file__))
import spec  # noqa: E402


MAP = (lambda x: x, lambda y: y)


def path(cmds):
    mx, my = MAP
    p = QPainterPath()
    for c in cmds:
        if c[0] == "M":
            p.moveTo(mx(c[1]), my(c[2]))
        elif c[0] == "L":
            p.lineTo(mx(c[1]), my(c[2]))
        elif c[0] == "C":
            p.cubicTo(mx(c[1]), my(c[2]), mx(c[3]), my(c[4]), mx(c[5]), my(c[6]))
        else:
            p.closeSubpath()
    return p


def wheel(p, cx, cy, r):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(12, 12, 14))
    p.drawEllipse(QPointF(cx, cy), r, r)
    g = QRadialGradient(QPointF(cx, cy), r * 0.68)
    g.setColorAt(0, QColor(200, 202, 208))
    g.setColorAt(1, QColor(110, 112, 120))
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), r * 0.66, r * 0.66)
    import math
    p.setPen(QPen(QColor(40, 42, 48), r * 0.09, Qt.SolidLine, Qt.RoundCap))
    for i in range(10):
        a = i * math.pi / 5
        p.drawLine(QPointF(cx + math.cos(a) * r * 0.14, cy + math.sin(a) * r * 0.14),
                   QPointF(cx + math.cos(a + 0.18) * r * 0.62, cy + math.sin(a + 0.18) * r * 0.62))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(60, 62, 68))
    p.drawEllipse(QPointF(cx, cy), r * 0.13, r * 0.13)


def side(color, out, g=None):
    global MAP
    W, H = spec.SIDE_W, int(g.side_h) if g else spec.SIDE_H
    MAP = (g.side_x, g.side_y) if g else (lambda x: x, lambda y: y)
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(QColor(15, 16, 18))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    S = spec.SIDE
    gy = MAP[1](286)
    sh = QRadialGradient(QPointF(W / 2, gy), W * 0.48)
    sh.setColorAt(0, QColor(0, 0, 0, 170)); sh.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.NoPen); p.setBrush(sh); p.drawEllipse(QPointF(W / 2, gy), W * 0.47, 18)
    c = QColor(color)
    g = QLinearGradient(0, 40, 0, 280)
    g.setColorAt(0, c.lighter(135)); g.setColorAt(0.45, c); g.setColorAt(1, c.darker(170))
    p.setBrush(g); p.setPen(QPen(QColor(255, 255, 255, 40), 1.2)); p.drawPath(path(S["body"]))
    p.setPen(Qt.NoPen)
    gl = QLinearGradient(0, 50, 0, 150); gl.setColorAt(0, QColor(70, 80, 95)); gl.setColorAt(1, QColor(12, 14, 18))
    p.setBrush(gl); p.drawPath(path(S["glass"]))
    p.setBrush(QColor(10, 10, 12)); p.drawPath(path(S["c_pillar"])); p.drawPath(path(S["b_pillar"]))
    p.setBrush(c.darker(120)); p.drawPath(path(S["mirror"]))
    p.setBrush(QColor(255, 255, 255, 235)); p.drawPath(path(S["headlight"]))
    p.setBrush(QColor(230, 30, 40)); p.drawPath(path(S["taillight"]))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 110), 2)); p.drawPath(path(S["shoulder"]))
    p.setPen(QPen(QColor(0, 0, 0, 90), 3)); p.drawPath(path(S["sill"]))
    p.setPen(QPen(QColor(180, 240, 255), 3, Qt.SolidLine, Qt.RoundCap)); p.drawPath(path(S["drl"]))
    p.setPen(QPen(QColor(0, 0, 0, 120), 3, Qt.SolidLine, Qt.RoundCap)); p.drawPath(path(S["handle"]))
    for cx, cy, r in S["wheels"]:
        wheel(p, MAP[0](cx), MAP[1](cy), r)
    p.end(); img.save(out)


def front(color, grille, out, badge="SEAT", g=None):
    global MAP
    W, H = spec.FRONT_W, int(g.front_h) if g else spec.FRONT_H
    MAP = (lambda x: x, g.front_y) if g else (lambda x: x, lambda y: y)
    img = QImage(W, H, QImage.Format_ARGB32); img.fill(QColor(15, 16, 18))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    F = spec.FRONT
    p.setPen(Qt.NoPen)
    sh = QRadialGradient(QPointF(W / 2, 340), 300); sh.setColorAt(0, QColor(0, 0, 0, 170)); sh.setColorAt(1, QColor(0, 0, 0, 0))
    p.setBrush(sh); p.drawEllipse(QPointF(W / 2, 342), 280, 16)
    p.setBrush(QColor(12, 12, 14))
    for x, y, w, h in F["tyres"]:
        p.drawRoundedRect(QRectF(x, MAP[1](y) - h, w, h), 10, 10)
    c = QColor(color)
    g = QLinearGradient(60, 0, 540, 0); g.setColorAt(0, c.darker(140)); g.setColorAt(0.5, c.lighter(115)); g.setColorAt(1, c.darker(140))
    p.setBrush(g); p.setPen(QPen(QColor(255, 255, 255, 40), 1.2)); p.drawPath(path(F["body"]))
    p.setPen(Qt.NoPen)
    gl = QLinearGradient(0, 60, 0, 160); gl.setColorAt(0, QColor(80, 90, 105)); gl.setColorAt(1, QColor(12, 14, 18))
    p.setBrush(gl); p.drawPath(path(F["glass"]))
    p.setBrush(c.darker(120)); p.drawPath(path(F["mirror_l"])); p.drawPath(path(F["mirror_r"]))
    p.setBrush(QColor(30, 32, 38)); p.drawPath(path(F["headlight_l"])); p.drawPath(path(F["headlight_r"]))
    p.setPen(QPen(QColor(200, 245, 255), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); p.setBrush(Qt.NoBrush)
    p.drawPath(path(F["drl_l"])); p.drawPath(path(F["drl_r"]))
    p.setPen(QPen(QColor(200, 200, 210), 3)); p.setBrush(QColor(14, 14, 16))
    p.drawPath(path(F["grille_" + grille]))
    p.setPen(Qt.NoPen); p.setBrush(QColor(14, 14, 16))
    p.drawPath(path(F["intake_l"])); p.drawPath(path(F["intake_r"])); p.drawPath(path(F["lower"]))
    f = QFont(); f.setBold(True); f.setPointSize(13); p.setFont(f); p.setPen(QColor(235, 235, 240))
    p.drawText(QRectF(200, MAP[1](236), 200, 30), Qt.AlignCenter, badge)
    p.end(); img.save(out)


def top(color, out):
    W, H = spec.TOP_W + 60, spec.TOP_H + 20
    img = QImage(W, H, QImage.Format_ARGB32); img.fill(QColor(15, 16, 18))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing); p.translate(30, 10)
    T = spec.TOP
    p.setPen(Qt.NoPen); p.setBrush(QColor(10, 10, 12))
    for x, y, w, h in T["wheels"]:
        p.drawRoundedRect(QRectF(x, y, w, h), 10, 10)
    c = QColor(color)
    g = QLinearGradient(0, 0, 400, 0); g.setColorAt(0, c.darker(150)); g.setColorAt(0.5, c.lighter(120)); g.setColorAt(1, c.darker(150))
    p.setBrush(g); p.setPen(QPen(QColor(255, 255, 255, 40), 1.2)); p.drawPath(path(T["body"]))
    p.setPen(Qt.NoPen); p.setBrush(c.darker(115)); p.drawPath(path(T["mirror_l"])); p.drawPath(path(T["mirror_r"]))
    p.setBrush(QColor(14, 16, 20)); p.drawPath(path(T["windscreen"])); p.drawPath(path(T["rear_glass"]))
    p.setBrush(QColor(20, 22, 26)); p.drawPath(path(T["roof"]))
    gl = QLinearGradient(0, 400, 0, 560); gl.setColorAt(0, QColor(70, 80, 95)); gl.setColorAt(1, QColor(20, 24, 30))
    p.setBrush(gl); p.drawPath(path(T["panorama"]))
    p.setBrush(QColor(240, 250, 255)); p.drawPath(path(T["headlight_l"])); p.drawPath(path(T["headlight_r"]))
    p.setBrush(QColor(230, 30, 40)); p.drawPath(path(T["taillight"]))
    p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 60), 2))
    p.drawPath(path(T["bonnet_l"])); p.drawPath(path(T["bonnet_r"]))
    p.end(); img.save(out)


if __name__ == "__main__":
    import geometry
    app = QApplication(sys.argv)
    out = sys.argv[1]
    for name, col, gr, badge in (("Ibiza", "#C8102E", "seat", "SEAT"), ("Arona", "#C8102E", "seat", "SEAT"),
                                 ("Leon", "#C8102E", "seat", "SEAT"), ("Grand i10", "#1F6FB2", "hyundai", "HYUNDAI")):
        g = geometry.for_model(name)
        key = name.replace(" ", "_").lower()
        side(col, f"{out}/side_{key}.png", g)
        front(col, gr, f"{out}/front_{key}.png", badge, g)
