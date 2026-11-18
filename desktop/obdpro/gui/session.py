"""Connection + live polling controller shared by all pages."""
from __future__ import annotations

import csv
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from .. import pids
from ..elm import ELM327, ELMError
from ..obd import OBD
from ..store import Store
from ..transport import BLETransport, SerialTransport, TCPTransport
from ..vag import VAG
from .common import run_bg

DEFAULT_TILES = [
    {"pid": 0x0C, "style": "arc", "warn": 6000}, {"pid": 0x0D, "style": "ring"},
    {"pid": 0x05, "style": "ring", "warn": 110}, {"pid": 0x04, "style": "graph"},
    {"pid": 0x11, "style": "bar"}, {"pid": 0x42, "style": "number"},
]


class Session(QObject):
    state_changed = Signal(str, str)        # state, detail  (idle / connecting / connected / failed)
    values = Signal(object)
    rate = Signal(float)
    battery = Signal(float)
    info = Signal(object)

    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.elm: ELM327 | None = None
        self.obd: OBD | None = None
        self.vag: VAG | None = None
        self.state = "idle"
        self.supported: set[int] = set()
        self.vin: str | None = None
        self.poll_enabled = True
        self.override_ids: list[int] | None = None     # e.g. power run: poll only these PIDs
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._log_file = None
        self._log_writer = None
        self.log_path = None
        self.tiles: list[dict] = store.get("tiles") or [dict(t) for t in DEFAULT_TILES]

    # ---------------------------------------------------------------- connection
    def connect(self, kind: str, arg) -> None:
        self.disconnect()
        self._set("connecting", str(arg))

        def work():
            if kind == "serial":
                port, baud = arg
                try:
                    t = SerialTransport(port, baud)
                except Exception as e:
                    if "Permission denied" in str(e):
                        raise RuntimeError(f"{e}\n\nRun once:  sudo usermod -aG dialout $USER  then log out and in.")
                    raise
            elif kind == "tcp":
                t = TCPTransport(*arg)
            elif kind == "ble":
                t = BLETransport(arg)
            else:
                from ..sim import SimTransport
                t = SimTransport()
            elm = ELM327(t)
            try:
                elm.initialize()
            except Exception:
                t.close()
                raise
            obd = OBD(elm)
            sup = obd.supported_pids()
            return elm, obd, sup

        def done(r):
            self.elm, self.obd, self.supported = r
            self.vag = VAG(self.elm)
            self._set("connected", f"{self.elm.version} · {self.elm.protocol_name}")
            self._start_poll()
            run_bg(self._read_info, self.info.emit, lambda _m: None)

        def fail(msg):
            self._set("failed", msg)

        run_bg(work, done, fail)

    def _read_info(self) -> dict:
        o = self.obd
        self.vin = o.mode09(0x02)
        return {"vin": self.vin, "cal": o.mode09(0x04), "ecu": o.mode09(0x0A),
                "adapter": self.elm.version, "protocol": self.elm.protocol_name,
                "vag": self.vag.supported}

    def disconnect(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        self.stop_logging()
        if self.elm:
            try:
                self.elm.close()
            except Exception:
                pass
        self.elm = self.obd = self.vag = None
        if self.state != "idle":
            self._set("idle", "")

    def _set(self, s: str, detail: str):
        self.state = s
        self.state_changed.emit(s, detail)

    @property
    def connected(self) -> bool:
        return self.state == "connected"

    # ---------------------------------------------------------------- polling
    def selected(self) -> list[int]:
        seen, out = set(), []
        for t in self.tiles:
            if t["pid"] not in seen:
                seen.add(t["pid"])
                out.append(t["pid"])
        return out

    def save_tiles(self):
        self.store.set("tiles", self.tiles)
        if self._log_writer:
            self.stop_logging()
            self.start_logging()

    def _start_poll(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        frames, t0, cycle = 0, time.monotonic(), 0
        while not self._stop.is_set():
            if not self.poll_enabled or not self.elm:
                time.sleep(0.1)
                continue
            ids = self.override_ids or [p for p in self.selected() if p in pids.BY_ID]
            try:
                with self.elm.lock:
                    vals = self.obd.read(ids) if ids else {}
                    cycle += 1
                    if cycle % 25 == 1:
                        v = self.elm.battery_voltage()
                        if v is not None:
                            self.battery.emit(v)
            except (ELMError, OSError, ConnectionError) as e:
                if isinstance(e, (OSError, ConnectionError)):
                    self._set("failed", f"Connection lost: {e}")
                    return
                vals = {}
            if vals:
                vals["_t"] = time.monotonic()
                self.values.emit(vals)
                self._log(vals)
            frames += 1
            dt = time.monotonic() - t0
            if dt >= 1:
                self.rate.emit(frames / dt)
                frames, t0 = 0, time.monotonic()
            time.sleep(0.001)          # let other jobs grab the bus lock

    # ---------------------------------------------------------------- CSV logging
    def start_logging(self):
        self.log_path = self.store.logs_dir() / f"obd_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self._log_file = open(self.log_path, "w", newline="")
        self._log_writer = csv.writer(self._log_file)
        self._log_cols = self.selected()
        self._log_writer.writerow(["timestamp"] + [f"{pids.BY_ID[p].name} ({pids.BY_ID[p].unit})"
                                                   for p in self._log_cols if p in pids.BY_ID])

    def stop_logging(self):
        if self._log_file:
            self._log_file.close()
        self._log_file = self._log_writer = None

    @property
    def logging(self) -> bool:
        return self._log_writer is not None

    def _log(self, vals: dict):
        w = self._log_writer
        if w:
            w.writerow([f"{time.time():.3f}"] + [f"{vals[p]:.3f}" if p in vals else ""
                                                for p in self._log_cols if p in pids.BY_ID])
