"""Theme, background workers and small helpers shared by all pages."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget)

ACCENT = "#0A84FF"
BG = "#111214"
CARD = "#1C1D21"
CARD2 = "#26272C"
TEXT = "#F2F2F7"
MUTED = "#8E8E93"
GREEN = "#30D158"
YELLOW = "#FFD60A"
ORANGE = "#FF9F0A"
RED = "#FF453A"

STYLE = f"""
* {{ font-family: 'Inter', 'Segoe UI', 'Ubuntu', sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QWidget#page {{ background: {BG}; }}
QLabel#h1 {{ font-size: 26px; font-weight: 700; }}
QLabel#h2 {{ font-size: 16px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QFrame#card {{ background: {CARD}; border-radius: 14px; }}
QListWidget#nav {{ background: #0B0C0E; border: none; padding-top: 12px; outline: 0; }}
QListWidget#nav::item {{ padding: 11px 16px; margin: 2px 8px; border-radius: 9px; color: {MUTED}; }}
QListWidget#nav::item:selected {{ background: {CARD2}; color: {TEXT}; }}
QPushButton {{ background: {CARD2}; border: none; border-radius: 9px; padding: 8px 14px; }}
QPushButton:hover {{ background: #303137; }}
QPushButton:disabled {{ color: #55565C; background: #1E1F23; }}
QPushButton#primary {{ background: {ACCENT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: #2B95FF; }}
QPushButton#primary:disabled, QPushButton#danger:disabled {{ background: #1E1F23; color: #55565C; }}
QPushButton#danger {{ background: #3A1D1D; color: {RED}; font-weight: 600; }}
QPushButton#danger:hover {{ background: #4A2323; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {CARD2}; border: 1px solid #2E2F35; border-radius: 8px; padding: 6px 8px; selection-background-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {CARD2}; selection-background-color: {ACCENT}; }}
QTableWidget, QListWidget, QTreeWidget {{ background: {CARD}; border: none; border-radius: 12px; gridline-color: #2A2B30;
    alternate-background-color: #202125; }}
QHeaderView::section {{ background: {CARD}; color: {MUTED}; border: none; padding: 6px; font-weight: 600; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: #2B3A55; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 14px; margin-right: 4px; border-radius: 8px; }}
QTabBar::tab:selected {{ background: {CARD2}; color: {TEXT}; }}
QProgressBar {{ background: {CARD2}; border: none; border-radius: 5px; height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #3A3B40; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QToolTip {{ background: {CARD2}; color: {TEXT}; border: 1px solid #3A3B40; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    for role, c in [(QPalette.Window, BG), (QPalette.Base, CARD2), (QPalette.AlternateBase, CARD),
                    (QPalette.Text, TEXT), (QPalette.WindowText, TEXT), (QPalette.Button, CARD2),
                    (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#FFFFFF")]:
        p.setColor(role, QColor(c))
    app.setPalette(p)
    app.setStyleSheet(STYLE)


# ---------------------------------------------------------------- workers
class _Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(object)


class Job(QRunnable):
    def __init__(self, fn, *args, **kw):
        super().__init__()
        self.fn, self.args, self.kw = fn, args, kw
        self.signals = _Signals()

    def run(self):
        try:
            r = self.fn(*self.args, **self.kw)
        except Exception as e:                 # noqa: BLE001 — surfaced to the UI
            traceback.print_exc()
            self.signals.error.emit(str(e) or e.__class__.__name__)
        else:
            self.signals.done.emit(r)


_pool = QThreadPool.globalInstance()
_alive: set[Job] = set()


def run_bg(fn, on_done=None, on_error=None, *args, **kw) -> Job:
    """Run fn in the thread pool; callbacks are delivered on the GUI thread."""
    j = Job(fn, *args, **kw)
    _alive.add(j)
    j.setAutoDelete(False)

    def fin(*_):
        _alive.discard(j)

    if on_done:
        j.signals.done.connect(on_done)
    j.signals.error.connect(on_error or (lambda m: error_box(m)))
    j.signals.done.connect(fin)
    j.signals.error.connect(fin)
    _pool.start(j)
    return j


# ---------------------------------------------------------------- widgets
def error_box(msg: str, parent=None):
    QMessageBox.critical(parent or QApplication.activeWindow(), "Error", msg)


def confirm(parent, title: str, text: str, ok: str = "Continue") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning)
    yes = box.addButton(ok, QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def label(text: str = "", obj: str | None = None, wrap: bool = False) -> QLabel:
    l = QLabel(text)
    if obj:
        l.setObjectName(obj)
    l.setWordWrap(wrap)
    return l


def button(text: str, kind: str | None = None, slot=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


def card(*widgets, layout: str = "v", spacing: int = 10, margins: int = 16) -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f) if layout == "v" else QHBoxLayout(f)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, QWidget):
            lay.addWidget(w)
        elif w == "stretch":
            lay.addStretch(1)
        else:
            lay.addLayout(w)
    return f


def page() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    w.setObjectName("page")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 22, 28, 22)
    lay.setSpacing(14)
    return w, lay


def row(*widgets, spacing: int = 8) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setSpacing(spacing)
    for w in widgets:
        if w == "stretch":
            h.addStretch(1)
        elif isinstance(w, QWidget):
            h.addWidget(w)
        else:
            h.addLayout(w)
    return h


def pill(text: str, color: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"background: {QColor(color).darker(330).name()}; color: {color}; border-radius: 10px;"
                    f"padding: 3px 10px; font-weight: 600; font-size: 12px;")
    return l
