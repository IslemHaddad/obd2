"""Pre-render car outlines (side + front PNG) for the Android app."""
import os
import sys

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(__file__))
import param          # noqa: E402
import preview2       # noqa: E402

SHAPES = {   # key: (car, colour, grille, badge)
    "leon": (param.Car(4263, 1810, 1446, 2636, "hatch"), "#C8102E", "seat", "SEAT"),
    "ibiza": (param.Car(4059, 1780, 1444, 2564, "hatch"), "#C8102E", "seat", "SEAT"),
    "arona": (param.Car(4138, 1780, 1552, 2566, "suv"), "#C8102E", "seat", "SEAT"),
    "grandi10": (param.Car(3765, 1660, 1520, 2425, "hatch"), "#1F6FB2", "hyundai", "HYUNDAI"),
    "i10": (param.Car(3645, 1660, 1500, 2385, "hatch"), "#1F6FB2", "hyundai", "HYUNDAI"),
    "clio4": (param.Car(4062, 1732, 1448, 2589, "hatch"), "#F2B705", "renault", ""),
    "clio5": (param.Car(4050, 1798, 1440, 2585, "hatch"), "#F2B705", "renault", ""),
    "captur": (param.Car(4122, 1778, 1567, 2606, "suv"), "#E8601C", "renault", ""),
    "megane": (param.Car(4359, 1814, 1446, 2669, "hatch"), "#F2B705", "renault", ""),
    "symbol": (param.Car(4346, 1733, 1517, 2634, "sedan"), "#B8BCC4", "renault", ""),
    "generic_hatch": (param.Car(4059, 1780, 1444, 2564, "hatch"), "#8E959F", "seat", ""),
    "generic_suv": (param.Car(4138, 1780, 1552, 2566, "suv"), "#8E959F", "seat", ""),
    "generic_sedan": (param.Car(4346, 1733, 1517, 2634, "sedan"), "#8E959F", "seat", ""),
}

if __name__ == "__main__":
    app = QApplication(sys.argv)
    out = sys.argv[1]
    for key, (car, col, gr, badge) in SHAPES.items():
        preview2.draw_side(param.side(car, scale=0.3), col).save(f"{out}/{key}_side.png")
        preview2.draw_front(param.front(car, scale=0.3, grille=gr), col, badge).save(f"{out}/{key}_front.png")
