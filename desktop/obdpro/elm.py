"""ELM327 command channel. Thread-safe: one command at a time (use `elm.lock` to hold the bus across commands)."""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from .transport import Transport


class ELMError(Exception):
    pass


class NoData(ELMError):
    def __init__(self):
        super().__init__("NO DATA")


ERROR_TOKENS = ("NO DATA", "UNABLE TO CONNECT", "CAN ERROR", "BUS ERROR", "BUS BUSY",
                "FB ERROR", "DATA ERROR", "STOPPED", "?", "ERR")

PROTOCOLS = {
    1: "SAE J1850 PWM", 2: "SAE J1850 VPW", 3: "ISO 9141-2", 4: "ISO 14230-4 KWP (5 baud)",
    5: "ISO 14230-4 KWP (fast)", 6: "ISO 15765-4 CAN 11/500", 7: "ISO 15765-4 CAN 29/500",
    8: "ISO 15765-4 CAN 11/250", 9: "ISO 15765-4 CAN 29/250", 10: "SAE J1939 CAN",
}

_HEX = re.compile(r"[0-9A-Fa-f]")


def hex_bytes(s: str) -> list[int]:
    digits = _HEX.findall(s)
    return [int(digits[i] + digits[i + 1], 16) for i in range(0, len(digits) - 1, 2)]


def to_hex(b, sep: str = "") -> str:
    return sep.join(f"{x:02X}" for x in b)


def log_path() -> Path:
    import os
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / "obdpro"
    d.mkdir(parents=True, exist_ok=True)
    return d / "adapter.log"


class TrafficLog:
    """Every command/response with timing, to ~/.config/obdpro/adapter.log (rotated at 2 MB) + in-memory tail."""

    def __init__(self):
        self.path = log_path()
        if self.path.exists() and self.path.stat().st_size > 2_000_000:
            self.path.replace(self.path.with_suffix(".log.1"))
        self.f = open(self.path, "a", buffering=1)
        self.tail: list[str] = []
        self.listeners = []

    def write(self, line: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {line}"
        self.f.write(line + "\n")
        self.tail.append(line)
        del self.tail[:-2000]
        for fn in list(self.listeners):
            try:
                fn(line)
            except Exception:
                pass


TRAFFIC = TrafficLog()


class AdapterProfile:
    """What kind of adapter this is, and which workarounds it needs."""

    def __init__(self, ati: str = "", sti: str = "", device: str = ""):
        self.ati, self.sti, self.device = ati, sti, device
        a = ati.upper()
        self.is_stn = bool(sti)                                   # OBDLink / STN-based (genuine, fast)
        # Elm Electronics never released v1.5 / v2.1 firmware for sale → those strings mean a clone.
        self.is_clone = not self.is_stn and (any(v in a for v in ("V1.5", "V2.1", "V2.2", "V2.3")) or
                                             not a.startswith("ELM327"))
        self.fast = self.is_stn                                   # response-count hint + shorter waits

    @property
    def chip(self) -> str:
        if self.is_stn:
            return f"{self.sti} (genuine STN)"
        return f"{self.ati} ({'clone' if self.is_clone else 'ELM327'})"

    @property
    def summary(self) -> str:
        if self.is_stn:
            return "Genuine STN chip: fast mode, long replies OK"
        if self.is_clone:
            return "Clone chip: reply re-sync, short fault lists, busy-retry and voltage correction enabled"
        return "ELM327: standard mode"


class ELM327:
    def __init__(self, transport: Transport):
        self.t = transport
        self.lock = threading.RLock()
        self.protocol = 0
        self.is_can = True
        self.version = ""
        self.profile = AdapterProfile()
        TRAFFIC.write(f"=== session start ({transport.__class__.__name__}) ===")

    @property
    def protocol_name(self) -> str:
        return PROTOCOLS.get(self.protocol, "Unknown")

    def send(self, cmd: str, timeout: float = 2.0) -> list[str]:
        with self.lock:
            self.t.flush_input()
            t0 = time.monotonic()
            self.t.write((cmd + "\r").encode())
            raw = self.t.read_until_prompt(timeout)
        ms = (time.monotonic() - t0) * 1000
        shown = raw.decode(errors="replace").replace("\r", "\\r").replace("\n", "\\n")
        TRAFFIC.write(f"> {cmd:<14} < {shown}  [{ms:.0f} ms]" + ("" if b">" in raw else "  TIMEOUT"))
        if b">" not in raw:
            raise ELMError(f"No reply from adapter to {cmd} (timeout {timeout:.0f}s)")
        text = raw.replace(b"\x00", b"").decode(errors="ignore").replace(">", "")
        lines = [l.strip() for l in re.split(r"[\r\n]+", text)]
        lines = [l for l in lines if l and l != cmd and not l.startswith("SEARCHING") and l != "BUS INIT: ...OK"]
        for l in lines:
            if any(tok in l for tok in ERROR_TOKENS):
                if "NO DATA" in l:
                    raise NoData()
                if "UNABLE TO CONNECT" in l:
                    raise ELMError("Adapter unable to connect to vehicle (ignition on?)")
                raise ELMError(l)
        return lines

    def request_uds(self, cmd: str, timeout: float = 2.0, pending_wait: float = 5.0) -> list[int]:
        """Like request(), but handles 7F xx 78 (response pending): cheap ELM clones stop listening after
        printing it, so retry with the adapter's maximum receive timeout (ATST FF ≈ 1 s per frame)."""
        with self.lock:
            d = self.request(cmd, timeout)
            if not _only_pending(d):
                return d
            try:
                self.send("ATSTFF", 1)
                end = time.monotonic() + pending_wait
                while _only_pending(d) and time.monotonic() < end:
                    try:
                        d = self.request(cmd, timeout + 2)
                    except NoData:
                        d = []
            finally:
                try:
                    self.send("ATST32", 1)
                    self.send("ATAT2", 1)
                except ELMError:
                    pass
            return d

    def _drain(self, quiet: float = 0.4) -> None:
        """Wait until the adapter has been silent for `quiet` seconds, discarding late replies."""
        end = time.monotonic() + 3
        while time.monotonic() < end:
            got = self.t.read_until_prompt(quiet)
            if not got:
                return
            TRAFFIC.write(f"  (discarded late data: {got.decode(errors='replace')!r})")

    def _sync(self) -> None:
        """Send ATE0 until we get a clean OK back, so commands and replies are aligned."""
        for _ in range(4):
            try:
                if any("OK" in l for l in self.send("ATE0", 2)):
                    return
            except ELMError:
                pass
            self._drain()
        raise ELMError("Adapter is not answering. Is it powered (plugged into the car) and not connected to "
                       "another phone/app?")

    def initialize(self) -> None:
        with self.lock:
            try:
                self.send("ATZ", 5)               # reset can be slow on BLE clones
            except ELMError:
                pass
            time.sleep(0.3)
            self._drain()
            self._sync()
            for c in ("ATL0", "ATS0", "ATH0", "ATAT2", "ATSP0"):
                self.send(c)
            try:
                self.version = (self.send("ATI") or [""])[0]
            except ELMError:
                pass
            sti = dev = ""
            try:
                sti = (self.send("STI", 1) or [""])[0]           # only STN chips understand ST commands
            except ELMError:
                pass
            try:
                dev = (self.send("AT@1", 1) or [""])[0]
            except ELMError:
                pass
            self.profile = AdapterProfile(self.version, sti, dev)
            TRAFFIC.write(f"=== adapter: {self.profile.chip} · {self.profile.summary} ===")
            try:
                self.send("0100", 12)
            except ELMError as e:
                raise ELMError(f"Adapter OK ({self.version}) but the car did not answer: {e}. "
                               f"Turn the ignition ON (engine can be off) and try again.") from e
            try:
                dp = self.send("ATDPN")[0].upper().lstrip("A")
                self.protocol = int(dp, 16)
            except (ELMError, ValueError, IndexError):
                self.protocol = 0
            self.is_can = self.protocol >= 6
            TRAFFIC.write(f"=== connected: {self.version} · protocol {self.protocol} {self.protocol_name} ===")

    @staticmethod
    def merge(lines: list[str], is_can: bool) -> list[int]:
        out: list[int] = []
        for l in lines:
            if is_can and len(l) == 3 and ":" not in l and _is_hex(l):
                continue                       # multi-frame byte count line
            if ":" in l:
                l = l.split(":", 1)[1]
            out += hex_bytes(l)
        return out

    def request(self, cmd: str, timeout: float = 2.0) -> list[int]:
        return self.merge(self.send(cmd, timeout), self.is_can)

    def request_lines(self, cmd: str, timeout: float = 3.0) -> list[list[int]]:
        return [hex_bytes(l.split(":", 1)[-1]) for l in self.send(cmd, timeout)]

    def battery_voltage(self) -> float | None:
        try:
            s = self.send("ATRV")[0]
            return float(re.sub(r"[^0-9.]", "", s))
        except (ELMError, ValueError, IndexError):
            return None

    def close(self):
        self.t.close()


def _only_pending(d: list[int]) -> bool:
    return len(d) >= 3 and d[0] == 0x7F and d[2] == 0x78 and all(
        d[i] == 0x7F and d[i + 2] == 0x78 for i in range(0, len(d) - 2, 3))


def _is_hex(s: str) -> bool:
    try:
        int(s, 16)
        return True
    except ValueError:
        return False
