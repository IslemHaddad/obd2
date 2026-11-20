"""VW Group catalog: brands, models, control modules (ported from the iOS app)."""

BRANDS = {  # key: (display, colour, [(model, body)])
    "seat": ("SEAT", "#DB1F29", [('Ibiza', 'hatch'), ('Leon', 'hatch'), ('Leon Sportstourer', 'estate'), ('Arona', 'suv'), ('Ateca', 'suv'), ('Tarraco', 'suv'), ('Alhambra', 'van'), ('Toledo', 'sedan'), ('Mii', 'hatch'), ('Altea', 'van'), ('Exeo', 'sedan')]),
    "cupra": ("CUPRA", "#B8734A", [('Born', 'hatch'), ('Formentor', 'suv'), ('Leon', 'hatch'), ('Ateca', 'suv'), ('Tavascan', 'suv'), ('Terramar', 'suv')]),
    "vw": ("Volkswagen", "#00479A", [('Up!', 'hatch'), ('Polo', 'hatch'), ('Golf', 'hatch'), ('Golf Variant', 'estate'), ('Golf Plus', 'van'), ('Jetta', 'sedan'), ('Passat', 'sedan'), ('Passat Variant', 'estate'), ('Arteon', 'coupe'), ('Scirocco', 'coupe'), ('Beetle', 'coupe'), ('Taigo', 'suv'), ('T-Cross', 'suv'), ('T-Roc', 'suv'), ('Tiguan', 'suv'), ('Touareg', 'suv'), ('Touran', 'van'), ('Sharan', 'van'), ('Caddy', 'van'), ('Transporter', 'van'), ('Amarok', 'suv'), ('ID.3', 'hatch'), ('ID.4', 'suv'), ('ID.5', 'suv'), ('ID.7', 'sedan'), ('ID. Buzz', 'van')]),
    "audi": ("Audi", "#BFBFBF", [('A1', 'hatch'), ('A3', 'hatch'), ('A4', 'sedan'), ('A4 Avant', 'estate'), ('A5', 'coupe'), ('A6', 'sedan'), ('A6 Avant', 'estate'), ('A7', 'coupe'), ('A8', 'sedan'), ('Q2', 'suv'), ('Q3', 'suv'), ('Q4 e-tron', 'suv'), ('Q5', 'suv'), ('Q7', 'suv'), ('Q8', 'suv'), ('e-tron GT', 'coupe'), ('TT', 'coupe'), ('R8', 'coupe')]),
    "skoda": ("Škoda", "#4FA83D", [('Citigo', 'hatch'), ('Fabia', 'hatch'), ('Rapid', 'sedan'), ('Scala', 'hatch'), ('Octavia', 'sedan'), ('Octavia Combi', 'estate'), ('Superb', 'sedan'), ('Superb Combi', 'estate'), ('Kamiq', 'suv'), ('Karoq', 'suv'), ('Kodiaq', 'suv'), ('Yeti', 'suv'), ('Roomster', 'van'), ('Enyaq', 'suv'), ('Elroq', 'suv')]),
    "porsche": ("Porsche", "#CC9933", [('911', 'coupe'), ('718', 'coupe'), ('Panamera', 'sedan'), ('Taycan', 'sedan'), ('Macan', 'suv'), ('Cayenne', 'suv')]),
    "bentley": ("Bentley", "#1A5940", [('Continental GT', 'coupe'), ('Flying Spur', 'sedan'), ('Bentayga', 'suv')]),
    "lamborghini": ("Lamborghini", "#F2BF1A", [('Huracán', 'coupe'), ('Revuelto', 'coupe'), ('Urus', 'suv')]),
    "hyundai": ("Hyundai", "#1F6FB2", [("i10", "hatch"), ("Grand i10", "hatch"), ("Grand i10 Nios", "hatch"),
                                     ("Grand i10 Sedan / Xcent", "sedan"), ("i20", "hatch"), ("Accent", "sedan"),
                                     ("Elantra", "sedan"), ("Venue", "suv"), ("Creta", "suv"), ("Kona", "suv"),
                                     ("Tucson", "suv"), ("Santa Fe", "suv"), ("Ioniq", "hatch"), ("Ioniq 5", "suv")]),
    "kia": ("Kia", "#BB162B", [("Picanto", "hatch"), ("Rio", "hatch"), ("Ceed", "hatch"), ("Sonet", "suv"),
                             ("Seltos", "suv"), ("Sportage", "suv"), ("Sorento", "suv"), ("Niro", "suv"),
                             ("EV6", "suv")]),
    "renault": ("Renault", "#F2B705", [("Clio IV", "hatch"), ("Clio V", "hatch"), ("Captur", "suv"), ("Mégane", "hatch"),
                                     ("Symbol", "sedan"), ("Kadjar", "suv"), ("Austral", "suv"), ("Arkana", "suv"),
                                     ("Duster", "suv"), ("Twingo", "hatch"), ("Kangoo", "van"), ("Scénic", "van"),
                                     ("Talisman", "sedan")]),
}

FAMILY = {k: "vag" for k in ("seat", "cupra", "vw", "audi", "skoda", "porsche", "bentley", "lamborghini")}
FAMILY.update(hyundai="hyundai", kia="hyundai", renault="renault")

WMI = {
    "KMH": "hyundai", "MAL": "hyundai", "NLH": "hyundai", "TMA": "hyundai", "5NP": "hyundai", "5NM": "hyundai",
    "KM8": "hyundai", "MAJ": "hyundai", "KNA": "kia", "KNC": "kia", "KND": "kia", "U5Y": "kia", "U6Y": "kia",
    "MZB": "kia", "5XY": "kia", "3KP": "kia",
    "VF1": "renault", "8A1": "renault", "93Y": "renault", "X7L": "renault", "MEE": "renault", "KNM": "renault",
    "VSS": "seat", "WVW": "vw", "WVG": "vw", "WV1": "vw", "WV2": "vw", "1VW": "vw", "3VW": "vw", "9BW": "vw",
    "LSV": "vw", "LFV": "vw", "XW8": "vw", "AAV": "vw", "WAU": "audi", "WUA": "audi", "TRU": "audi", "WA1": "audi",
    "TMB": "skoda", "TMP": "skoda", "WP0": "porsche", "WP1": "porsche", "SCB": "bentley", "SJA": "bentley",
    "ZHW": "lamborghini",
}

BODY_ASPECT = {"hatch": 2.15, "sedan": 2.45, "estate": 2.5, "suv": 2.25, "coupe": 2.35, "van": 2.55}

# Drag area CdA (Cd × frontal area, m²) by body, for the Power Run crank-power estimate.
CDA_BY_BODY = {"hatch": 0.65, "sedan": 0.64, "estate": 0.70, "coupe": 0.60, "suv": 0.90, "van": 1.05}


def body_for(brand: str, model: str) -> str:
    for m, body in BRANDS.get(brand, ("", "", []))[2]:
        if m == model:
            return body
    return "hatch"


def cda_for(brand: str, model: str) -> float:
    return CDA_BY_BODY.get(body_for(brand, model), 0.65)

CATEGORY_COLOR = {"powertrain": "#FF9F0A", "chassis": "#FF9F0A", "safety": "#FF453A", "electronics": "#FFD60A"}

MODULES = [  # (address, name, request, response, category, x, y)
    ("01", "Engine Electronics", "7E0", "7E8", "powertrain", 0.5, 0.14),
    ("02", "Transmission", "7E1", "7E9", "powertrain", 0.5, 0.27),
    ("03", "Brakes / ABS", "713", "77D", "chassis", 0.27, 0.2),
    ("44", "Steering Assist", "712", "77C", "chassis", 0.7, 0.22),
    ("08", "Air Conditioning", "746", "7B0", "electronics", 0.5, 0.41),
    ("09", "Central Electrics", "70E", "778", "electronics", 0.2, 0.42),
    ("15", "Airbags", "715", "77F", "safety", 0.5, 0.5),
    ("16", "Steering Column Electr.", "70C", "776", "electronics", 0.33, 0.41),
    ("17", "Instruments", "714", "77E", "electronics", 0.33, 0.34),
    ("19", "Gateway", "710", "77A", "electronics", 0.66, 0.44),
    ("5F", "Infotainment", "773", "7DD", "electronics", 0.5, 0.34),
    ("42", "Driver Door", "74A", "7B4", "electronics", 0.06, 0.5),
    ("52", "Passenger Door", "74B", "7B5", "electronics", 0.94, 0.5),
]
