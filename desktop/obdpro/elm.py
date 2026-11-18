"""ELM327 command channel. Thread-safe: one command at a time (use `elm.lock` to hold the bus across commands)."""
from __future__ import annotations

import re
import threading

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


class ELM327:
    def __init__(self, transport: Transport):
        self.t = transport
        self.lock = threading.RLock()
        self.protocol = 0
        self.is_can = True
        self.version = ""
        self.log: list[str] = []

    @property
    def protocol_name(self) -> str:
        return PROTOCOLS.get(self.protocol, "Unknown")

    def send(self, cmd: str, timeout: float = 2.0) -> list[str]:
        with self.lock:
            self.t.flush_input()
            self.t.write((cmd + "\r").encode())
            raw = self.t.read_until_prompt(timeout)
        if b">" not in raw:
            raise ELMError(f"Timeout on {cmd}")
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

    def initialize(self) -> None:
        try:
            self.send("ATZ", 3)
        except ELMError:
            pass
        for c in ("ATE0", "ATL0", "ATS0", "ATH0", "ATAT2", "ATSP0"):
            self.send(c)
        try:
            self.version = (self.send("ATI") or [""])[0]
        except ELMError:
            pass
        self.send("0100", 10)
        try:
            dp = self.send("ATDPN")[0].replace("A", "")
            self.protocol = int(dp, 16)
        except (ELMError, ValueError, IndexError):
            self.protocol = 0
        self.is_can = self.protocol >= 6

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


def _is_hex(s: str) -> bool:
    try:
        int(s, 16)
        return True
    except ValueError:
        return False
