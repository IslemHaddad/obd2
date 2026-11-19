"""Generic OBD-II services: supported PIDs, live data, DTCs (per ECU), readiness, freeze frame, VIN."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import dtc_db, pids
from .elm import ELM327, ELMError


@dataclass
class DTC:
    code: str
    kind: str                    # Stored / Pending / Permanent

    @property
    def description(self) -> str:
        return dtc_db.describe(self.code)


@dataclass(frozen=True)
class ECU:
    request: str
    response: str

    @property
    def name(self) -> str:
        if self.request == "*":
            return "All Modules"
        return {"7E0": "Engine (ECM)", "18DA10F1": "Engine (ECM)",
                "7E1": "Transmission (TCM)", "18DA18F1": "Transmission (TCM)"}.get(self.request, f"Module {self.response}")


BROADCAST = ECU("*", "*")


@dataclass
class ModuleReport:
    ecu: ECU
    dtcs: list[DTC] = field(default_factory=list)

    @property
    def faulty(self) -> bool:
        return bool(self.dtcs)


@dataclass
class Readiness:
    mil_on: bool
    dtc_count: int
    monitors: list[tuple[str, bool, bool]]     # name, supported, complete


@dataclass
class MonitorTest:
    mid: int                 # monitor ID
    tid: int                 # test ID
    value: float
    low: float
    high: float
    unit: str = ""

    @property
    def passed(self) -> bool:
        return self.low <= self.value <= self.high

    @property
    def name(self) -> str:
        return _OBD_MID.get(self.mid, f"Monitor ${self.mid:02X}") + f" · test ${self.tid:02X}"


# Mode 06 unit-and-scaling IDs (SAE J1979 Appendix); value = raw * scale.
_OBD_UAS = {
    0x01: (1.0, ""), 0x02: (0.1, ""), 0x03: (0.01, ""), 0x04: (0.001, ""),
    0x05: (0.0000305, ""), 0x06: (0.000305, ""), 0x07: (0.25, "rpm"), 0x08: (0.01, "km/h"),
    0x09: (1.0, "km/h"), 0x0A: (0.122, "mV"), 0x0B: (0.001, "V"), 0x0C: (0.01, "V"),
    0x10: (1.0, "ms"), 0x12: (0.1, "s"), 0x18: (1.0, "Pa"), 0x19: (0.25, "Pa"),
    0x1A: (1.0, "kPa"), 0x22: (0.1, "°C"), 0x27: (0.1, "%"), 0x29: (0.0000305, "%"),
    0x2A: (0.000305, "%"), 0x30: (1.0, "count"), 0x31: (1.0, "km"),
}
_OBD_MID = {
    0x01: "O2 Sensor Mon. B1S1", 0x02: "O2 Sensor Mon. B1S2", 0x05: "O2 Sensor Mon. B2S1",
    0x06: "O2 Sensor Mon. B2S2", 0x21: "Catalyst Bank 1", 0x22: "Catalyst Bank 2",
    0x31: "EGR Monitor", 0x39: "EVAP Monitor", 0x3B: "EVAP (0.090\")",
    0x41: "Oxygen Sensor Heater B1", 0x42: "Oxygen Sensor Heater B2",
    0xA1: "Misfire General", 0xA2: "Misfire Cyl.1", 0xA3: "Misfire Cyl.2",
    0xA4: "Misfire Cyl.3", 0xA5: "Misfire Cyl.4",
}


def _index_after(d: list[int], mode: int, pid: int):
    for i in range(len(d) - 1):
        if d[i] == mode and d[i + 1] == pid:
            return i + 2
    return None


class OBD:
    def __init__(self, elm: ELM327):
        self.elm = elm
        self.single_ecu = False        # set after discovery when only one ECU answers mode 01

    # ---------- PIDs ----------
    def supported_pids(self) -> set[int]:
        out: set[int] = set()
        base = 0
        while True:
            try:
                d = self.elm.request(f"01{base:02X}")
            except ELMError:
                break
            i = _index_after(d, 0x41, base)
            if i is None or len(d) < i + 4:
                break
            mask = d[i] << 24 | d[i + 1] << 16 | d[i + 2] << 8 | d[i + 3]
            for bit in range(32):
                if mask & (1 << (31 - bit)):
                    out.add(base + bit + 1)
            if base + 0x20 not in out or base >= 0xE0:
                break
            base += 0x20
        return out

    def read(self, ids: list[int]) -> dict[int, float]:
        out: dict[int, float] = {}
        chunk = 6 if self.elm.is_can else 1
        for k in range(0, len(ids), chunk):
            group = ids[k:k + chunk]
            cmd = "01" + "".join(f"{p:02X}" for p in group)
            if self.elm.profile.fast and self.single_ecu:
                cmd += "1"            # STN: return after the first ECU answers instead of waiting for timeout
            try:
                d = self.elm.request(cmd)
            except ELMError:
                continue
            i = 0
            while i < len(d):
                if d[i] != 0x41:
                    i += 1
                    continue
                i += 1
                while i < len(d) and d[i] != 0x41:
                    pid = d[i]
                    n = pids.length(pid)
                    if n is None or i + 1 + n > len(d):
                        i = len(d)
                        break
                    p = pids.BY_ID.get(pid)
                    if p and pid not in out:
                        out[pid] = p.decode(d[i + 1:i + 1 + n])
                    i += 1 + n
        return out

    # ---------- DTCs ----------
    def dtcs(self, mode: str, kind: str) -> list[DTC]:
        resp = int(mode, 16) + 0x40
        raw: list[int] = []
        try:
            if self.elm.is_can:
                d = self.elm.request(mode, 4)
                i = 0
                while i < len(d):
                    if d[i] == resp and i + 1 < len(d):
                        n = d[i + 1]
                        raw += d[i + 2:i + 2 + n * 2]
                        i += 2 + n * 2
                    else:
                        i += 1
            else:
                for l in self.elm.request_lines(mode, 4):
                    if l and l[0] == resp:
                        raw += l[1:]
        except ELMError:
            return []
        seen, out = set(), []
        for j in range(0, len(raw) - 1, 2):
            a, b = raw[j], raw[j + 1]
            if a == 0 and b == 0:
                continue
            c = dtc_db.decode(a, b)
            if c not in seen:
                seen.add(c)
                out.append(DTC(c, kind))
        return out

    def all_dtcs(self) -> list[DTC]:
        return self.dtcs("03", "Stored") + self.dtcs("07", "Pending") + self.dtcs("0A", "Permanent")

    def clear(self) -> None:
        self.elm.send("04", 5)

    # ---------- per-ECU ----------
    def _is29(self) -> bool:
        return self.elm.protocol in (7, 9)

    def functional_header(self) -> str:
        return "18DB33F1" if self._is29() else "7DF"

    def discover_ecus(self) -> list[ECU]:
        if not self.elm.is_can:
            return [BROADCAST]
        wide = self._is29()
        with self.elm.lock:
            try:
                self.elm.send("ATH1")
                lines = self.elm.send("0100", 3)
            except ELMError:
                lines = []
            finally:
                try:
                    self.elm.send("ATH0")
                except ELMError:
                    pass
        seen: list[str] = []
        for l in lines:
            h = l[:8 if wide else 3]
            try:
                v = int(h, 16)
            except ValueError:
                continue
            ok = h.startswith("18DAF1") if wide else 0x7E8 <= v <= 0x7EF
            if ok and h not in seen:
                seen.append(h)
        ecus = [ECU("18DA" + r[-2:] + "F1", r) if wide else ECU(f"{int(r, 16) - 8:03X}", r) for r in sorted(seen)]
        return ecus or [BROADCAST]

    def _on(self, ecu: ECU, fn):
        if ecu == BROADCAST:
            return fn()
        with self.elm.lock:
            self.elm.send("ATSH" + ecu.request)
            try:
                return fn()
            finally:
                try:
                    self.elm.send("ATSH" + self.functional_header())
                except ELMError:
                    pass

    def dtcs_for(self, ecu: ECU) -> list[DTC]:
        try:
            return self._on(ecu, self.all_dtcs)
        except ELMError:
            return []

    def clear_for(self, ecu: ECU) -> None:
        self._on(ecu, self.clear)

    # ---------- readiness / freeze / info ----------
    def readiness(self) -> Readiness | None:
        try:
            d = self.elm.request("0101")
        except ELMError:
            return None
        i = _index_after(d, 0x41, 0x01)
        if i is None or len(d) < i + 4:
            return None
        A, B, C, D = d[i:i + 4]
        diesel = bool(B & 0x08)
        m = [("Misfire", bool(B & 1), not B & 0x10), ("Fuel System", bool(B & 2), not B & 0x20),
             ("Components", bool(B & 4), not B & 0x40)]
        names = (["NMHC Catalyst", "NOx/SCR", "", "Boost Pressure", "", "Exhaust Gas Sensor", "PM Filter", "EGR/VVT"]
                 if diesel else
                 ["Catalyst", "Heated Catalyst", "Evaporative", "Secondary Air", "A/C Refrigerant",
                  "O2 Sensor", "O2 Heater", "EGR/VVT"])
        for bit, n in enumerate(names):
            if n:
                m.append((n, bool(C & (1 << bit)), not D & (1 << bit)))
        return Readiness(bool(A & 0x80), A & 0x7F, m)

    def freeze_frame(self, supported: set[int]) -> dict[int, float]:
        out = {}
        for p in pids.ALL:
            if supported and p.id not in supported:
                continue
            try:
                d = self.elm.request(f"02{p.id:02X}00")
            except ELMError:
                continue
            i = _index_after(d, 0x42, p.id)
            if i is not None and len(d) >= i + 1 + p.nbytes:
                out[p.id] = p.decode(d[i + 1:i + 1 + p.nbytes])
        return out

    # ---------- Mode 06: on-board monitor test results ----------
    def supported_mids(self) -> set[int]:
        """MID 00/20/40/... bitmasks list which monitor IDs the ECU supports."""
        out: set[int] = set()
        for base in range(0x00, 0xA0, 0x20):
            try:
                d = self.elm.request(f"06{base:02X}")
            except ELMError:
                break
            i = _index_after(d, 0x46, base)
            if i is None or len(d) < i + 4:
                break
            mask = (d[i] << 24) | (d[i + 1] << 16) | (d[i + 2] << 8) | d[i + 3]
            for bit in range(32):
                if mask & (1 << (31 - bit)):
                    out.add(base + bit + 1)
            if not mask & 1:            # lowest bit flags "next block supported"
                break
        return out

    def monitor_tests(self, mids: set[int] | None = None) -> list["MonitorTest"]:
        """Decode Mode 06 results: each test's value vs min/max, with pass/fail."""
        mids = mids if mids is not None else self.supported_mids()
        out: list[MonitorTest] = []
        for mid in sorted(m for m in mids if m % 0x20):
            try:
                d = self.elm.request(f"06{mid:02X}")
            except ELMError:
                continue
            if 0x46 not in d:
                continue
            j = d.index(0x46) + 1       # groups: MID TID UAS val(2) min(2) max(2)
            while j + 8 < len(d):
                g_mid, tid, uas = d[j], d[j + 1], d[j + 2]
                if g_mid == 0 or g_mid % 0x20 == 0:
                    break
                val = (d[j + 3] << 8) | d[j + 4]
                lo = (d[j + 5] << 8) | d[j + 6]
                hi = (d[j + 7] << 8) | d[j + 8]
                sc, unit = _OBD_UAS.get(uas, (1.0, ""))
                out.append(MonitorTest(g_mid, tid, val * sc, lo * sc, hi * sc, unit))
                j += 9
        return out

    def mode09(self, pid: int) -> str | None:
        try:
            d = self.elm.request(f"09{pid:02X}", 4)
        except ELMError:
            return None
        i = _index_after(d, 0x49, pid)
        if i is None:
            return None
        s = bytes(b for b in d[i:] if 0x20 <= b <= 0x7E).decode().strip()
        return s or None
