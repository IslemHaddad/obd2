"""Hyundai / Kia support: module discovery (11-bit CAN, response = request + 8), DTC read/clear over UDS
(0x19 / 0x14) with KWP2000-on-CAN fallback (0x18 / 0x14), identification.

Module names for common addresses are best-effort labels; anything else is shown by its CAN ID.
Discovery is authoritative: only modules that actually answer on the car are used."""
from __future__ import annotations

from .elm import ELM327, ELMError, NoData
from .vag import Fault, Module, Report, VAG, _negative, _positive
from . import dtc_db

# request id → (name, category, x, y on the top-view diagram)
KNOWN = {
    "7E0": ("Engine (ECU)", "powertrain", 0.50, 0.14),
    "7E1": ("Transmission (TCU)", "powertrain", 0.50, 0.27),
    "7D1": ("ABS / ESC", "chassis", 0.27, 0.20),
    "7D2": ("Airbag (SRS)", "safety", 0.50, 0.50),
    "7D4": ("Power steering (MDPS)", "chassis", 0.66, 0.24),
    "7C6": ("Instrument cluster", "electronics", 0.33, 0.35),
    "7A0": ("Body control (BCM)", "electronics", 0.20, 0.42),
    "770": ("Integrated body unit (IPM)", "electronics", 0.22, 0.45),
    "7B3": ("Air conditioning", "electronics", 0.50, 0.41),
    "7C4": ("Smart key / immobilizer", "electronics", 0.62, 0.45),
    "7A5": ("Tyre pressure (TPMS)", "chassis", 0.50, 0.80),
    "780": ("Audio / head unit", "electronics", 0.50, 0.34),
}

PROBE_RANGE = list(range(0x700, 0x7E8))         # 7DF (functional) and 7E8+ (responses) excluded below


def module_for(req: str) -> Module:
    name, cat, x, y = KNOWN.get(req, (f"Module {req}", "electronics", 0.5 + ((int(req, 16) * 37) % 50 - 25) / 100,
                                      0.6 + ((int(req, 16) * 53) % 30) / 100))
    return Module(req, name, req, f"{int(req, 16) + 8:03X}", cat, x, y)


class Hyundai(VAG):
    """Reuses VAG's channel handling (ATSH/ATCRA/flow-control); different discovery and DTC services."""

    @property
    def supported(self) -> bool:
        return self.elm.protocol in (6, 8)

    def discover(self, progress=None) -> list[Module]:
        """Send TesterPresent (3E 00) to every 11-bit physical address and keep the ones that answer on +8."""
        found: list[Module] = []
        ids = [i for i in PROBE_RANGE if i != 0x7DF]
        with self.elm.lock:
            try:
                self.elm.send("ATH1", 1)
                for n, rid in enumerate(ids):
                    if progress and n % 8 == 0:
                        progress(n / len(ids), len(found))
                    try:
                        self.elm.send(f"ATSH{rid:03X}", 1)
                        lines = self.elm.send("3E00", 0.3)
                    except ELMError:
                        continue
                    want = f"{rid + 8:03X}"
                    if any(l.replace(" ", "").upper().startswith(want) for l in lines):
                        found.append(module_for(f"{rid:03X}"))
            finally:
                for c in ("ATH0", "ATSH7DF"):
                    try:
                        self.elm.send(c, 1)
                    except ELMError:
                        pass
        return found

    # ---- faults
    def report(self, m: Module) -> Report:
        with self.channel(m):
            faults: list[Fault] = []
            ok = False
            # UDS first
            try:
                d = self.elm.request_uds("1902FF", 2)
                r = _positive(d, 0x59, 0x02)
                if r is not None:
                    ok = True
                    rec = r[3:]
                    for j in range(0, len(rec) - 3, 4):
                        a, b, c, st = rec[j:j + 4]
                        if (a | b) and st & 0x2F:
                            faults.append(Fault(dtc_db.decode(a, b), c, st, a << 16 | b << 8 | c, True))
            except ELMError:
                pass
            if not ok:
                # KWP2000: 18 02 FF 00 → 58 n [hi lo status]*n
                try:
                    d = self.elm.request_uds("1802FF00", 2)
                    r = _positive(d, 0x58)
                    if r is not None and len(r) >= 2:
                        ok = True
                        rec = r[2:]
                        for j in range(0, len(rec) - 2, 3):
                            a, b, st = rec[j:j + 3]
                            if (a | b) and st:
                                # KWP status: bit6 = warning lamp, bits 5/6 "present"; treat bit5 as active
                                faults.append(Fault(dtc_db.decode(a, b), 0, 0x09 if st & 0x20 else 0x08,
                                                    a << 16 | b << 8, True))
                except ELMError:
                    pass
            if not ok:
                return Report(m, False)
            uniq = {}
            for f in faults:
                uniq.setdefault(f.code, f)
            return Report(m, True, list(uniq.values()), self._ascii_any(0xF187, 0x87), self._ascii_any(0xF18C, 0x8C))

    def _ascii_any(self, uds_did: int, kwp_lid: int) -> str | None:
        s = self._ascii(uds_did)
        if s:
            return s
        try:
            d = self.elm.request_uds(f"1A{kwp_lid:02X}", 1)
            r = _positive(d, 0x5A, kwp_lid)
            if r:
                t = bytes(b for b in r[2:] if 0x20 <= b <= 0x7E).decode().strip()
                return t or None
        except ELMError:
            pass
        return None

    def clear(self, m: Module) -> None:
        with self.channel(m):
            for cmd, pos in (("14FFFFFF", 0x54), ("14FF00", 0x54)):
                try:
                    d = self.elm.request_uds(cmd, 3, pending_wait=8)
                    if _positive(d, pos) is not None:
                        return
                except ELMError:
                    pass
            if m.category == "powertrain":
                try:
                    d = self.elm.request_uds("04", 5, pending_wait=8)
                    if 0x44 in d:
                        return
                    n = _negative(d, 0x04)
                    if n and n.nrc == 0x22:
                        raise ELMError(f"{m.name} refused — switch the ENGINE OFF, keep ignition ON")
                except NoData:
                    pass
            raise ELMError(f"{m.name} refused to clear codes")

    def identification(self, m: Module) -> list[tuple[str, str]]:
        out = super().identification(m)
        if out:
            return out
        with self.channel(m):
            for lid, name in ((0x87, "Part number (KWP)"), (0x8C, "Serial (KWP)"), (0x90, "VIN (KWP)"),
                              (0x88, "Software (KWP)"), (0x8A, "Supplier (KWP)")):
                try:
                    d = self.elm.request_uds(f"1A{lid:02X}", 1)
                    r = _positive(d, 0x5A, lid)
                    if r:
                        out.append((name, bytes(b for b in r[2:] if 0x20 <= b <= 0x7E).decode().strip()))
                except ELMError:
                    pass
        return out
