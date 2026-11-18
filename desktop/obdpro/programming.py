"""Programming (coding) readiness: checks conditions and probes which modules accept coding writes.
The probe writes each module's CURRENT coding back unchanged (no change to the car), and reads it again to confirm."""
from __future__ import annotations

from dataclasses import dataclass, field

from .elm import ELMError, to_hex
from .vag import MODULES, NRC, VAG, _negative


@dataclass
class Check:
    name: str
    status: str          # ok | warn | fail | info
    detail: str


@dataclass
class ModuleCoding:
    address: str
    name: str
    present: bool
    readable: bool = False
    verdict: str = ""        # codable | login | read-only | not-supported | absent
    detail: str = ""
    coding: str = ""


@dataclass
class Readiness:
    checks: list[Check] = field(default_factory=list)
    modules: list[ModuleCoding] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not any(c.status == "fail" for c in self.checks)


def conditions(elm, obd) -> list[Check]:
    out = []
    p = elm.profile
    out.append(Check("Adapter", "ok" if p.is_stn else "warn",
                     f"{p.chip}. " + ("Suitable for coding." if p.is_stn else
                                      "Clone chip: fine for coding, NOT suitable for firmware flashing.")))
    v = obd.read([0x0C, 0x42])
    rpm, volts = v.get(0x0C), v.get(0x42)
    if volts is None:
        volts = elm.battery_voltage()
    if rpm is None:
        out.append(Check("Ignition", "warn", "Engine speed not readable — make sure ignition is ON."))
    elif rpm > 0:
        out.append(Check("Engine", "fail", f"Engine is running ({rpm:.0f} rpm). Switch the engine OFF, keep ignition ON."))
    else:
        out.append(Check("Engine", "ok", "Engine off, ignition on."))
    if volts is None:
        out.append(Check("Battery", "warn", "Voltage not readable."))
    elif volts < 12.0:
        out.append(Check("Battery", "fail", f"{volts:.1f} V — too low. Connect a charger before coding."))
    elif volts < 12.4:
        out.append(Check("Battery", "warn", f"{volts:.1f} V — low-ish. A charger is recommended for longer sessions."))
    else:
        out.append(Check("Battery", "ok", f"{volts:.1f} V"))
    proto = elm.protocol_name
    out.append(Check("Car network", "ok" if elm.protocol in (6, 8) else "fail",
                     proto + ("" if elm.protocol in (6, 8) else " — module coding needs CAN 11-bit.")))
    return out


def probe_module(vag: VAG, m) -> ModuleCoding:
    r = ModuleCoding(m.address, m.name, False)
    with vag.channel(m):
        try:
            coding = vag.read_did(0x0600)
        except ELMError as e:
            msg = str(e)
            r.present = "NO DATA" not in msg.upper()
            r.verdict = "not-supported" if r.present else "absent"
            r.detail = "Module has no long coding (DID 0600)." if r.present else "Not fitted / no response."
            return r
        r.present, r.readable, r.coding = True, True, to_hex(coding)
        try:
            vag.session(0x03)
        except ELMError as e:
            r.verdict, r.detail = "read-only", f"Extended session refused: {e}"
            return r
        try:
            d = vag.elm.request_uds(f"2E0600{to_hex(coding)}", 5)
            neg = _negative(d, 0x2E)
            if neg is None:
                back = vag.read_did(0x0600)
                ok = back == coding
                r.verdict = "codable" if ok else "read-only"
                r.detail = "Accepts coding without login (same value written back, unchanged)." if ok else \
                    "Write acknowledged but read-back differs — do not code this module."
            elif neg.nrc in (0x33, 0x24, 0x35):
                r.verdict = "login"
                r.detail = f"Needs the manufacturer security login ({NRC.get(neg.nrc, hex(neg.nrc))})."
            elif neg.nrc == 0x22:
                r.verdict = "read-only"
                r.detail = "Conditions not correct (engine off? ignition on? speed 0?)."
            else:
                r.verdict = "read-only"
                r.detail = f"Refused: {NRC.get(neg.nrc, hex(neg.nrc))}."
        except ELMError as e:
            r.verdict, r.detail = "read-only", str(e)
        finally:
            try:
                vag.session(0x01)
            except ELMError:
                pass
    return r


def check(elm, obd, vag, family: str, progress=lambda f, msg: None) -> Readiness:
    out = Readiness()
    with elm.lock:
        progress(0.02, "Checking conditions")
        out.checks = conditions(elm, obd)
        if family != "vag":
            out.checks.append(Check("Coding", "info", "Module coding in this app is VW Group (SEAT/VW/Audi/Škoda) only."))
            return out
        if not vag.supported:
            return out
        for i, m in enumerate(MODULES):
            progress(0.05 + 0.95 * i / len(MODULES), f"{m.address} · {m.name}")
            res = probe_module(vag, m)
            if res.verdict != "absent":
                out.modules.append(res)
    n = sum(1 for m in out.modules if m.verdict == "codable")
    out.checks.append(Check("Codable modules", "ok" if n else "info",
                            f"{n} module(s) accept coding without login." if n else
                            "No module accepts coding without the manufacturer login."))
    return out
