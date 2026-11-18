"""Byte transports to an ELM327 adapter: serial (USB / Bluetooth RFCOMM / COM), TCP (Wi-Fi), BLE."""
from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections import deque


class Transport:
    def write(self, data: bytes) -> None: ...
    def read_until_prompt(self, timeout: float) -> bytes: ...
    def close(self) -> None: ...
    def flush_input(self) -> None: ...


class SerialTransport(Transport):
    def __init__(self, port: str, baud: int = 38400):
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.05, write_timeout=2)
        self.ser.reset_input_buffer()

    def write(self, data: bytes) -> None:
        self.ser.write(data)
        self.ser.flush()

    def read_until_prompt(self, timeout: float) -> bytes:
        buf = bytearray()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if b">" in chunk:
                    break
        return bytes(buf)

    def flush_input(self) -> None:
        self.ser.reset_input_buffer()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass


class TCPTransport(Transport):
    def __init__(self, host: str, port: int):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.settimeout(0.05)

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)

    def read_until_prompt(self, timeout: float) -> bytes:
        buf = bytearray()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Adapter closed connection")
                buf += chunk
                if b">" in chunk:
                    break
            except socket.timeout:
                continue
        return bytes(buf)

    def flush_input(self) -> None:
        self.sock.setblocking(False)
        try:
            while self.sock.recv(4096):
                pass
        except (BlockingIOError, OSError):
            pass
        self.sock.settimeout(0.05)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


class BLETransport(Transport):
    """BLE via bleak, run on a private asyncio loop thread. Auto-picks notify + write characteristics."""

    def __init__(self, address: str):
        from bleak import BleakClient
        self._rx: deque[int] = deque()
        self._cv = threading.Condition()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        _release_stale_link(address)
        self.client = BleakClient(address)
        self._run(self._connect(), 20)

    def _run(self, coro, timeout):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    async def _connect(self):
        await self.client.connect()
        notify = write = None
        for svc in self.client.services:
            n = next((c for c in svc.characteristics if {"notify", "indicate"} & set(c.properties)), None)
            w = next((c for c in svc.characteristics
                      if {"write-without-response", "write"} & set(c.properties)), None)
            if n and w:
                notify, write = n, w
                break
            notify = notify or n
            write = write or w
        if not notify or not write:
            raise ConnectionError("No usable BLE characteristics")
        self._write_char = write
        self._wwr = "write-without-response" in write.properties
        await self.client.start_notify(notify, self._on_notify)

    def _on_notify(self, _h, data: bytearray):
        with self._cv:
            self._rx.extend(data)
            self._cv.notify_all()

    def write(self, data: bytes) -> None:
        mtu = max(20, (self.client.mtu_size or 23) - 3)
        for i in range(0, len(data), mtu):
            self._run(self.client.write_gatt_char(self._write_char, data[i:i + mtu], response=not self._wwr), 5)

    def read_until_prompt(self, timeout: float) -> bytes:
        buf = bytearray()
        end = time.monotonic() + timeout
        with self._cv:
            while True:
                while self._rx:
                    b = self._rx.popleft()
                    buf.append(b)
                    if b == 0x3E:
                        return bytes(buf)
                left = end - time.monotonic()
                if left <= 0:
                    return bytes(buf)
                self._cv.wait(left)

    def flush_input(self) -> None:
        with self._cv:
            self._rx.clear()

    def close(self) -> None:
        try:
            self._run(self.client.disconnect(), 5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)


def _bluez_devices() -> list[tuple[str, str, bool]]:
    """Known BlueZ devices (address, name, connected). Linux only; empty elsewhere."""
    import shutil
    import subprocess
    if not shutil.which("bluetoothctl"):
        return []
    try:
        out = subprocess.run(["bluetoothctl", "devices"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return []
    res = []
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0] == "Device":
            try:
                info = subprocess.run(["bluetoothctl", "info", parts[1]], capture_output=True, text=True,
                                      timeout=5).stdout
            except Exception:
                info = ""
            res.append((parts[1], parts[2], "Connected: yes" in info))
    return res


def _release_stale_link(address: str) -> None:
    """If BlueZ holds a link to the adapter (left over from a crash or Settings), drop it so we can connect."""
    import shutil
    import subprocess
    if not shutil.which("bluetoothctl"):
        return
    try:
        info = subprocess.run(["bluetoothctl", "info", address], capture_output=True, text=True, timeout=5).stdout
        if "Connected: yes" in info:
            subprocess.run(["bluetoothctl", "disconnect", address], capture_output=True, timeout=8)
            time.sleep(1.5)
    except Exception:
        pass


def list_serial_ports() -> list[tuple[str, str]]:
    from serial.tools import list_ports
    out = [(p.device, f"{p.device} — {p.description}") for p in list_ports.comports()
           if not (p.device.startswith("/dev/ttyS") and p.description in ("n/a", ""))]
    import glob
    for dev in sorted(glob.glob("/dev/rfcomm*")):
        if dev not in [d for d, _ in out]:
            out.append((dev, f"{dev} — Bluetooth RFCOMM"))
    return out


def scan_ble(seconds: float = 5.0) -> list[tuple[str, str, int]]:
    from bleak import BleakScanner

    async def go():
        found = await BleakScanner.discover(timeout=seconds, return_adv=True)
        return [(d.address, d.name or adv.local_name or "", adv.rssi) for d, adv in found.values()]

    likely = ("OBD", "ELM", "KONNWEI", "KW", "VLINK", "V-LINK", "OBDII", "MAXOBD")
    try:
        res = [r for r in asyncio.run(go()) if r[1]]
    except Exception:
        res = []
    seen = {r[0] for r in res}
    # adapters already linked to this PC don't advertise: list them from BlueZ too
    for addr, name, connected in _bluez_devices():
        if addr not in seen and any(k in name.upper() for k in likely):
            res.append((addr, name + (" (linked)" if connected else " (known)"), -100))
    res.sort(key=lambda r: (not any(k in r[1].upper() for k in likely), -r[2]))
    return res
