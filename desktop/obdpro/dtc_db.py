"""DTC descriptions (ported from the iOS app)."""
KNOWN = {
    "P0010": "Camshaft Position Actuator Circuit (Bank 1)",
    "P0011": "Camshaft Timing Over-Advanced (Bank 1)",
    "P0016": "Crankshaft/Camshaft Position Correlation (Bank 1 Sensor A)",
    "P0087": "Fuel Rail/System Pressure Too Low",
    "P0100": "Mass Air Flow Circuit Malfunction",
    "P0101": "Mass Air Flow Circuit Range/Performance",
    "P0102": "Mass Air Flow Circuit Low Input",
    "P0106": "MAP Sensor Circuit Range/Performance",
    "P0113": "Intake Air Temperature Circuit High Input",
    "P0117": "Engine Coolant Temperature Circuit Low",
    "P0118": "Engine Coolant Temperature Circuit High",
    "P0121": "Throttle Position Sensor A Range/Performance",
    "P0128": "Coolant Thermostat Below Regulating Temperature",
    "P0131": "O2 Sensor Circuit Low Voltage (B1S1)",
    "P0133": "O2 Sensor Circuit Slow Response (B1S1)",
    "P0135": "O2 Sensor Heater Circuit (B1S1)",
    "P0141": "O2 Sensor Heater Circuit (B1S2)",
    "P0171": "System Too Lean (Bank 1)",
    "P0172": "System Too Rich (Bank 1)",
    "P0174": "System Too Lean (Bank 2)",
    "P0175": "System Too Rich (Bank 2)",
    "P0217": "Engine Overheat Condition",
    "P0234": "Turbocharger Overboost Condition",
    "P0299": "Turbocharger Underboost",
    "P0300": "Random/Multiple Cylinder Misfire Detected",
    "P0301": "Cylinder 1 Misfire Detected",
    "P0302": "Cylinder 2 Misfire Detected",
    "P0303": "Cylinder 3 Misfire Detected",
    "P0304": "Cylinder 4 Misfire Detected",
    "P0305": "Cylinder 5 Misfire Detected",
    "P0306": "Cylinder 6 Misfire Detected",
    "P0325": "Knock Sensor 1 Circuit (Bank 1)",
    "P0335": "Crankshaft Position Sensor A Circuit",
    "P0340": "Camshaft Position Sensor Circuit (Bank 1)",
    "P0380": "Glow Plug/Heater Circuit A",
    "P0401": "EGR Flow Insufficient",
    "P0402": "EGR Flow Excessive",
    "P0420": "Catalyst Efficiency Below Threshold (Bank 1)",
    "P0430": "Catalyst Efficiency Below Threshold (Bank 2)",
    "P0440": "EVAP System Malfunction",
    "P0442": "EVAP System Small Leak Detected",
    "P0455": "EVAP System Large Leak Detected",
    "P0456": "EVAP System Very Small Leak Detected",
    "P0500": "Vehicle Speed Sensor Malfunction",
    "P0505": "Idle Air Control System",
    "P0507": "Idle RPM Higher Than Expected",
    "P0562": "System Voltage Low",
    "P0563": "System Voltage High",
    "P0600": "Serial Communication Link",
    "P0606": "ECM/PCM Processor Fault",
    "P0700": "Transmission Control System Malfunction",
    "P0715": "Input/Turbine Speed Sensor Circuit",
    "P0730": "Incorrect Gear Ratio",
    "P0741": "Torque Converter Clutch Circuit Performance",
    "P2002": "Diesel Particulate Filter Efficiency Below Threshold",
    "P2135": "Throttle/Pedal Position Sensor A/B Voltage Correlation",
    "P242F": "Diesel Particulate Filter Restriction - Ash Accumulation",
    "U0100": "Lost Communication With ECM/PCM",
    "U0101": "Lost Communication With TCM",
    "U0121": "Lost Communication With ABS Module",
    "U0140": "Lost Communication With Body Control Module",
}


# --- Online fallback: full code table fetched once from the project repo, cached on disk ---
import json as _json
import os as _os
import urllib.request as _url

_ONLINE: dict[str, str] = {}
_ONLINE_URL = "https://raw.githubusercontent.com/IslemHaddad/obd2/main/data/dtc.json"
_CACHE = _os.path.join(_os.path.expanduser("~"), ".cache", "obdpro", "dtc.json")


def _load_cache() -> None:
    global _ONLINE
    try:
        with open(_CACHE, encoding="utf-8") as f:
            _ONLINE = _json.load(f)
    except Exception:
        pass


def preload_online() -> None:
    """Fetch the full code table once and cache it. Best-effort; silent offline."""
    global _ONLINE
    if len(_ONLINE) > 100:
        return
    try:
        req = _url.Request(_ONLINE_URL, headers={"User-Agent": "OBDPro/1.0"})
        with _url.urlopen(req, timeout=8) as r:
            data = r.read()
        m = _json.loads(data)
        if m:
            _ONLINE = m
            _os.makedirs(_os.path.dirname(_CACHE), exist_ok=True)
            with open(_CACHE, "wb") as f:
                f.write(data)
    except Exception:
        pass


def lookup(code: str) -> str | None:
    """Curated set first, then the online table."""
    return KNOWN.get(code) or _ONLINE.get(code)


_load_cache()


def describe(code: str) -> str:
    if code in KNOWN:
        return KNOWN[code]
    if code in _ONLINE:
        return _ONLINE[code]
    if len(code) != 5:
        return "Unknown"
    s, d1, d2 = code[0], code[1], code[2]
    generic = d1 in "02" or (s == "P" and d1 == "3" and d2 >= "4")
    scope = "Generic" if generic else "Manufacturer-specific"
    if s == "P":
        area = {"0": "Fuel & Air Metering", "1": "Fuel & Air Metering", "2": "Fuel & Air Metering",
                "3": "Ignition / Misfire", "4": "Auxiliary Emission Controls", "5": "Speed / Idle Control",
                "6": "Computer Output Circuit", "7": "Transmission", "8": "Transmission", "9": "Transmission",
                "A": "Hybrid Propulsion", "B": "Hybrid Propulsion", "C": "Hybrid Propulsion"}.get(d2, "Powertrain")
    else:
        area = {"C": "Chassis", "B": "Body", "U": "Network Communication"}[s]
    return f"{scope} – {area}"


def decode(a: int, b: int) -> str:
    return "PCBU"[a >> 6] + f"{(a >> 4) & 3:X}{a & 0xF:X}{b:02X}"
