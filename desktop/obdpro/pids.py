"""SAE J1979 mode 01 PIDs (ported from the iOS app)."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PID:
    id: int
    name: str
    unit: str
    nbytes: int
    min: float
    max: float
    fn: Callable[[float, float], float]

    def decode(self, d):
        A = float(d[0])
        AB = float(d[0] << 8 | d[1]) if len(d) > 1 else A
        return self.fn(A, AB)


ALL = [
    PID(0x04, "Engine Load", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x05, "Coolant Temp", "°C", 1, -40, 215, lambda A, AB: A - 40),
    PID(0x06, "Short Fuel Trim B1", "%", 1, -100, 99.2, lambda A, AB: A / 1.28 - 100),
    PID(0x07, "Long Fuel Trim B1", "%", 1, -100, 99.2, lambda A, AB: A / 1.28 - 100),
    PID(0x08, "Short Fuel Trim B2", "%", 1, -100, 99.2, lambda A, AB: A / 1.28 - 100),
    PID(0x09, "Long Fuel Trim B2", "%", 1, -100, 99.2, lambda A, AB: A / 1.28 - 100),
    PID(0x0A, "Fuel Pressure", "kPa", 1, 0, 765, lambda A, AB: A * 3),
    PID(0x0B, "Intake MAP", "kPa", 1, 0, 255, lambda A, AB: A),
    PID(0x0C, "RPM", "rpm", 2, 0, 8000, lambda A, AB: AB / 4),
    PID(0x0D, "Speed", "km/h", 1, 0, 255, lambda A, AB: A),
    PID(0x0E, "Timing Advance", "°", 1, -64, 63.5, lambda A, AB: A / 2 - 64),
    PID(0x0F, "Intake Air Temp", "°C", 1, -40, 215, lambda A, AB: A - 40),
    PID(0x10, "MAF Rate", "g/s", 2, 0, 655.35, lambda A, AB: AB / 100),
    PID(0x11, "Throttle Position", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x1F, "Run Time", "s", 2, 0, 65535, lambda A, AB: AB),
    PID(0x21, "Distance w/ MIL", "km", 2, 0, 65535, lambda A, AB: AB),
    PID(0x22, "Fuel Rail Pressure", "kPa", 2, 0, 5177, lambda A, AB: AB * 0.079),
    PID(0x23, "Fuel Rail Gauge Pressure", "kPa", 2, 0, 655350, lambda A, AB: AB * 10),
    PID(0x2C, "Commanded EGR", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x2F, "Fuel Level", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x31, "Distance Since Clear", "km", 2, 0, 65535, lambda A, AB: AB),
    PID(0x33, "Barometric Pressure", "kPa", 1, 0, 255, lambda A, AB: A),
    PID(0x3C, "Catalyst Temp B1S1", "°C", 2, -40, 6513, lambda A, AB: AB / 10 - 40),
    PID(0x42, "Module Voltage", "V", 2, 0, 65.535, lambda A, AB: AB / 1000),
    PID(0x43, "Absolute Load", "%", 2, 0, 25700, lambda A, AB: AB * 100 / 255),
    PID(0x44, "Commanded AFR λ", "λ", 2, 0, 2, lambda A, AB: AB * 2 / 65536),
    PID(0x45, "Relative Throttle", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x46, "Ambient Air Temp", "°C", 1, -40, 215, lambda A, AB: A - 40),
    PID(0x47, "Throttle Pos B", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x49, "Accel Pedal D", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x4A, "Accel Pedal E", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x4C, "Commanded Throttle", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x4D, "Time w/ MIL", "min", 2, 0, 65535, lambda A, AB: AB),
    PID(0x4E, "Time Since Clear", "min", 2, 0, 65535, lambda A, AB: AB),
    PID(0x51, "Fuel Type", "", 1, 0, 255, lambda A, AB: A),
    PID(0x52, "Ethanol %", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x5A, "Rel. Accel Pedal", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x5B, "Hybrid Battery Life", "%", 1, 0, 100, lambda A, AB: A * 100 / 255),
    PID(0x5C, "Oil Temp", "°C", 1, -40, 210, lambda A, AB: A - 40),
    PID(0x5E, "Fuel Rate", "L/h", 2, 0, 3212, lambda A, AB: AB / 20),
    PID(0x61, "Demanded Torque", "%", 1, -125, 130, lambda A, AB: A - 125),
    PID(0x62, "Actual Torque", "%", 1, -125, 130, lambda A, AB: A - 125),
    PID(0x63, "Reference Torque", "Nm", 2, 0, 65535, lambda A, AB: AB),
]
BY_ID = {p.id: p for p in ALL}


def length(pid: int):
    if pid in BY_ID:
        return BY_ID[pid].nbytes
    if pid in (0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0, 0x01, 0x41):
        return 4
    if pid == 0x03:
        return 2
    if pid in (0x12, 0x13, 0x1C, 0x1D, 0x1E, 0x30):
        return 1
    if 0x14 <= pid <= 0x1B or 0x3D <= pid <= 0x3F:
        return 2
    if 0x24 <= pid <= 0x2B or 0x34 <= pid <= 0x3B:
        return 4
    return None
