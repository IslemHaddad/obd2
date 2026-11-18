"""Parametric modern car outlines from real dimensions.
Side profile is built from landmark ratios of real modern cars (fractions of length / height), not a stretched drawing.
Coordinates: x right (front at left), y down; ground at y = GY."""
from dataclasses import dataclass


@dataclass
class Car:
    L: float      # mm
    W: float
    H: float
    WB: float
    body: str     # hatch | suv | sedan


def side(c: Car, scale=0.25):
    """Hatch/SUV profile landmarks measured from a real SEAT Ibiza KJ side view (fractions of length / height);
    the sedan keeps its own roof/boot. Real L/H come from each car's dimensions."""
    L, H = c.L * scale, c.H * scale
    pad = 10
    GY = H + pad + 6
    X0 = pad
    suv = c.body == "suv"
    sedan = c.body == "sedan"
    wr = (0.235 if suv else 0.224) * H
    # wheel placement: calibrated on the Ibiza (measured centres 16.5 % / 85.7 % of length vs spec WB/L 0.632)
    span = min(0.74, c.WB / c.L * 1.095)
    ff = (1 - span) * 0.535
    fw, rw = X0 + ff * L, X0 + (ff + span) * L
    cy = GY - wr
    y = lambda f: GY - f * H
    x = lambda f: X0 + f * L
    clr = 0.15 if suv else 0.116
    lift = 0.03 if suv else 0.0
    arch = wr * 1.12
    if sedan:
        roof = [("C", x(0.53), y(1.0), x(0.62), y(1.0), x(0.70), y(0.995)),
                ("C", x(0.75), y(0.99), x(0.79), y(0.94), x(0.84), y(0.82)),
                ("C", x(0.86), y(0.775), x(0.90), y(0.765), x(0.975), y(0.75)),
                ("C", x(0.99), y(0.745), x(1.0), y(0.70), x(1.0), y(0.62)),
                ("C", x(1.0), y(0.52), x(1.0), y(0.40), x(0.995), y(0.29))]
    else:
        roof = [("C", x(0.48), y(0.99), x(0.53), y(1.0), x(0.59), y(1.0)),
                ("C", x(0.66), y(1.0), x(0.73), y(1.0 if not suv else 1.0), x(0.78), y(0.996)),
                ("C", x(0.82), y(0.99), x(0.85), y(0.97), x(0.87), y(0.944)),               # spoiler
                ("C", x(0.90), y(0.89 if not suv else 0.91), x(0.93), y(0.82), x(0.95), y(0.763)),   # rear screen
                ("C", x(0.965), y(0.73), x(0.977), y(0.715), x(0.984), y(0.70)),
                ("C", x(0.995), y(0.60), x(1.0), y(0.45), x(1.0), y(0.29))]                # tail
    P = [("M", x(0.013), y(clr + 0.02)),
         ("C", x(-0.002), y(0.25 + lift), x(-0.004), y(0.38 + lift), x(0.0), y(0.44 + lift)),          # nose
         ("C", x(0.008), y(0.50 + lift), x(0.025), y(0.535 + lift), x(0.045), y(0.546 + lift)),       # headlight corner
         ("C", x(0.12), y(0.585 + lift), x(0.22), y(0.645 + lift / 2), x(0.278), y(0.677)),          # bonnet
         ("C", x(0.33), y(0.77), x(0.38), y(0.90), x(0.43), y(0.957)),                               # windscreen
         *roof,
         ("C", x(1.0), y(0.2), x(0.995), y(clr + 0.01), x(0.976), y(clr)),                            # rear bumper
         ("L", rw + arch, y(clr)),
         ("C", rw + arch, cy - arch * 0.55, rw + arch * 0.55, cy - arch, rw, cy - arch),
         ("C", rw - arch * 0.55, cy - arch, rw - arch, cy - arch * 0.55, rw - arch, y(clr)),
         ("L", fw + arch, y(clr)),
         ("C", fw + arch, cy - arch * 0.55, fw + arch * 0.55, cy - arch, fw, cy - arch),
         ("C", fw - arch * 0.55, cy - arch, fw - arch, cy - arch * 0.55, fw - arch, y(clr)),
         ("Z",)]
    if sedan:
        G = [("M", x(0.335), y(0.70)), ("C", x(0.37), y(0.80), x(0.40), y(0.89), x(0.435), y(0.935)),
             ("C", x(0.50), y(0.965), x(0.62), y(0.968), x(0.70), y(0.962)),
             ("C", x(0.75), y(0.95), x(0.78), y(0.88), x(0.81), y(0.715)),
             ("C", x(0.70), y(0.71), x(0.50), y(0.705), x(0.335), y(0.70)), ("Z",)]
        Cp = [("M", x(0.74), y(0.958)), ("C", x(0.76), y(0.93), x(0.785), y(0.86), x(0.81), y(0.715)),
              ("L", x(0.77), y(0.712)), ("Z",)]
    else:
        G = [("M", x(0.335), y(0.70)), ("C", x(0.37), y(0.80), x(0.40), y(0.89), x(0.435), y(0.935)),
             ("C", x(0.50), y(0.965), x(0.62), y(0.968), x(0.75), y(0.96)),
             ("C", x(0.80), y(0.955), x(0.83), y(0.93), x(0.85), y(0.89)),
             ("L", x(0.862), y(0.735)), ("C", x(0.70), y(0.725), x(0.50), y(0.71), x(0.335), y(0.70)), ("Z",)]
        Cp = [("M", x(0.80), y(0.955)), ("C", x(0.83), y(0.93), x(0.845), y(0.90), x(0.85), y(0.89)),
              ("L", x(0.862), y(0.735)), ("L", x(0.82), y(0.731)), ("Z",)]
    Bp = [("M", x(0.567), y(0.968)), ("L", x(0.582), y(0.968)), ("L", x(0.578), y(0.712)), ("L", x(0.563), y(0.712)), ("Z",)]
    shoulder = [("M", x(0.08), y(0.53 + lift)), ("C", x(0.40), y(0.58), x(0.70), y(0.64), x(0.965), y(0.69))]
    crease = [("M", fw + arch * 1.05, y(0.30 + lift)), ("C", x(0.45), y(0.30 + lift), x(0.62), y(0.31 + lift), rw - arch * 1.05, y(0.33 + lift))]
    head = [("M", x(0.004), y(0.47 + lift)), ("C", x(0.02), y(0.53 + lift), x(0.06), y(0.555 + lift), x(0.12), y(0.565 + lift)),
            ("L", x(0.115), y(0.53 + lift)), ("C", x(0.07), y(0.515 + lift), x(0.035), y(0.49 + lift), x(0.01), y(0.43 + lift)), ("Z",)]
    drl = [("M", x(0.012), y(0.475 + lift)), ("C", x(0.035), y(0.53 + lift), x(0.07), y(0.545 + lift), x(0.11), y(0.55 + lift))]
    if sedan:
        tail = [("M", x(0.94), y(0.73)), ("C", x(0.965), y(0.73), x(0.99), y(0.72), x(0.998), y(0.70)),
                ("L", x(0.999), y(0.64)), ("C", x(0.975), y(0.655), x(0.955), y(0.66), x(0.935), y(0.665)), ("Z",)]
    else:
        tail = [("M", x(0.905), y(0.745)), ("C", x(0.94), y(0.745), x(0.975), y(0.72), x(0.99), y(0.69)),
                ("L", x(0.997), y(0.62)), ("C", x(0.97), y(0.64), x(0.935), y(0.665), x(0.90), y(0.685)), ("Z",)]
    mirror = [("M", x(0.355), y(0.665)), ("C", x(0.36), y(0.71), x(0.39), y(0.725), x(0.42), y(0.712)),
              ("L", x(0.415), y(0.675)), ("C", x(0.395), y(0.66), x(0.37), y(0.655), x(0.355), y(0.665)), ("Z",)]
    sill = [("M", fw + arch * 1.1, y(clr + 0.055)), ("L", rw - arch * 1.1, y(clr + 0.055))]
    handles = [("M", x(0.49), y(0.62)), ("L", x(0.535), y(0.62)), ("M", x(0.72), y(0.64)), ("L", x(0.765), y(0.64))]
    cladding = [("M", fw - arch, y(clr)), ("C", fw - arch, cy - arch * 0.55, fw - arch * 0.55, cy - arch, fw, cy - arch),
                ("C", fw + arch * 0.55, cy - arch, fw + arch, cy - arch * 0.55, fw + arch, y(clr))] if suv else []
    return {"W": X0 * 2 + L, "H": GY + 8, "ground": GY, "body": P, "glass": G, "c_pillar": Cp, "b_pillar": Bp,
            "shoulder": shoulder, "crease": crease, "headlight": head, "drl": drl, "taillight": tail, "mirror": mirror,
            "sill": sill, "handles": handles, "wheels": [(fw, cy, wr), (rw, cy, wr)], "cladding": cladding, "suv": suv}


def front(c: Car, scale=0.25, grille="seat"):
    W, H = c.W * scale, c.H * scale
    pad = 34
    X0, GY = pad, H + 12
    x = lambda f: X0 + f * W
    y = lambda f: GY - f * H
    suv = c.body == "suv"
    clr = 0.12 if suv else 0.09
    body = [("M", x(0.04), y(clr)),
            ("C", x(0.0), y(clr + 0.1), x(-0.005), y(0.45), x(0.015), y(0.58)),          # side of bumper / wing
            ("C", x(0.03), y(0.64), x(0.08), y(0.66), x(0.13), y(0.665)),                 # shoulder
            ("C", x(0.17), y(0.78), x(0.21), y(0.93), x(0.27), y(0.985)),                 # A-pillar (tumblehome)
            ("C", x(0.40), y(1.005), x(0.60), y(1.005), x(0.73), y(0.985)),               # roof
            ("C", x(0.79), y(0.93), x(0.83), y(0.78), x(0.87), y(0.665)),
            ("C", x(0.92), y(0.66), x(0.97), y(0.64), x(0.985), y(0.58)),
            ("C", x(1.005), y(0.45), x(1.0), y(clr + 0.1), x(0.96), y(clr)), ("Z",)]
    glass = [("M", x(0.16), y(0.665)), ("C", x(0.20), y(0.78), x(0.235), y(0.9), x(0.285), y(0.95)),
             ("C", x(0.42), y(0.965), x(0.58), y(0.965), x(0.715), y(0.95)),
             ("C", x(0.765), y(0.9), x(0.80), y(0.78), x(0.84), y(0.665)), ("C", x(0.65), y(0.675), x(0.35), y(0.675), x(0.16), y(0.665)), ("Z",)]
    hl = lambda s: [("M", x(s(0.035)), y(0.565)), ("C", x(s(0.10)), y(0.60), x(s(0.20)), y(0.605), x(s(0.30)), y(0.585)),
                    ("L", x(s(0.29)), y(0.54)), ("C", x(s(0.20)), y(0.535), x(s(0.10)), y(0.52), x(s(0.045)), y(0.50)), ("Z",)]
    L_ = lambda f: f
    R_ = lambda f: 1 - f
    drl = lambda s: [("M", x(s(0.05)), y(0.555)), ("L", x(s(0.27)), y(0.575)), ("L", x(s(0.245)), y(0.545))]
    grilles = {
        "seat": [("M", x(0.33), y(0.53)), ("L", x(0.67), y(0.53)), ("L", x(0.72), y(0.36)),
                 ("C", x(0.62), y(0.33), x(0.38), y(0.33), x(0.28), y(0.36)), ("Z",)],
        "hyundai": [("M", x(0.31), y(0.52)), ("L", x(0.69), y(0.52)), ("C", x(0.70), y(0.42), x(0.66), y(0.33), x(0.60), y(0.31)),
                    ("L", x(0.40), y(0.31)), ("C", x(0.34), y(0.33), x(0.30), y(0.42), x(0.31), y(0.52)), ("Z",)],
        "renault": [("M", x(0.30), y(0.53)), ("L", x(0.70), y(0.53)), ("C", x(0.71), y(0.49), x(0.70), y(0.46), x(0.68), y(0.455)),
                    ("L", x(0.32), y(0.455)), ("C", x(0.30), y(0.46), x(0.29), y(0.49), x(0.30), y(0.53)), ("Z",),
                    ("M", x(0.5), y(0.555)), ("L", x(0.525), y(0.49)), ("L", x(0.5), y(0.425)), ("L", x(0.475), y(0.49)), ("Z",)],
        "kia": [("M", x(0.38), y(0.50)), ("C", x(0.45), y(0.53), x(0.55), y(0.53), x(0.62), y(0.50)),
                ("C", x(0.60), y(0.45), x(0.40), y(0.45), x(0.38), y(0.50)), ("Z",)],
    }
    intake = lambda s: [("M", x(s(0.06)), y(0.34)), ("L", x(s(0.22)), y(0.30)), ("L", x(s(0.23)), y(0.22)),
                        ("L", x(s(0.07)), y(0.22)), ("Z",)]
    lower = [("M", x(0.30), y(0.25)), ("L", x(0.70), y(0.25)), ("L", x(0.66), y(clr + 0.03)), ("L", x(0.34), y(clr + 0.03)), ("Z",)]
    mirror = lambda s: [("M", x(s(0.135)), y(0.68)), ("C", x(s(0.09)), y(0.70), x(s(0.03)), y(0.70), x(s(-0.01)), y(0.675)),
                        ("C", x(s(0.0)), y(0.645), x(s(0.08)), y(0.64), x(s(0.14)), y(0.65)), ("Z",)]
    tyres = [(x(0.03), GY - 0.16 * H, 0.13 * W, 0.16 * H), (x(0.84), GY - 0.16 * H, 0.13 * W, 0.16 * H)]
    return {"W": W + 2 * X0, "H": GY + 10, "ground": GY, "body": body, "glass": glass,
            "headlight_l": hl(L_), "headlight_r": hl(R_), "drl_l": drl(L_), "drl_r": drl(R_),
            "grille": grilles.get(grille, grilles["seat"]), "intake_l": intake(L_), "intake_r": intake(R_),
            "lower": lower, "mirror_l": mirror(L_), "mirror_r": mirror(R_), "tyres": tyres,
            "badge": (x(0.5), y(0.44))}


CARS = {
    "Renault Clio IV": (Car(4062, 1732, 1448, 2589, "hatch"), "#F2B705", "renault", "RENAULT"),
    "Renault Captur": (Car(4122, 1778, 1567, 2606, "suv"), "#E8601C", "renault", "RENAULT"),
    "Renault Symbol": (Car(4346, 1733, 1517, 2634, "sedan"), "#B8BCC4", "renault", "RENAULT"),
    "SEAT Leon (5F)": (Car(4263, 1810, 1446, 2636, "hatch"), "#C8102E", "seat", "SEAT"),
    "SEAT Ibiza (KJ)": (Car(4059, 1780, 1444, 2564, "hatch"), "#C8102E", "seat", "SEAT"),
    "SEAT Arona": (Car(4138, 1780, 1552, 2566, "suv"), "#C8102E", "seat", "SEAT"),
    "Hyundai Grand i10": (Car(3765, 1660, 1520, 2425, "hatch"), "#1F6FB2", "hyundai", "HYUNDAI"),
}
