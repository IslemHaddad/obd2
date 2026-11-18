"""Per-car proportions (real dimensions, mm) → remapping of the base artwork.
Mirrors Sources/UI/CarGeometry.swift. Wheels/arches stay rigid; overhangs, wheelbase and cabin stretch."""

DIMS = {   # length, width, height, wheelbase (Wikipedia)
    "ibiza": (4059, 1780, 1444, 2564),
    "arona": (4138, 1780, 1552, 2566),
    "leon": (4263, 1810, 1446, 2636),
    "grand i10": (3765, 1660, 1520, 2425),
    "i10": (3645, 1660, 1500, 2385),
}


def interp(x, xs, ys):
    for i in range(len(xs) - 1):
        if x <= xs[i + 1] or i == len(xs) - 2:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])


class Geo:
    def __init__(self, L, W, H, WB):
        # side: body spans x 14..982 (968 units = length)
        span = 968.0
        oh = (L - WB) / L * span
        fo = oh * 212 / (212 + 202)
        fw = 14 + fo
        rw = fw + WB / L * span
        self.sx_in = [14, 134, 318, 690, 872, 982]
        self.sx_out = [14, fw - 92, fw + 92, rw - 92, rw + 92, 982]
        self.fw, self.rw = fw, rw
        # side, vertical: ground..arch top (274..186) rigid; doors (186..150) and glass (150..40) stretch so the
        # window line sits at ~60 % of the real height (real cars), roof at the real height.
        hu = span * H / L
        self.sd = max(1.0, (0.60 * hu - 88) / 36)
        self.sg = max(0.6, (0.40 * hu) / 110)
        self.sshift = 40 - 186 + 36 * self.sd + 110 * self.sg
        self.side_h = 340 + self.sshift
        # front, vertical: bumper/grille (>=226) rigid; body between lights and glass (160..226) and glass (<160)
        fu = 486 * H / W
        self.fd = max(1.0, (0.60 * fu - 110) / 66)
        self.fg = max(0.6, (0.40 * fu) / 104)
        self.fshift = 56 - 226 + 66 * self.fd + 104 * self.fg
        self.front_h = 400 + self.fshift
        # top: body 360 wide x 860 long → aspect from real L/W
        self.top_h = 900 * (L / W) / (860 / 360)

    def side_x(self, x):
        return interp(x, self.sx_in, self.sx_out)

    def side_y(self, y):
        if y >= 186:
            return y + self.sshift
        if y >= 150:
            return 186 + self.sshift - (186 - y) * self.sd
        return 186 + self.sshift - 36 * self.sd - (150 - y) * self.sg

    def front_y(self, y):
        if y >= 226:
            return y + self.fshift
        if y >= 160:
            return 226 + self.fshift - (226 - y) * self.fd
        return 226 + self.fshift - 66 * self.fd - (160 - y) * self.fg


def for_model(name: str):
    n = name.lower()
    for k in ("grand i10", "i10", "arona", "ibiza", "leon"):
        if k in n:
            return Geo(*DIMS[k])
    return Geo(*DIMS["leon"])
