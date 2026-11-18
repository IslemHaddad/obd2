"""Trip logger, battery monitor, alerts, fault history, user labels, VAG live gauges."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

from .store import Store

RPM, SPEED, THROTTLE, COOLANT, IAT, VOLTS = 0x0C, 0x0D, 0x11, 0x05, 0x0F, 0x42
BACKGROUND_PIDS = [RPM, SPEED, THROTTLE, COOLANT, IAT, VOLTS]


# ---------------------------------------------------------------- settings with defaults (all user-editable)
DEFAULTS = {
    "theme": "dark", "font_scale": 1.0, "autoconnect": False, "auto_reconnect": True,
    "alert_coolant": 110.0, "alert_oil": 125.0, "alert_volt_low": 11.8, "alert_volt_high": 15.0,
    "alert_new_faults": True, "fault_check_s": 120, "harsh_brake_kmh_s": 12.0, "full_throttle_pct": 90.0,
    "batt_rest_ok": 12.4, "batt_crank_ok": 9.6, "batt_charge_min": 13.5, "batt_charge_max": 14.8,
}


def setting(store: Store, key: str):
    st = store.get("settings", {}) or {}
    return st.get(key, DEFAULTS.get(key))


def set_setting(store: Store, key: str, value) -> None:
    st = store.get("settings", {}) or {}
    st[key] = value
    store.set("settings", st)


# ---------------------------------------------------------------- VAG live gauges (module DIDs as gauges)
@dataclass(frozen=True)
class VPID:
    """Duck-types pids.PID for GaugeTile: id is a string key 'vag:01:11BD'."""
    id: str
    name: str
    unit: str
    min: float
    max: float
    module: str
    did: int
    defn: tuple


VAG_PRESETS = [
    {"module": "01", "did": 0x11BD, "name": "Oil Temp", "unit": "°C", "min": 0, "max": 150,
     "kind": "number", "offset": 0, "length": 2, "scale": 0.1, "add": -273.15},
    {"module": "01", "did": 0x1063, "name": "Coolant (engine)", "unit": "°C", "min": 0, "max": 130,
     "kind": "number", "offset": 0, "length": 2, "scale": 0.1, "add": -273.15},
    {"module": "01", "did": 0x10E0, "name": "Odometer", "unit": "km", "min": 0, "max": 400000,
     "kind": "number", "offset": 1, "length": 3, "scale": 1, "add": 0},
]


def vpid_from(defn: dict) -> VPID:
    return VPID(f"vag:{defn['module']}:{defn['did']:04X}", defn["name"], defn.get("unit", ""),
                float(defn.get("min", 0)), float(defn.get("max", 100)), defn["module"], int(defn["did"]),
                tuple(sorted((k, v) for k, v in defn.items() if k != "id")))


# ---------------------------------------------------------------- labels (user descriptions)
def label(store: Store, key: str) -> str | None:
    return (store.get("labels", {}) or {}).get(key)


def set_label(store: Store, key: str, text: str) -> None:
    lab = store.get("labels", {}) or {}
    if text.strip():
        lab[key] = text.strip()
    else:
        lab.pop(key, None)
    store.set("labels", lab)


def fault_description(store: Store, module: str, code: str, default: str) -> str:
    return label(store, f"dtc:{module}:{code}") or label(store, f"dtc:*:{code}") or default


# ---------------------------------------------------------------- fault history
def record_faults(store: Store, vin: str | None, module: str, faults: list[tuple[str, str]], event: str = "scan"):
    """faults: [(code, state)]. Also records an 'ok' marker so 'gone' can be computed."""
    hist = store.get("fault_history") or []
    now = datetime.now().isoformat(timespec="seconds")
    if not faults:
        hist.append({"date": now, "vin": vin or "", "module": module, "code": "", "state": "OK", "event": event})
    for code, state in faults:
        hist.append({"date": now, "vin": vin or "", "module": module, "code": code, "state": state, "event": event})
    store.set("fault_history", hist[-5000:])


def record_clear(store: Store, vin: str | None, module: str):
    record_faults(store, vin, module, [("", "CLEARED")], "clear")


def summarize_history(store: Store) -> list[dict]:
    hist = store.get("fault_history") or []
    by: dict[tuple, dict] = {}
    clears: dict[str, list[str]] = {}
    for h in hist:
        if h["state"] == "CLEARED":
            clears.setdefault(h["module"], []).append(h["date"])
    for h in hist:
        if not h["code"]:
            continue
        k = (h["module"], h["code"])
        e = by.setdefault(k, {"module": h["module"], "code": h["code"], "first": h["date"], "last": h["date"],
                              "seen": 0, "state": h["state"]})
        e["seen"] += 1
        e["last"] = max(e["last"], h["date"])
        if h["date"] >= e["last"]:
            e["state"] = h["state"]
    for e in by.values():
        cl = [d for d in clears.get(e["module"], []) if d > e["first"]]
        e["cleared"] = len(cl)
        e["returned"] = any(e["last"] > d for d in cl)
    return sorted(by.values(), key=lambda e: e["last"], reverse=True)


# ---------------------------------------------------------------- trip recorder
@dataclass
class Trip:
    start: str
    end: str = ""
    duration_s: float = 0
    distance_km: float = 0
    max_speed: float = 0
    max_rpm: float = 0
    max_coolant: float | None = None
    max_iat: float | None = None
    max_oil: float | None = None
    idle_s: float = 0
    full_throttle: int = 0
    harsh_brakes: int = 0
    odo_start: float | None = None
    odo_end: float | None = None

    @property
    def avg_speed(self) -> float:
        moving = self.duration_s - self.idle_s
        return self.distance_km / (moving / 3600) if moving > 1 else 0.0


class TripRecorder:
    def __init__(self, store: Store):
        self.store = store
        self.trip: Trip | None = None
        self._last_t = None
        self._last_speed = None
        self._ft = False
        self._engine_off_since = None

    def feed(self, t: float, v: dict) -> None:
        rpm, spd = v.get(RPM), v.get(SPEED)
        if rpm is None and spd is None:
            return
        running = (rpm or 0) > 300
        if not self.trip:
            if running or (spd or 0) > 0:
                self.trip = Trip(start=datetime.now().isoformat(timespec="seconds"))
                self._last_t = t
            else:
                return
        tr = self.trip
        dt = max(0.0, min(5.0, t - (self._last_t or t)))
        self._last_t = t
        tr.duration_s += dt
        if spd is not None:
            tr.distance_km += spd * dt / 3600
            tr.max_speed = max(tr.max_speed, spd)
            if self._last_speed is not None and dt > 0:
                decel = (self._last_speed - spd) / dt
                if decel >= float(setting(self.store, "harsh_brake_kmh_s")) and self._last_speed > 20:
                    tr.harsh_brakes += 1
            self._last_speed = spd
            if running and spd < 1:
                tr.idle_s += dt
        if rpm is not None:
            tr.max_rpm = max(tr.max_rpm, rpm)
        th = v.get(THROTTLE)
        if th is not None:
            ft = th >= float(setting(self.store, "full_throttle_pct"))
            if ft and not self._ft:
                tr.full_throttle += 1
            self._ft = ft
        for key, attr in ((COOLANT, "max_coolant"), (IAT, "max_iat"), ("vag:01:11BD", "max_oil")):
            if v.get(key) is not None:
                cur = getattr(tr, attr)
                setattr(tr, attr, v[key] if cur is None else max(cur, v[key]))
        odo = v.get("vag:01:10E0")
        if odo:
            tr.odo_start = tr.odo_start or odo
            tr.odo_end = odo
        # engine off for 60 s → trip ends
        if not running and (spd or 0) < 1:
            self._engine_off_since = self._engine_off_since or t
            if t - self._engine_off_since > 60:
                self.finish()
        else:
            self._engine_off_since = None

    def finish(self) -> Trip | None:
        tr, self.trip = self.trip, None
        self._last_speed = None
        self._engine_off_since = None
        if not tr or tr.duration_s < 30:
            return None
        tr.end = datetime.now().isoformat(timespec="seconds")
        d = dict(tr.__dict__)
        d["avg_speed"] = tr.avg_speed
        trips = self.store.get("trips") or []
        trips.append(d)
        self.store.set("trips", trips[-1000:])
        return tr


# ---------------------------------------------------------------- battery monitor
class BatteryMonitor:
    """Tracks resting voltage (engine off), minimum while cranking, and charging voltage (engine running)."""

    def __init__(self, store: Store):
        self.store = store
        self.rest = None
        self.charging = None
        self.crank_min = None
        self._off_window: list[float] = []
        self._was_running = False

    def feed(self, volts: float, rpm: float | None) -> dict | None:
        running = (rpm or 0) > 400
        if not running:
            self._off_window = (self._off_window + [volts])[-40:]
            if (rpm or 0) == 0 and not self._was_running:
                self.rest = volts
        else:
            self.charging = volts
        event = None
        if running and not self._was_running and self._off_window:
            self.crank_min = min(self._off_window)
            event = {"date": datetime.now().isoformat(timespec="seconds"), "rest": self.rest,
                     "crank_min": self.crank_min}
            self._off_window = []
        if event:
            hist = self.store.get("battery") or []
            hist.append(event)
            self.store.set("battery", hist[-500:])
        self._was_running = running
        return event

    def verdict(self) -> list[tuple[str, str, str]]:
        """[(label, value, status ok|warn|bad)]"""
        out = []
        s = lambda k: float(setting(self.store, k))
        if self.rest is not None:
            out.append(("Resting voltage", f"{self.rest:.2f} V", "ok" if self.rest >= s("batt_rest_ok") else "warn"))
        if self.crank_min is not None:
            out.append(("Lowest while starting", f"{self.crank_min:.2f} V",
                        "ok" if self.crank_min >= s("batt_crank_ok") else "bad"))
        if self.charging is not None:
            ok = s("batt_charge_min") <= self.charging <= s("batt_charge_max")
            out.append(("Charging voltage", f"{self.charging:.2f} V", "ok" if ok else "bad"))
        return out


# ---------------------------------------------------------------- alerts
class AlertMonitor:
    def __init__(self, store: Store, emit):
        self.store = store
        self.emit = emit
        self._last: dict[str, float] = {}

    def _fire(self, key: str, text: str, level: str = "warn"):
        now = time.monotonic()
        if now - self._last.get(key, -1e9) >= 60:
            self._last[key] = now
            self.emit(level, text)

    def check(self, v: dict, volts: float | None, tiles: list[dict]):
        s = lambda k: float(setting(self.store, k))
        if v.get(COOLANT) is not None and v[COOLANT] >= s("alert_coolant"):
            self._fire("coolant", f"Coolant temperature high: {v[COOLANT]:.0f} °C", "bad")
        oil = v.get("vag:01:11BD")
        if oil is not None and oil >= s("alert_oil"):
            self._fire("oil", f"Oil temperature high: {oil:.0f} °C", "bad")
        if volts is not None:
            rpm = v.get(RPM) or 0
            if volts <= s("alert_volt_low") and rpm > 400:
                self._fire("vlow", f"Low system voltage while running: {volts:.1f} V", "bad")
            if volts >= s("alert_volt_high"):
                self._fire("vhigh", f"High system voltage: {volts:.1f} V (charging system?)", "bad")
        for t in tiles:
            key = t.get("key") or t.get("pid")
            w = t.get("warn")
            if w is not None and v.get(key) is not None and v[key] >= w:
                self._fire(f"tile:{key}", f"{t.get('label', key)} above warning: {v[key]:.1f}")

    def new_faults(self, codes: list[str], previous: set[str]) -> set[str]:
        cur = set(codes)
        for c in sorted(cur - previous):
            self._fire(f"dtc:{c}", f"New fault detected: {c}", "bad")
        return cur
