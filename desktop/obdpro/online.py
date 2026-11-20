"""Best-effort online enrichment for any VAG (and generic) vehicle.

When the machine has internet, fetch a photo + short description for the car, its engine family and
its platform from Wikipedia (keyless), plus a structured spec sheet from the public NHTSA VIN decoder
when the VIN is one it knows (mostly US-market cars; European VAG VINs usually aren't).

Privacy: only the make/model/year and the detected engine string are sent to Wikipedia. The VIN is
sent ONLY to the NHTSA government decoder, and nothing else about the user leaves the machine. Every
call has a short timeout and fails silently, so the app works identically offline.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

_UA = "OBDPro/1.0 (open-source OBD2 diagnostic app)"
_TIMEOUT = 8


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.load(r)


@dataclass
class Media:
    title: str = ""
    image_url: str = ""
    summary: str = ""
    source: str = "Wikipedia"

    def ok(self) -> bool:
        return bool(self.image_url or self.summary)


@dataclass
class CarInfo:
    title: str = ""                                   # "SEAT Ibiza"
    specs: list[tuple[str, str]] = field(default_factory=list)
    car: Media = field(default_factory=Media)
    engine: Media = field(default_factory=Media)
    platform: Media = field(default_factory=Media)
    error: str = ""

    def ok(self) -> bool:
        return bool(self.car.ok() or self.engine.ok() or self.specs)


# -------------------------------------------------------------------- Wikipedia
def wiki_search(query: str) -> Media | None:
    """Fuzzy-match the best English-Wikipedia article and return its thumbnail + intro. Keyless."""
    params = {
        "action": "query", "format": "json", "redirects": "1",
        "generator": "search", "gsrsearch": query, "gsrlimit": "1",
        "prop": "pageimages|extracts", "piprop": "thumbnail", "pithumbsize": "640",
        "exintro": "1", "explaintext": "1", "exsentences": "3",
    }
    try:
        d = _get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params))
    except Exception:
        return None
    pages = list(((d.get("query") or {}).get("pages") or {}).values())
    if not pages:
        return None
    p = pages[0]
    m = Media(title=p.get("title", ""), image_url=(p.get("thumbnail") or {}).get("source", ""),
              summary=(p.get("extract") or "").strip())
    return m if m.ok() else None


def _first(queries: list[str]) -> Media:
    for q in queries:
        if not q.strip():
            continue
        m = wiki_search(q)
        if m and m.ok():
            return m
    return Media()


# -------------------------------------------------------------------- NHTSA VIN decode (best effort)
_NHTSA_FIELDS = [
    ("Make", "Make"), ("Model", "Model"), ("ModelYear", "Year"), ("Trim", "Trim"),
    ("Series", "Series"), ("BodyClass", "Body"), ("DriveType", "Drive"), ("Doors", "Doors"),
    ("EngineModel", "Engine"), ("DisplacementL", "Displacement (L)"), ("EngineCylinders", "Cylinders"),
    ("EngineHP", "Power (hp)"), ("FuelTypePrimary", "Fuel"), ("TransmissionStyle", "Transmission"),
    ("PlantCountry", "Built in"), ("Manufacturer", "Manufacturer"),
]


def nhtsa_specs(vin: str) -> list[tuple[str, str]]:
    if not vin or len(vin) < 11:
        return []
    try:
        d = _get("https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
                 + urllib.parse.quote(vin) + "?format=json")
    except Exception:
        return []
    row = (d.get("Results") or [{}])[0]
    out = []
    for key, label in _NHTSA_FIELDS:
        v = (row.get(key) or "").strip()
        if v and v.lower() not in ("not applicable", "0", "none"):
            out.append((label, v))
    return out


# -------------------------------------------------------------------- engine family guess
# Common VAG families keyed by what the engine System Name / fuel tells us. Best-effort.
_PETROL_ENGINE = "Volkswagen EA211 engine"          # 1.0–1.5 TSI/MPI (has a good photo)
_DIESEL_ENGINE = "List of Volkswagen Group diesel engines"


def _displacement(system_name: str) -> float:
    import re
    m = re.search(r"(\d\.\d)\s*l", (system_name or "").lower())
    return float(m.group(1)) if m else 0.0


def _engine_queries(brand: str, system_name: str, fuel: str) -> list[str]:
    """Prefer a clean engine-family article (real engine-bay photo) over the generic list."""
    sn = (system_name or "").strip()
    up = sn.upper()
    disp = _displacement(sn)
    q = []
    if "TDI" in up or fuel == "diesel":
        q += [_DIESEL_ENGINE]
    else:
        # petrol family by displacement: EA888 for 1.8/2.0, EA211 for the small ones
        if disp >= 1.8 or any(x in up for x in ("1.8", "2.0", "TFSI")):
            q += ["Volkswagen EA888 engine", _PETROL_ENGINE]
        else:
            q += [_PETROL_ENGINE, "Volkswagen EA888 engine"]
        q += ["List of Volkswagen Group petrol engines"]
    if sn:                                        # last resort: exact string the ECU reported
        q += [f"{brand} {sn} engine", f"{sn} engine"]
    return q


# -------------------------------------------------------------------- main entry
def fetch(brand_display: str, model: str, vin: str = "", fuel: str = "",
          system_name: str = "", platform: str = "", family: str = "vag") -> CarInfo:
    """Fetch everything we can for this car. brand_display e.g. 'Volkswagen', 'SEAT', 'Audi'."""
    info = CarInfo()
    brand = (brand_display or "").strip()
    model = (model or "").strip()
    info.title = (f"{brand} {model}".strip()) or (vin or "Vehicle")

    # 1) structured specs from the VIN (works mainly for US-market cars)
    try:
        info.specs = nhtsa_specs(vin)
    except Exception as e:
        info.error = f"VIN decode unavailable ({e})"

    # 2) car photo + blurb — drive from make+model (no VIN leaves to Wikipedia)
    if brand or model:
        info.car = _first([f"{brand} {model}", model, brand])
        if info.car.title:
            info.title = info.car.title

    # 3) engine photo + blurb
    if family == "vag":
        info.engine = _first(_engine_queries(brand, system_name, fuel))
    elif brand or system_name:
        info.engine = _first([f"{brand} {system_name} engine".strip(), f"{system_name} engine".strip()])

    # 4) platform (nice-to-have, VAG only)
    if family == "vag":
        info.platform = _first([platform] if platform else ["Volkswagen Group MQB platform"])

    return info
