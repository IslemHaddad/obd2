"""VW Group UDS (ISO 14229) over ELM327: per-module faults, clear, identification, live DIDs,
long coding, adaptations, output tests (2F / 31) and basic settings (31 01/03/02)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import catalog, dtc_db
from .elm import ELM327, ELMError, NoData, to_hex

NRC = {
    0x10: "General reject", 0x11: "Service not supported", 0x12: "Sub-function not supported",
    0x13: "Incorrect message length", 0x22: "Conditions not correct", 0x24: "Request sequence error",
    0x31: "Request out of range", 0x33: "Security access denied", 0x35: "Invalid key",
    0x72: "General programming failure", 0x7E: "Not supported in active session",
    0x7F: "Service not supported in active session",
}

FTB = {
    0x00: "No sub-type", 0x01: "General electrical failure", 0x02: "General signal failure",
    0x11: "Short to ground", 0x12: "Short to battery", 0x13: "Open circuit",
    0x14: "Short to ground or open", 0x15: "Short to battery or open",
    0x16: "Voltage below threshold", 0x17: "Voltage above threshold", 0x1C: "Voltage out of range",
    0x29: "Signal invalid", 0x31: "No signal", 0x54: "Missing calibration", 0x55: "Not configured",
    0x62: "Signal compare failure", 0x64: "Signal plausibility failure", 0x87: "Missing message",
    0x88: "Bus off", 0x96: "Component internal failure", 0x98: "Over temperature",
}

STANDARD_DIDS = [
    (0xF187, "Spare Part Number"), (0xF189, "Software Version"), (0xF191, "Hardware Number"),
    (0xF197, "System Name"), (0xF18C, "Serial Number"), (0xF19E, "ASAM/ODX File"),
    (0xF1A2, "ODX Version"), (0xF1A3, "Hardware Version"), (0xF190, "VIN"), (0x0600, "Coding"),
]


class UDSNegative(ELMError):
    def __init__(self, sid: int, nrc: int):
        self.sid, self.nrc = sid, nrc
        super().__init__(f"Module rejected 0x{sid:02X}: {NRC.get(nrc, f'NRC 0x{nrc:02X}')}")


@dataclass(frozen=True)
class Module:
    address: str
    name: str
    request: str
    response: str
    category: str
    x: float
    y: float

    @property
    def color(self) -> str:
        return catalog.CATEGORY_COLOR[self.category]


MODULES = [Module(*m) for m in catalog.MODULES]
MODULE_BY_ADDR = {m.address: m for m in MODULES}


# ISO 14229 DTC status bits that mean "this is a real fault" (not just "test not run yet").
FAULT_MASK = 0x2F   # testFailed | testFailedThisCycle | pending | confirmed | testFailedSinceLastClear


@dataclass
class Fault:
    dtc: str
    ftb: int
    status: int
    raw: int = 0               # 3-byte UDS DTC as integer
    powertrain: bool = True    # SAE P-code meaning applies (engine / gearbox)

    @property
    def code(self) -> str:
        if self.powertrain:
            return f"{self.dtc} {self.ftb:02X}"
        return f"{self.raw:06X}"

    @property
    def active(self) -> bool:
        return bool(self.status & 0x01)

    @property
    def state(self) -> str:
        if self.status & 0x01:
            return "Active"
        if self.status & 0x08:
            return "Stored"
        if self.status & 0x04:
            return "Pending"
        return "Intermittent"

    @property
    def description(self) -> str:
        if self.powertrain:
            return dtc_db.describe(self.dtc)
        return f"Module-specific fault (SAE form {self.dtc}-{self.ftb:02X})"

    @property
    def detail(self) -> str:
        return FTB.get(self.ftb, f"Fault type {self.ftb:02X}")


@dataclass
class Report:
    module: Module
    present: bool
    faults: list[Fault] = field(default_factory=list)
    part: str | None = None
    system: str | None = None

    @property
    def faulty(self) -> bool:
        return bool(self.faults)


def _positive(d: list[int], sid: int, sub: int | None = None):
    for i in range(len(d)):
        if d[i] == sid and (sub is None or (i + 1 < len(d) and d[i + 1] == sub)):
            return d[i:]
    return None


def _negative(d: list[int], sid: int):
    for i in range(len(d) - 2):
        if d[i] == 0x7F and d[i + 1] == sid and d[i + 2] != 0x78:
            return UDSNegative(sid, d[i + 2])
    return None


class VAG:
    """All methods assume the caller holds `elm.lock` (use `with vag.channel(module):`)."""

    def __init__(self, elm: ELM327):
        self.elm = elm

    @property
    def supported(self) -> bool:
        return self.elm.protocol in (6, 8)

    # ---------- channel ----------
    class _Channel:
        def __init__(self, vag: "VAG", m: Module):
            self.vag, self.m = vag, m

        def __enter__(self):
            self.vag.elm.lock.acquire()
            self.vag.m_req, self.vag.m_resp = self.m.request, self.m.response
            for c in ("ATSH" + self.m.request, "ATCRA" + self.m.response, "ATFCSH" + self.m.request,
                      "ATFCSD300000", "ATFCSM1"):
                try:
                    self.vag.elm.send(c, 1)
                except ELMError:
                    pass
            return self.vag

        def __exit__(self, *exc):
            for c in ("ATFCSM0", "ATCRA", "ATSH7DF"):
                try:
                    self.vag.elm.send(c, 1)
                except ELMError:
                    pass
            self.vag.elm.lock.release()

    def channel(self, m: Module) -> "_Channel":
        return VAG._Channel(self, m)

    # ---------- primitives ----------
    def uds(self, cmd: str, pos_sid: int, req_sid: int, timeout: float = 3.0) -> list[int]:
        d = self.elm.request_uds(cmd, timeout)
        p = _positive(d, pos_sid)
        if p is not None:
            return p
        raise _negative(d, req_sid) or NoData()

    def read_did(self, did: int, timeout: float = 1.0) -> list[int]:
        d = self.elm.request_uds(f"22{did:04X}", timeout, pending_wait=3)
        p = _positive(d, 0x62, did >> 8)
        if p is not None and len(p) >= 3 and p[2] == did & 0xFF:
            return p[3:]
        raise _negative(d, 0x22) or NoData()

    def write_did(self, did: int, data: list[int]) -> None:
        d = self.elm.request_uds(f"2E{did:04X}{to_hex(data)}", 5)
        if _positive(d, 0x6E, did >> 8) is None:
            raise _negative(d, 0x2E) or NoData()

    def session(self, t: int) -> None:
        d = self.elm.request_uds(f"10{t:02X}", 1.5)
        if _positive(d, 0x50, t) is None:
            raise _negative(d, 0x10) or NoData()

    def tester_present(self) -> None:
        try:
            self.elm.request("3E00", 0.5)
        except ELMError:
            pass

    def _ascii(self, did: int) -> str | None:
        try:
            p = self.read_did(did)
        except ELMError:
            return None
        while p and p[-1] in (0x00, 0xAA, 0xFF):
            p = p[:-1]
        s = bytes(b for b in p if 0x20 <= b <= 0x7E).decode().strip()
        return s or None

    # ---------- faults ----------
    def report(self, m: Module) -> Report:
        with self.channel(m):
            # Ask only for real faults: listing every supported DTC (mask FF) can be hundreds of
            # records, which cheap ELM327 clones truncate.
            try:
                d = self.elm.request_uds(f"1902{FAULT_MASK:02X}", 2)
            except NoData:
                return Report(m, False)
            except ELMError:
                return Report(m, False)
            r = _positive(d, 0x59, 0x02)
            if r is None:
                neg = _negative(d, 0x19)
                if neg is None:
                    return Report(m, False)
                d = self.elm.request_uds("1902FF", 2)        # module rejects the mask → fall back
                r = _positive(d, 0x59, 0x02)
                if r is None:
                    return Report(m, False)
            rec = r[3:]
            faults: list[Fault] = []
            for j in range(0, len(rec) - 3, 4):
                a, b, c, st = rec[j:j + 4]
                if (a | b | c) and st & FAULT_MASK:
                    f = Fault(dtc_db.decode(a, b), c, st, a << 16 | b << 8 | c, m.category == "powertrain")
                    if all(f.code != x.code for x in faults):
                        faults.append(f)
            return Report(m, True, faults, self._ascii(0xF187), self._ascii(0xF197))

    def clear(self, m: Module) -> None:
        with self.channel(m):
            if self._try_clear():
                return
            try:
                self.session(0x03)
            except ELMError:
                pass
            ok = self._try_clear()
            try:
                self.session(0x01)
            except ELMError:
                pass
            if not ok and m.category == "powertrain":
                ok = self._try_obd_clear()       # engine/gearbox ECUs often only accept SAE mode 04
            if not ok:
                raise ELMError(f"{m.name} refused to clear codes" + (f" ({self._last_nrc})" if self._last_nrc else ""))

    _last_nrc = ""

    def _try_clear(self) -> bool:
        try:
            d = self.elm.request_uds("14FFFFFF", 3, pending_wait=8)
            if _positive(d, 0x54) is not None:
                return True
            n = _negative(d, 0x14)
            self._last_nrc = str(n) if n else ""
            return False
        except ELMError:
            return False

    def _try_obd_clear(self) -> bool:
        """SAE J1979 mode 04: first physically to this ECU, then functionally (7DF) — some VAG engine ECUs
        only accept the functional request."""
        try:
            d = self.elm.request_uds("04", 5, pending_wait=8)
            if 0x44 in d:
                return True
            for c in ("ATFCSM0", "ATCRA", "ATSH7DF"):
                self.elm.send(c, 1)
            try:
                d2 = self.elm.request_uds("04", 5, pending_wait=8)
            finally:
                for c in ("ATSH" + self.m_req, "ATCRA" + self.m_resp, "ATFCSM1"):
                    try:
                        self.elm.send(c, 1)
                    except ELMError:
                        pass
            if 0x44 in d2:
                return True
            d = d2
            n = _negative(d, 0x04)
            if n and n.nrc == 0x22:
                self._last_nrc = "conditions not correct — switch the ENGINE OFF, keep ignition ON"
            elif n:
                self._last_nrc = str(n)
            return False
        except ELMError as e:
            self._last_nrc = str(e)
            return False

    # ---------- identification ----------
    def identification(self, m: Module) -> list[tuple[str, str]]:
        out = []
        with self.channel(m):
            for did, name in STANDARD_DIDS:
                try:
                    p = self.read_did(did)
                except ELMError:
                    continue
                trimmed = list(p)
                while trimmed and trimmed[-1] in (0x00, 0xAA, 0xFF, 0x20):   # VAG pads with AA/00/FF
                    trimmed.pop()
                if trimmed and all(0x20 <= b <= 0x7E for b in trimmed):
                    out.append((name, bytes(trimmed).decode().strip()))
                else:
                    out.append((name, to_hex(p)))
        return out

    # ---------- coding / adaptation ----------
    def read_coding(self, m: Module) -> list[int]:
        with self.channel(m):
            return self.read_did(0x0600)

    def write_did_verified(self, m: Module, did: int, data: list[int]) -> list[int]:
        with self.channel(m):
            try:
                self.session(0x03)
                self.write_did(did, data)
                return self.read_did(did)
            finally:
                try:
                    self.session(0x01)
                except ELMError:
                    pass

    def read_one(self, m: Module, did: int) -> list[int]:
        with self.channel(m):
            return self.read_did(did)

    def scan_dids(self, m: Module, start: int, end: int, progress=None, stop=None) -> list[tuple[int, list[int]]]:
        found = []
        with self.channel(m):
            total = max(1, end - start + 1)
            for i, did in enumerate(range(start, end + 1)):
                if stop and stop():
                    break
                try:
                    found.append((did, self.read_did(did, 0.4)))
                except ELMError:
                    pass
                if progress and i % 8 == 0:
                    progress(i / total, len(found))
        return found

    # ---------- output tests ----------
    def run_output_test(self, m: Module, t: dict, stop, status) -> None:
        """t: {method: 'io'|'routine', id: int, data: hex, duration: s}."""
        io = t["method"] == "io"
        idh, data = f"{t['id']:04X}", t.get("data", "")
        start = f"2F{idh}03{data}" if io else f"3101{idh}{data}"
        stop_cmd = f"2F{idh}00" if io else f"3102{idh}"
        pos, req = (0x6F, 0x2F) if io else (0x71, 0x31)
        with self.channel(m):
            try:
                self.session(0x03)
                resp = self.uds(start, pos, req)
                end = time.monotonic() + float(t.get("duration", 10))
                last_tp = time.monotonic()
                while not stop() and time.monotonic() < end:
                    status(f"Running · {end - time.monotonic():.0f}s left · {to_hex(resp, ' ')}")
                    if time.monotonic() - last_tp >= 2:
                        self.tester_present()
                        last_tp = time.monotonic()
                    time.sleep(0.25)
            finally:
                status("Stopping…")
                try:
                    self.uds(stop_cmd, pos, req)
                except ELMError:
                    pass
                try:
                    self.session(0x01)
                except ELMError:
                    pass

    # ---------- basic settings ----------
    def run_basic_setting(self, m: Module, b: dict, stop, update, watch_defs=()) -> str:
        """Returns final phase: done / failed / stopped / timedOut."""
        rid = f"{b['routine']:04X}"
        started = False
        final = "stopped"
        with self.channel(m):
            try:
                self.session(0x03)
                first = self.uds(f"3101{rid}{b.get('data', '')}", 0x71, 0x31, 5)
                started = True
                update(phase="running", result=to_hex(first[4:], " "))
                t0 = time.monotonic()
                while not stop():
                    el = time.monotonic() - t0
                    update(elapsed=el)
                    if el >= float(b.get("timeout", 60)):
                        final = "timedOut"
                        break
                    try:
                        r = self.uds(f"3103{rid}", 0x71, 0x31, 1.5)[4:]
                        update(result=to_hex(r, " "))
                        o = b.get("done_offset")
                        if o is not None and o < len(r):
                            if b.get("fail_value") is not None and r[o] == b["fail_value"]:
                                final = "failed"
                                break
                            if r[o] == b.get("done_value", 0):
                                final = "done"
                                break
                    except ELMError:
                        self.tester_present()
                    for w in watch_defs:
                        try:
                            update(watch={w["id"]: decode_measurement(w, self.read_did(w["did"], 0.8))})
                        except ELMError:
                            update(watch={w["id"]: "—"})
                    time.sleep(0.4)
            finally:
                if started and final not in ("done", "failed"):
                    update(phase="stopping")
                    try:
                        self.uds(f"3102{rid}", 0x71, 0x31)
                    except ELMError:
                        pass
                try:
                    self.session(0x01)
                except ELMError:
                    pass
        return final


# ---------- measurement decoding (shared by live data / adaptations / basic settings) ----------
def numeric(defn: dict, p: list[int]) -> float | None:
    off, n = int(defn.get("offset", 0)), int(defn.get("length", 2))
    if defn.get("kind", "number") != "number" or off + n > len(p):
        return None
    raw = 0
    for b in p[off:off + n]:
        raw = raw << 8 | b
    if defn.get("signed") and raw & (1 << (n * 8 - 1)):
        raw -= 1 << (n * 8)
    return raw * float(defn.get("scale", 1)) + float(defn.get("add", 0))


def decode_measurement(defn: dict, p: list[int]) -> str:
    k = defn.get("kind", "number")
    if k == "hex":
        return to_hex(p, " ")
    if k == "ascii":
        return bytes(b for b in p if 0x20 <= b <= 0x7E).decode()
    v = numeric(defn, p)
    if v is None:
        return "—"
    s = f"{v:.0f}" if abs(v) >= 100 or v == int(v) else f"{v:.2f}"
    return f"{s} {defn.get('unit', '')}".strip()


def patch_number(defn: dict, p: list[int], value: float) -> list[int] | None:
    off, n = int(defn.get("offset", 0)), int(defn.get("length", 1))
    scale = float(defn.get("scale", 1))
    if off + n > len(p) or scale == 0:
        return None
    raw = round((value - float(defn.get("add", 0))) / scale)
    if raw < 0 or raw >= 1 << (n * 8):
        return None
    out = list(p)
    for i in range(off + n - 1, off - 1, -1):
        out[i] = raw & 0xFF
        raw >>= 8
    return out
