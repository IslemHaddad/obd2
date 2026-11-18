"""Render the parametric outlines (param.py) to a contact sheet for review."""
import math
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(__file__))
import param  # noqa: E402


def path(cmds):
    p = QPainterPath()
    for c in cmds:
        if c[0] == "M":
            p.moveTo(c[1], c[2])
        elif c[0] == "L":
            p.lineTo(c[1], c[2])
        elif c[0] == "C":
            p.cubicTo(*c[1:])
        else:
            p.closeSubpath()
    return p


def wheel(p, cx, cy, r):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(14, 14, 16)); p.drawEllipse(QPointF(cx, cy), r, r)
    g = QRadialGradient(QPointF(cx, cy), r * 0.72)
    g.setColorAt(0, QColor(215, 217, 222)); g.setColorAt(0.85, QColor(150, 152, 160)); g.setColorAt(1, QColor(90, 92, 98))
    p.setBrush(g); p.drawEllipse(QPointF(cx, cy), r * 0.70, r * 0.70)
    p.setBrush(QColor(28, 30, 34))
    for i in range(5):                                  # 5 twin-spoke windows
        a = i * 2 * math.pi / 5
        q = QPainterPath()
        q.moveTo(cx + math.cos(a + 0.22) * r * 0.2, cy + math.sin(a + 0.22) * r * 0.2)
        q.lineTo(cx + math.cos(a + 0.30) * r * 0.62, cy + math.sin(a + 0.30) * r * 0.62)
        q.lineTo(cx + math.cos(a + 0.98) * r * 0.62, cy + math.sin(a + 0.98) * r * 0.62)
        q.lineTo(cx + math.cos(a + 1.06) * r * 0.2, cy + math.sin(a + 1.06) * r * 0.2)
        q.closeSubpath()
        p.drawPath(q)
    p.setBrush(QColor(70, 72, 78)); p.drawEllipse(QPointF(cx, cy), r * 0.14, r * 0.14)


def draw_side(d, color):
    W, H = int(d["W"]), int(d["H"])
    img = QImage(W, H, QImage.Format_ARGB32); img.fill(QColor(16, 17, 19))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    gy = d["ground"]
    sh = QRadialGradient(QPointF(W / 2, gy), W * 0.5); sh.setColorAt(0, QColor(0, 0, 0, 200)); sh.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.NoPen); p.setBrush(sh); p.drawEllipse(QPointF(W / 2, gy), W * 0.47, 9)
    c = QColor(color)
    top = min(pt[2] for pt in d["body"] if len(pt) > 2)
    g = QLinearGradient(0, top, 0, gy)
    g.setColorAt(0, c.lighter(150)); g.setColorAt(0.35, c.lighter(110)); g.setColorAt(0.36, c.darker(105))
    g.setColorAt(0.7, c.darker(130)); g.setColorAt(1, c.darker(190))
    p.setBrush(g); p.setPen(QPen(QColor(255, 255, 255, 50), 1)); p.drawPath(path(d["body"]))
    p.setPen(Qt.NoPen)
    if d["cladding"]:
        p.setBrush(QColor(30, 31, 34)); p.drawPath(path(d["cladding"]))
    gl = QLinearGradient(0, top, 0, top + 60); gl.setColorAt(0, QColor(85, 95, 110)); gl.setColorAt(1, QColor(14, 16, 20))
    p.setBrush(gl); p.drawPath(path(d["glass"]))
    p.setBrush(QColor(8, 8, 10)); p.drawPath(path(d["c_pillar"])); p.drawPath(path(d["b_pillar"]))
    p.setBrush(c.darker(115)); p.drawPath(path(d["mirror"]))
    p.setBrush(QColor(28, 30, 34)); p.drawPath(path(d["headlight"]))
    p.setBrush(QColor(200, 20, 30)); p.drawPath(path(d["taillight"]))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 70), 1.4)); p.drawPath(path(d["shoulder"]))
    p.setPen(QPen(QColor(0, 0, 0, 70), 1.4)); p.drawPath(path(d["crease"]))
    p.setPen(QPen(QColor(0, 0, 0, 110), 2)); p.drawPath(path(d["sill"]))
    p.setPen(QPen(QColor(190, 245, 255), 2.2, Qt.SolidLine, Qt.RoundCap)); p.drawPath(path(d["drl"]))
    p.setPen(QPen(QColor(0, 0, 0, 120), 2.2, Qt.SolidLine, Qt.RoundCap)); p.drawPath(path(d["handles"]))
    for cx, cy, r in d["wheels"]:
        wheel(p, cx, cy, r)
    p.end()
    return img


def draw_front(d, color, badge):
    W, H = int(d["W"]), int(d["H"])
    img = QImage(W, H, QImage.Format_ARGB32); img.fill(QColor(16, 17, 19))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    gy = d["ground"]
    sh = QRadialGradient(QPointF(W / 2, gy), W * 0.5); sh.setColorAt(0, QColor(0, 0, 0, 200)); sh.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.NoPen); p.setBrush(sh); p.drawEllipse(QPointF(W / 2, gy), W * 0.46, 8)
    p.setBrush(QColor(12, 12, 14))
    for x, y, w, h in d["tyres"]:
        p.drawRoundedRect(QRectF(x, y, w, h), 5, 5)
    c = QColor(color)
    xs = [pt[1] for pt in d["body"] if len(pt) > 2]
    g = QLinearGradient(min(xs), 0, max(xs), 0)
    g.setColorAt(0, c.darker(160)); g.setColorAt(0.25, c); g.setColorAt(0.5, c.lighter(125)); g.setColorAt(0.75, c); g.setColorAt(1, c.darker(160))
    p.setBrush(g); p.setPen(QPen(QColor(255, 255, 255, 50), 1)); p.drawPath(path(d["body"]))
    p.setPen(Qt.NoPen)
    gl = QLinearGradient(0, 0, 0, gy * 0.45); gl.setColorAt(0, QColor(90, 100, 115)); gl.setColorAt(1, QColor(14, 16, 20))
    p.setBrush(gl); p.drawPath(path(d["glass"]))
    p.setBrush(c.darker(115)); p.drawPath(path(d["mirror_l"])); p.drawPath(path(d["mirror_r"]))
    p.setBrush(QColor(26, 28, 32)); p.drawPath(path(d["headlight_l"])); p.drawPath(path(d["headlight_r"]))
    p.setPen(QPen(QColor(200, 245, 255), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); p.setBrush(Qt.NoBrush)
    p.drawPath(path(d["drl_l"])); p.drawPath(path(d["drl_r"]))
    p.setPen(QPen(QColor(190, 192, 200), 2)); p.setBrush(QColor(16, 16, 18)); p.drawPath(path(d["grille"]))
    p.setPen(Qt.NoPen); p.setBrush(QColor(16, 16, 18))
    p.drawPath(path(d["intake_l"])); p.drawPath(path(d["intake_r"])); p.drawPath(path(d["lower"]))
    f = QFont(); f.setBold(True); f.setPointSize(9); p.setFont(f); p.setPen(QColor(235, 235, 240))
    bx, by = d["badge"]
    p.drawText(QRectF(bx - 60, by - 10, 120, 20), Qt.AlignCenter, badge)
    p.end()
    return img


if __name__ == "__main__":
    app = QApplication(sys.argv)
    out = sys.argv[1]
    imgs = []
    for name, (car, col, gr, badge) in param.CARS.items():
        s = draw_side(param.side(car), col)
        f = draw_front(param.front(car, grille=gr), col, badge)
        row = QImage(s.width() + f.width() + 30, max(s.height(), f.height()) + 34, QImage.Format_ARGB32)
        row.fill(QColor(16, 17, 19))
        p = QPainter(row); p.setRenderHint(QPainter.Antialiasing)
        p.drawImage(0, row.height() - s.height(), s); p.drawImage(s.width() + 30, row.height() - f.height(), f)
        ft = QFont(); ft.setPointSize(11); ft.setBold(True); p.setFont(ft); p.setPen(QColor(200, 200, 205))
        p.drawText(8, 20, name); p.end()
        imgs.append(row)
    W = max(i.width() for i in imgs); H = sum(i.height() for i in imgs)
    sheet = QImage(W, H, QImage.Format_ARGB32); sheet.fill(QColor(16, 17, 19))
    p = QPainter(sheet); y = 0
    for i in imgs:
        p.drawImage(0, y, i); y += i.height()
    p.end(); sheet.save(f"{out}/sheet2.png")
