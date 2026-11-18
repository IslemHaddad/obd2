"""Speaker Test: play channel-isolated tones through the car radio (PC paired over Bluetooth), measure each
speaker with the PC microphone, guide the user through the radio's fader for front/rear."""
from __future__ import annotations

import array
import math
from datetime import datetime

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
from PySide6.QtWidgets import (QComboBox, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import common as C

RATE = 48000
TONE_HZ = 440.0
STEPS = [("Front left", "front", "L"), ("Front right", "front", "R"),
         ("Rear left", "rear", "L"), ("Rear right", "rear", "R")]


def tone(freq: float, secs: float, channel: str, sweep_to: float | None = None, vol: float = 0.5) -> bytes:
    """Interleaved stereo int16. channel: 'L', 'R' or 'B'. Optional log sweep freq→sweep_to."""
    n = int(RATE * secs)
    buf = array.array("h")
    ph = 0.0
    fade = int(RATE * 0.02)
    for i in range(n):
        f = freq * (sweep_to / freq) ** (i / n) if sweep_to else freq
        ph += 2 * math.pi * f / RATE
        env = min(1.0, i / fade, (n - i) / fade)
        v = int(32767 * vol * env * math.sin(ph))
        buf.append(v if channel in ("L", "B") else 0)
        buf.append(v if channel in ("R", "B") else 0)
    return buf.tobytes()


def goertzel_db(samples: array.array, freq: float, rate: int) -> float:
    """Level of one frequency in dBFS (Goertzel)."""
    n = len(samples)
    if n == 0:
        return -120.0
    k = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x / 32768.0 + k * s1 - s2
        s2, s1 = s1, s0
    power = s1 * s1 + s2 * s2 - k * s1 * s2
    amp = 2 * math.sqrt(max(power, 0.0)) / n
    return 20 * math.log10(max(amp, 1e-6))


class SpeakerPage(QWidget):
    def __init__(self, s):
        super().__init__()
        self.s = s
        self.sink = None
        self.src = None
        self.src_dev = None
        self._buf = None
        self.captured = array.array("h")
        self.results: dict[str, dict] = {}
        w, lay = C.page()
        QVBoxLayout(self).addWidget(w)
        self.layout().setContentsMargins(0, 0, 0, 0)
        lay.addWidget(C.label("Speaker Test", "h1"))
        lay.addWidget(C.label(
            "1. Pair this PC with the car radio over Bluetooth (like a phone) and select the radio's Bluetooth audio source. "
            "2. Choose the car as output below.  3. Put the PC inside the car (mic hears the cabin).  "
            "4. Follow the steps — the app plays each side, you set the radio FADER front/rear when asked.",
            "muted", True))
        self.out = QComboBox()
        self.inp = QComboBox()
        self._devices()
        lay.addLayout(C.row(C.label("Output (car)"), self.out, C.label("Microphone"), self.inp,
                            C.button("Refresh devices", slot=self._devices), "stretch"))
        self.instr = C.label("Press Start to begin.", "h2")
        self.instr.setWordWrap(True)
        self.start_btn = C.button("▶ Start test", "primary", self.start)
        self.play_btn = C.button("▶ Play this speaker", slot=self.play_current)
        self.ok_btn = C.button("✓ Works", slot=lambda: self.mark("OK"))
        self.bad_btn = C.button("✗ Silent / bad", "danger", lambda: self.mark("BAD"))
        self.sweep_btn = C.button("Rattle sweep (40 Hz → 12 kHz)", slot=self.sweep)
        for b in (self.play_btn, self.ok_btn, self.bad_btn):
            b.setEnabled(False)
        lay.addWidget(C.card(self.instr, C.row(self.start_btn, self.play_btn, self.ok_btn, self.bad_btn, "stretch",
                                               self.sweep_btn)))
        self.table = QTableWidget(4, 4)
        self.table.setHorizontalHeaderLabels(["Speaker", "Mic level", "Your verdict", "Result"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        for i, (name, _f, _c) in enumerate(STEPS):
            self.table.setItem(i, 0, QTableWidgetItem(name))
        lay.addWidget(self.table)
        self.summary = C.label("", "h2")
        lay.addWidget(self.summary)
        lay.addStretch(1)
        self.step = -1

    def _devices(self):
        self.out.clear()
        for d in QMediaDevices.audioOutputs():
            self.out.addItem(d.description(), d)
        self.inp.clear()
        self.inp.addItem("(no microphone — judge by ear)", None)
        for d in QMediaDevices.audioInputs():
            self.inp.addItem(d.description(), d)
        if self.inp.count() > 1:
            self.inp.setCurrentIndex(1)

    def _fmt(self, channels):
        f = QAudioFormat()
        f.setSampleRate(RATE)
        f.setChannelCount(channels)
        f.setSampleFormat(QAudioFormat.Int16)
        return f

    def _play(self, data: bytes, on_done=None):
        dev = self.out.currentData()
        if dev is None:
            return C.error_box("No audio output selected.")
        if self.sink:
            self.sink.stop()
        self.sink = QAudioSink(dev, self._fmt(2))
        self._buf = QBuffer()
        self._buf.setData(QByteArray(data))
        self._buf.open(QIODevice.ReadOnly)
        self.sink.start(self._buf)
        if on_done:
            QTimer.singleShot(int(len(data) / 4 / RATE * 1000) + 300, on_done)

    def _rec_start(self):
        self.captured = array.array("h")
        dev = self.inp.currentData()
        if dev is None:
            return
        self.src = QAudioSource(dev, self._fmt(1))
        self.src_dev = self.src.start()
        self.src_dev.readyRead.connect(self._rec_read)

    def _rec_read(self):
        data = bytes(self.src_dev.readAll())
        a = array.array("h")
        a.frombytes(data[: len(data) // 2 * 2])
        self.captured.extend(a)

    def _rec_stop(self) -> float | None:
        if not self.src:
            return None
        self.src.stop()
        self.src = None
        # skip the first 0.3 s (Bluetooth latency) and analyse the rest
        samples = self.captured[int(RATE * 0.3):]
        return goertzel_db(samples, TONE_HZ, RATE) if len(samples) > RATE // 4 else None

    # ---- guided steps
    def start(self):
        self.results.clear()
        for i in range(4):
            for j in (1, 2, 3):
                self.table.setItem(i, j, QTableWidgetItem(""))
        self.summary.setText("")
        self.step = 0
        self._show_step()

    def _show_step(self):
        name, fader, ch = STEPS[self.step]
        self.instr.setText(f"Step {self.step + 1}/4 — {name}:  set the radio FADER fully to the "
                           f"{fader.upper()}, then press Play. Listen: sound should come ONLY from the {name.lower()} "
                           f"speaker.")
        for b in (self.play_btn, self.ok_btn, self.bad_btn):
            b.setEnabled(True)

    def play_current(self):
        name, _fader, ch = STEPS[self.step]
        self.play_btn.setEnabled(False)
        self._rec_start()

        def done():
            lvl = self._rec_stop()
            self.results.setdefault(name, {})["level"] = lvl
            self.table.setItem(self.step, 1, QTableWidgetItem("—" if lvl is None else f"{lvl:.1f} dB"))
            self.play_btn.setEnabled(True)

        self._play(tone(TONE_HZ, 2.0, ch), done)

    def mark(self, verdict):
        name = STEPS[self.step][0]
        self.results.setdefault(name, {})["verdict"] = verdict
        it = QTableWidgetItem("Works" if verdict == "OK" else "Silent / bad")
        it.setForeground(QColor(C.GREEN if verdict == "OK" else C.RED))
        self.table.setItem(self.step, 2, it)
        if self.step < 3:
            self.step += 1
            self._show_step()
        else:
            self._finish()

    def _finish(self):
        for b in (self.play_btn, self.ok_btn, self.bad_btn):
            b.setEnabled(False)
        levels = [r.get("level") for r in self.results.values() if r.get("level") is not None]
        best = max(levels) if levels else None
        bad = []
        for i, (name, _f, _c) in enumerate(STEPS):
            r = self.results.get(name, {})
            lvl = r.get("level")
            weak = best is not None and lvl is not None and lvl < best - 12     # >12 dB quieter than the best
            ok = r.get("verdict") == "OK" and not weak
            txt = "OK" if ok else ("Much quieter than the others" if weak and r.get("verdict") == "OK" else "Problem")
            it = QTableWidgetItem(txt)
            it.setForeground(QColor(C.GREEN if ok else C.RED))
            self.table.setItem(i, 3, it)
            if not ok:
                bad.append(name)
        self.summary.setText("All 4 speakers work." if not bad else "Check: " + ", ".join(bad))
        self.summary.setStyleSheet(f"color: {C.GREEN if not bad else C.RED}")
        hist = self.s.store.get("speaker_tests") or []
        hist.append({"date": datetime.now().isoformat(timespec="seconds"), "results": self.results})
        self.s.store.set("speaker_tests", hist[-50:])
        self.instr.setText("Done. Put the fader back to the middle.")

    def sweep(self):
        self.instr.setText("Sweep playing on both channels — listen for buzzing, rattling or crackling from any door.")
        self._play(tone(40, 12.0, "B", sweep_to=12000, vol=0.4))
