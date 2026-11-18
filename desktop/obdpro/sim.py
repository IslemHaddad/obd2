"""Simulated ELM327 + SEAT Leon (CAN 11/500) for demo mode and tests."""
from __future__ import annotations

import math
import time

from .transport import Transport


class SimTransport(Transport):
    def __init__(self):
        self.out = b""
        self.header = "7DF"
        self.headers_on = False
        self.t0 = time.monotonic()
        self.session = 1
        self.obd_dtcs = {"7E0": ["0133", "0300"], "7E1": []}
        self.vag_faults = {"714": [(0x9A, 0x10, 0x13, 0x09)],               # instruments: U1A10 13
                           "70E": [(0x90, 0x23, 0x11, 0x08), (0x91, 0x01, 0x13, 0x09)],
                           "7E0": [(0x01, 0x33, 0x00, 0x09)]}
        self.present = {"7E0", "7E1", "713", "712", "746", "70E", "715", "714", "710", "773", "74A", "74B"}
        self.coding = {"70E": [0x3C, 0x1A, 0x0F, 0x80, 0x00, 0x22, 0x47, 0x01, 0x00, 0x10, 0x3F, 0x00],
                       "714": [0x01, 0x04, 0x20, 0x00, 0x8C, 0x00]}
        self.dids = {0xF187: b"5F0919605B ", 0xF197: b"BCM MQB    ", 0xF189: b"0254", 0xF191: b"5Q0937084  ",
                     0x1000: bytes([0x00, 0x7B]), 0x1001: bytes([0x2E]), 0x02BD: bytes([0x01])}
        self.routine_polls = 0

    # transport API
    def write(self, data: bytes) -> None:
        cmd = data.decode().strip().upper().replace(" ", "")
        self.out = (self._handle(cmd) + "\r\r>").encode()

    def read_until_prompt(self, timeout: float) -> bytes:
        time.sleep(0.004)
        o, self.out = self.out, b""
        return o

    def flush_input(self) -> None:
        pass

    def close(self) -> None:
        pass

    # ---------------------------------------------------------------
    def _handle(self, c: str) -> str:
        if c.startswith("AT"):
            return self._at(c[2:])
        if self.header == "7DF":
            return self._obd(c)
        if self.header not in self.present:
            return "NO DATA"
        return self._uds(c)

    def _at(self, a: str) -> str:
        if a == "Z" or a == "I":
            return "ELM327 v1.5 (SIM)"
        if a == "DPN":
            return "A6"
        if a == "RV":
            return f"{12.4 + 0.1 * math.sin(time.monotonic()):.1f}V"
        if a == "H1":
            self.headers_on = True
        elif a == "H0":
            self.headers_on = False
        elif a.startswith("SH"):
            self.header = a[2:]
            if self.header in ("7E0", "7E1") and self.header in self.obd_dtcs:
                pass
        return "OK"

    def _t(self):
        return time.monotonic() - self.t0

    def _pidval(self, pid: int) -> str:
        t = self._t()
        rpm = int((850 + 1800 * (0.5 + 0.5 * math.sin(t / 3))) * 4)
        vals = {
            0x04: f"{int(60 + 50 * math.sin(t / 2)) & 0xFF:02X}",
            0x05: f"{min(int(40 + 50 + t), 255) & 0xFF:02X}",
            0x0B: f"{int(35 + 30 * math.sin(t / 3)):02X}",
            0x0C: f"{rpm >> 8:02X}{rpm & 0xFF:02X}",
            0x0D: f"{int(50 + 45 * math.sin(t / 6)):02X}",
            0x0F: "41", 0x10: "0190", 0x11: f"{int(40 + 35 * math.sin(t / 2)) & 0xFF:02X}",
            0x2F: "B3", 0x33: "65", 0x42: "3070", 0x46: "3C", 0x5C: "7D",
        }
        return vals.get(pid, "")

    def _obd(self, c: str) -> str:
        mode = c[:2]
        if mode == "01":
            body = c[2:]
            if body.endswith("1") and len(body) % 2 == 1:
                body = body[:-1]
            pids = [int(body[i:i + 2], 16) for i in range(0, len(body), 2)]
            if pids == [0x00]:
                if self.headers_on:
                    return "7E8064100BE3FB813\r7E9064100983B0011"
                return "4100BE3FB813"
            if pids == [0x20]:
                return "4120A007B015"
            if pids == [0x40]:
                return "4140FED08500"
            if pids == [0x01]:
                n = len(self.obd_dtcs.get("7E0", []))
                return f"4101{0x80 | n if n else 0:02X}076504"
            out = "".join(f"{p:02X}{self._pidval(p)}" for p in pids if self._pidval(p))
            return "41" + out if out else "NO DATA"
        if mode in ("03", "07", "0A"):
            codes = self.obd_dtcs.get("7E0", []) if mode == "03" else []
            return f"{int(mode, 16) + 0x40:02X}{len(codes):02X}" + "".join(codes)
        if mode == "04":
            self.obd_dtcs["7E0"] = []
            return "44"
        if c == "0902":
            vin = "VSSZZZKLZMR123456".encode().hex().upper()
            return "014\r0:4902015653535A\r1:" + vin[8:22] + "\r2:" + vin[22:]
        if mode == "02":
            pid = int(c[2:4], 16)
            v = self._pidval(pid)
            return f"42{pid:02X}00{v}" if v else "NO DATA"
        return "NO DATA"

    def _uds(self, c: str) -> str:
        h = self.header
        sid = c[:2]
        if h in ("7E0", "7E1") and sid in ("03", "07", "0A", "04"):
            codes = self.obd_dtcs.get(h, []) if sid == "03" else []
            if sid == "04":
                self.obd_dtcs[h] = []
                return "44"
            return f"{int(sid, 16) + 0x40:02X}{len(codes):02X}" + "".join(codes)
        if c.startswith("1902"):
            mask = int(c[4:6], 16)
            noise = [(0x90, 0x4D, 0x00, 0x10), (0xEA, 0x61, 0x00, 0x10)]     # supported, not tested since clear
            recs = "".join(f"{a:02X}{b:02X}{f:02X}{s:02X}" for a, b, f, s in self.vag_faults.get(h, []) + noise
                           if s & mask)
            return "59021" + "9" + recs
        if c.startswith("10"):
            self.session = int(c[2:4], 16)
            return "50" + c[2:4] + "003201F4"
        if c == "14FFFFFF":
            self.vag_faults[h] = []
            if h in self.obd_dtcs:
                self.obd_dtcs[h] = []
            return "54"
        if c == "3E00":
            return "7E00"
        if sid == "22":
            did = int(c[2:6], 16)
            if did == 0x0600 and h in self.coding:
                return "620600" + "".join(f"{b:02X}" for b in self.coding[h])
            if did in self.dids:
                return f"62{did:04X}" + self.dids[did].hex().upper()
            if did == 0xF190:
                return "62F190" + b"VSSZZZKLZMR123456".hex().upper()
            return "7F2231"
        if sid == "2E":
            did = int(c[2:6], 16)
            if self.session != 3:
                return "7F2E7F"
            data = [int(c[i:i + 2], 16) for i in range(6, len(c), 2)]
            if did == 0x0600:
                self.coding[h] = data
            else:
                self.dids[did] = bytes(data)
            return f"6E{did:04X}"
        if sid == "2F":
            return "6F" + c[2:6] + c[6:8] + "01"
        if sid == "31":
            sub, rid = c[2:4], c[4:8]
            if sub == "01":
                self.routine_polls = 0
                return f"7101{rid}01"
            if sub == "03":
                self.routine_polls += 1
                return f"7103{rid}" + ("00" if self.routine_polls >= 8 else "01")
            return f"7102{rid}"
        return f"7F{sid}11"
