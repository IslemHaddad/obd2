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


# Renault / Dacia (diag CAN 500k): physical request 7xx, response usually request + 0x20 (ECM keeps OBD +8).
# Labels are best-effort; discovery decides what is really fitted.
RENAULT = {
    "7E0": ("Engine (UCE)", "powertrain", 0.50, 0.14),
    "7E1": ("Automatic gearbox (BVA)", "powertrain", 0.50, 0.27),
    "740": ("ABS / ESP", "chassis", 0.27, 0.20),
    "742": ("Power steering (DAE)", "chassis", 0.66, 0.24),
    "743": ("Instrument cluster (TdB)", "electronics", 0.33, 0.35),
    "744": ("Climate control", "electronics", 0.50, 0.41),
    "745": ("Body control (UCH)", "electronics", 0.20, 0.42),
    "752": ("Airbag", "safety", 0.50, 0.50),
    "74D": ("Parking sensors", "electronics", 0.50, 0.92),
    "747": ("Radio / multimedia", "electronics", 0.50, 0.34),
    "76D": ("Hands-free card / keyless", "electronics", 0.62, 0.45),
}
OFFSETS = {"hyundai": (8,), "renault": (0x20, 8)}


def module_for(req: str, family: str = "hyundai", resp: str | None = None) -> Module:
    table = RENAULT if family == "renault" else KNOWN
    v = int(req, 16)
    name, cat, x, y = table.get(req, (f"Module {req}", "electronics", 0.5 + ((v * 37) % 50 - 25) / 100,
                                      0.6 + ((v * 53) % 30) / 100))
    if resp is None:
        off = 8 if (family != "renault" or req in ("7E0", "7E1")) else 0x20
        resp = f"{v + off:03X}"
    return Module(req, name, req, resp, cat, x, y)


class Hyundai(VAG):
    """Reuses VAG's channel handling (ATSH/ATCRA/flow-control); different discovery and DTC services.
    Also used for Renault/Dacia (family="renault": responses on +0x20 as well as +8)."""

    def __init__(self, elm, family: str = "hyundai"):
        super().__init__(elm)
        self.family = family

    @property
    def supported(self) -> bool:
        return self.elm.protocol in (6, 8)

    # Hyundai modules differ in which "are you there" they answer (seen on a Grand i10: ABS/cluster/BCM answer
    # 3E01 with a negative reply, MDPS only answers 10 81, airbag only 10 03…). Any reply on +8 = module present.
    PROBES = ("3E00", "3E01", "1081", "1003")

    def discover(self, progress=None) -> list[Module]:
        found: list[Module] = []
        ids = [i for i in PROBE_RANGE if i != 0x7DF]
        with self.elm.lock:
            try:
                self.elm.send("ATH1", 1)
                self.elm.send("ATST19", 1)          # ~100 ms receive timeout: modules reply in <20 ms
                for n, rid in enumerate(ids):
                    if progress and n % 8 == 0:
                        progress(n / len(ids), len(found))
                    wants = {f"{rid + o:03X}": o for o in OFFSETS.get(self.family, (8,))}
                    try:
                        self.elm.send(f"ATSH{rid:03X}", 1)
                    except ELMError:
                        continue
                    for probe in self.PROBES:
                        try:
                            lines = self.elm.send(probe, 0.4)
                        except ELMError:
                            continue
                        hit = next((h for l in lines for h in wants
                                    if l.replace(" ", "").upper().startswith(h)), None)
                        if hit:
                            found.append(module_for(f"{rid:03X}", self.family, hit))
                            break
                    if found and found[-1].address == f"{rid:03X}":
                        try:                                  # return the module to its default session
                            self.elm.send("1001", 0.4)
                        except ELMError:
                            pass
            finally:
                for c in ("ATST32", "ATAT2", "ATH0", "ATSH7DF"):
                    try:
                        self.elm.send(c, 1)
                    except ELMError:
                        pass
        return found

    # ---- faults
    def _uds_faults(self, m: Module):
        """UDS 19 02 with fallbacks seen on Hyundai: some reject mask FF (NRC 31 → narrower mask),
        some only answer in extended session (NRC 7F/7E/22 → 10 03 first)."""
        in_ext = False
        for mask in ("FF", "2F", "09", "08", "0D", "0F"):
            for _attempt in range(2):
                try:
                    d = self.elm.request_uds(f"1902{mask}", 2)
                except ELMError:
                    return None, in_ext
                r = _positive(d, 0x59, 0x02)
                if r is not None:
                    out = []
                    rec = r[3:]
                    for j in range(0, len(rec) - 3, 4):
                        a, b, c, st = rec[j:j + 4]
                        if (a | b) and st & 0x2F:
                            out.append(Fault(dtc_db.decode(a, b), c, st, a << 16 | b << 8 | c, True))
                    return out, in_ext
                n = _negative(d, 0x19)
                if n and n.nrc in (0x7F, 0x7E, 0x22) and not in_ext:
                    try:
                        self.session(0x03)
                        in_ext = True
                        continue                      # retry same mask in extended session
                    except ELMError:
                        return None, in_ext
                if n and n.nrc == 0x31:
                    break                             # try next mask
                return None, in_ext                   # 0x11 not supported etc.
        return None, in_ext

    def _kwp_faults(self):
        # 18 = KWP readDTCByStatus (Hyundai/Kia); 17 FF00 = readStatusOfDTC used by older Renault ECUs
        for cmd, pos in (("1800FF00", 0x58), ("1802FF00", 0x58), ("17FF00", 0x57)):
            try:
                d = self.elm.request_uds(cmd, 2)
            except ELMError:
                continue
            r = _positive(d, pos)
            if r is not None and len(r) >= 2:
                out = []
                rec = r[2:]
                for j in range(0, len(rec) - 2, 3):
                    a, b, st = rec[j:j + 3]
                    if a | b:
                        out.append(Fault(dtc_db.decode(a, b), 0, 0x09 if st & 0x20 else 0x08, a << 16 | b << 8, True))
                return out
        return None

    def faults_open(self, m: Module):
        faults, in_ext = self._uds_faults(m)
        if in_ext:
            try:
                self.session(0x01)
            except ELMError:
                pass
        return faults if faults is not None else self._kwp_faults()

    def report(self, m: Module) -> Report:
        with self.channel(m):
            faults, in_ext = self._uds_faults(m)
            if faults is None:
                faults = self._kwp_faults()
            if faults is None and m.category == "powertrain":
                try:                                  # SAE mode 03/07 sent physically
                    from .obd import OBD
                    o = OBD(self.elm)
                    faults = [Fault(d.code, 0, 0x08 if d.kind == "Stored" else 0x04, 0, True)
                              for d in o.dtcs("03", "Stored") + o.dtcs("07", "Pending")]
                except ELMError:
                    faults = None
            if in_ext:
                try:
                    self.session(0x01)
                except ELMError:
                    pass
            if faults is None:
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
            for ext in (False, True):
                if ext:
                    try:
                        self.session(0x03)
                    except ELMError:
                        break
                for cmd, pos in (("14FFFFFF", 0x54), ("14FF00", 0x54)):
                    try:
                        d = self.elm.request_uds(cmd, 3, pending_wait=8)
                        if _positive(d, pos) is not None:
                            if ext:
                                try:
                                    self.session(0x01)
                                except ELMError:
                                    pass
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
