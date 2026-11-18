"""Connection + live polling controller shared by all pages.

Adds: auto-reconnect, last-adapter memory, SEAT/VAG module values as live gauges, background trip logger,
battery monitor, alerts (temperatures, voltage, warnings, new faults)."""
from __future__ import annotations

import csv
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from .. import features as F
from .. import pids
from ..elm import ELM327, ELMError
from ..obd import OBD
from ..store import Store
from ..transport import BLETransport, SerialTransport, TCPTransport
from ..vag import MODULE_BY_ADDR, VAG, numeric
from ..hyundai import Hyundai
from .. import catalog
from .. import adapters as AD
from .common import run_bg

DEFAULT_TILES = [
    {"pid": 0x0C, "style": "arc", "warn": 6000}, {"pid": 0x0D, "style": "ring"},
    {"pid": 0x05, "style": "ring", "warn": 110}, {"vag": F.VAG_PRESETS[0], "style": "ring", "warn": 125},
    {"pid": 0x11, "style": "bar"}, {"pid": 0x42, "style": "number"},
]


def _open(kind: str, arg):
    if kind == "serial":
        port, baud = arg
        try:
            t = SerialTransport(port, int(baud))
        except Exception as e:
            if "Permission denied" in str(e):
                raise RuntimeError(f"{e}\n\nRun once:  sudo usermod -aG dialout $USER  then log out and in.")
            raise
    elif kind == "tcp":
        t = TCPTransport(arg[0], int(arg[1]))
    elif kind == "ble":
        t = BLETransport(arg)
    else:
        from ..sim import SimTransport
        t = SimTransport(arg if arg in ("hyundai", "renault") else "seat")
    elm = ELM327(t)
    try:
        elm.initialize()
    except Exception:
        t.close()
        raise
    obd = OBD(elm)
    sup = obd.supported_pids()
    if elm.profile.fast:
        try:
            obd.single_ecu = len(obd.discover_ecus()) == 1
        except ELMError:
            pass
    return elm, obd, sup


class Session(QObject):
    state_changed = Signal(str, str)        # idle / connecting / connected / reconnecting / failed
    values = Signal(object)
    rate = Signal(float)
    battery = Signal(float)
    info = Signal(object)
    alert = Signal(str, str)                # level (warn|bad), text
    trip_saved = Signal(object)

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
        self.override_ids: list[int] | None = None
        self.extra_vag: list[dict] = []        # extra module values requested by the visible page
        self.extra_pids: list[int] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._log_file = None
        self._log_writer = None
        self.log_path = None
        self.tiles: list[dict] = store.get("tiles") or [dict(t) for t in DEFAULT_TILES]
        self._conn: tuple | None = None
        self.trips = F.TripRecorder(store)
        self.batt = F.BatteryMonitor(store)
        self.alerts = F.AlertMonitor(store, lambda lvl, txt: self.alert.emit(lvl, txt))
        self.last_volts: float | None = None
        self.adapter: dict | None = None
        self._known_faults: set[str] | None = None
        veh = store.get("vehicle", {}) or {}
        self.family = catalog.FAMILY.get(veh.get("brand", "seat"), "vag")

    def _tool(self):
        return Hyundai(self.elm, self.family) if self.family in ("hyundai", "renault") else VAG(self.elm)

    def set_family(self, family: str):
        if family != self.family:
            self.family = family
            if self.elm:
                self.vag = self._tool()

    # ---------------------------------------------------------------- connection
    @property
    def last_connection(self):
        lc = F.setting(self.store, "last_conn")
        return tuple(lc) if lc else None

    def connect_saved(self, rec: dict):
        arg = rec["arg"]
        self.connect(rec["kind"], tuple(arg) if isinstance(arg, list) else arg)

    def connect_last(self):
        lc = self.last_connection
        if lc:
            kind, arg = lc
            self.connect(kind, tuple(arg) if isinstance(arg, list) else arg)

    def connect(self, kind: str, arg) -> None:
        self.disconnect()
        self._set("connecting", str(arg))
        self._conn = (kind, arg)

        def done(r):
            self.elm, self.obd, self.supported = r
            self.vag = self._tool()
            F.set_setting(self.store, "last_conn", [kind, list(arg) if isinstance(arg, tuple) else arg])
            name = {"ble": "Bluetooth LE adapter", "serial": f"Serial {arg[0] if isinstance(arg, (list, tuple)) else arg}",
                    "tcp": "Wi-Fi adapter", "sim": "Demo"}.get(kind, kind)
            self.adapter = AD.remember(self.store, kind, arg, name, self.elm.profile)
            self._set("connected", f"{self.elm.version} · {self.elm.protocol_name}")
            self._start_poll()
            run_bg(self._read_info, self.info.emit, lambda _m: None)

        run_bg(lambda: _open(kind, arg), done, lambda msg: self._set("failed", msg))

    def _read_info(self) -> dict:
        o = self.obd
        with self.elm.lock:
            self.vin = o.mode09(0x02)
            return {"vin": self.vin, "cal": o.mode09(0x04), "ecu": o.mode09(0x0A),
                    "adapter": self.elm.version, "protocol": self.elm.protocol_name, "vag": self.vag.supported}

    def disconnect(self) -> None:
        self._conn = None
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        self._thread = None
        self.stop_logging()
        tr = self.trips.finish()
        if tr:
            self.trip_saved.emit(tr)
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

    def _reconnect(self) -> bool:
        """Runs in the poll thread after the link died. True when back online."""
        if not self._conn or not F.setting(self.store, "auto_reconnect"):
            return False
        kind, arg = self._conn
        try:
            self.elm.close()
        except Exception:
            pass
        for attempt in range(1, 41):                       # ~2 minutes
            if self._stop.is_set():
                return False
            self._set("reconnecting", f"Link lost — reconnecting (attempt {attempt})…")
            try:
                self.elm, self.obd, self.supported = _open(kind, arg)
                self.vag = self._tool()
                self._set("connected", f"{self.elm.version} · {self.elm.protocol_name} (reconnected)")
                return True
            except Exception:
                self._stop.wait(3)
        return False

    # ---------------------------------------------------------------- tiles
    def selected(self) -> list[int]:
        seen, out = set(), []
        for t in self.tiles:
            p = t.get("pid")
            if p is not None and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def vag_tiles(self) -> list[dict]:
        seen, out = set(), []
        for t in self.tiles + [{"vag": d} for d in self.extra_vag]:
            d = t.get("vag")
            if d and (d["module"], d["did"]) not in seen:
                seen.add((d["module"], d["did"]))
                out.append(d)
        return out

    def save_tiles(self):
        self.store.set("tiles", self.tiles)
        if self._log_writer:
            self.stop_logging()
            self.start_logging()

    # ---------------------------------------------------------------- polling
    def _start_poll(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll_ids(self) -> list[int]:
        if self.override_ids:
            return self.override_ids
        ids = self.selected()
        ids += [p for p in F.BACKGROUND_PIDS + self.extra_pids if p not in ids]
        return [p for p in ids if p in pids.BY_ID and (not self.supported or p in self.supported)]

    def _read_vag(self) -> dict:
        out = {}
        if not self.vag or not self.vag.supported or self.family != "vag":
            return out
        by_mod: dict[str, list[dict]] = {}
        for d in self.vag_tiles():
            by_mod.setdefault(d["module"], []).append(d)
        for addr, defs in by_mod.items():
            m = MODULE_BY_ADDR.get(addr)
            if not m:
                continue
            with self.vag.channel(m):
                for d in defs:
                    try:
                        v = numeric(d, self.vag.read_did(int(d["did"])))
                    except ELMError:
                        v = None
                    if v is not None:
                        out[F.vpid_from(d).id] = v
        return out

    def _check_faults(self):
        codes = [d.code for d in self.obd.dtcs("03", "Stored") + self.obd.dtcs("07", "Pending")]
        if self._known_faults is None:
            self._known_faults = set(codes)
        else:
            self._known_faults = self.alerts.new_faults(codes, self._known_faults)

    def _poll(self):
        frames, t0, cycle = 0, time.monotonic(), 0
        last_vag, last_faults, rpm = 0.0, time.monotonic(), None
        while not self._stop.is_set():
            if not self.poll_enabled or not self.elm or self.state != "connected":
                time.sleep(0.1)
                continue
            try:
                with self.elm.lock:
                    vals = self.obd.read(self._poll_ids())
                    rpm = vals.get(F.RPM, rpm)
                    cycle += 1
                    engine_off = not rpm
                    if F.VOLTS in vals:                         # car's own voltage (accurate) when supported
                        v = vals[F.VOLTS]
                        self.last_volts = v
                        if cycle % 10 == 1:
                            self.battery.emit(v)
                        self.batt.feed(v, rpm)
                        if cycle % 50 == 5 and self.adapter:   # learn this adapter's voltmeter error
                            av = self.elm.battery_voltage()
                            if av is not None:
                                AD.learn_voltage(self.store, self.adapter["key"], av, v)
                    elif engine_off or cycle % 25 == 1:        # fallback: adapter voltmeter, corrected if learned
                        v = self.elm.battery_voltage()
                        off = (AD.get(self.store, self.adapter["key"]) or {}).get("volt_offset") if self.adapter else None
                        if v is not None and off is not None:
                            v -= off
                        if v is not None:
                            self.last_volts = v
                            self.battery.emit(v)
                            self.batt.feed(v, rpm)
                    now = time.monotonic()
                    if self.vag_tiles() and now - last_vag >= 1.0 and not self.override_ids:
                        vals.update(self._read_vag())
                        last_vag = now
                    if F.setting(self.store, "alert_new_faults") and \
                            now - last_faults >= float(F.setting(self.store, "fault_check_s")):
                        self._check_faults()
                        last_faults = now
            except ELMError:
                vals = {}
            except Exception as e:                                # transport died
                if self._stop.is_set():
                    return
                if not self._reconnect():
                    self._set("failed", f"Connection lost: {e}")
                    return
                continue
            if vals:
                vals["_t"] = time.monotonic()
                self.values.emit(vals)
                self._log(vals)
                self.trips.feed(vals["_t"], vals)
                labels = [dict(t, key=(t.get("pid") if t.get("pid") is not None else F.vpid_from(t["vag"]).id),
                               label=(pids.BY_ID[t["pid"]].name if t.get("pid") in pids.BY_ID
                                      else t.get("vag", {}).get("name", ""))) for t in self.tiles]
                self.alerts.check(vals, self.last_volts, labels)
            frames += 1
            dt = time.monotonic() - t0
            if dt >= 1:
                self.rate.emit(frames / dt)
                frames, t0 = 0, time.monotonic()
            time.sleep(0.001)

    # ---------------------------------------------------------------- CSV logging
    def start_logging(self):
        self.log_path = self.store.logs_dir() / f"obd_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self._log_file = open(self.log_path, "w", newline="")
        self._log_writer = csv.writer(self._log_file)
        self._log_cols = [p for p in self.selected() if p in pids.BY_ID]
        self._log_vag = [F.vpid_from(d) for d in self.vag_tiles()]
        self._log_writer.writerow(["timestamp"] + [f"{pids.BY_ID[p].name} ({pids.BY_ID[p].unit})" for p in self._log_cols]
                                  + [f"{v.name} ({v.unit})" for v in self._log_vag])

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
            w.writerow([f"{time.time():.3f}"] + [f"{vals[p]:.3f}" if p in vals else "" for p in self._log_cols]
                       + [f"{vals[v.id]:.3f}" if v.id in vals else "" for v in self._log_vag])
