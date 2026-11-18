import CoreGraphics

/// Real-dimension proportions for the car artwork (mirrors tools/carart/geometry.py).
/// Wheels/arches stay rigid; overhangs, wheelbase, doors and glasshouse stretch to the real car.
struct CarGeometry {
    let sxIn: [CGFloat], sxOut: [CGFloat]
    let sd: CGFloat, sg: CGFloat, sshift: CGFloat
    let fd: CGFloat, fg: CGFloat, fshift: CGFloat
    let sideH: CGFloat, frontH: CGFloat, topAspect: CGFloat     // canvas heights; top: height / width

    /// length, width, height, wheelbase in mm (Wikipedia).
    init(_ L: CGFloat, _ W: CGFloat, _ H: CGFloat, _ WB: CGFloat) {
        let span: CGFloat = 968
        let oh = (L - WB) / L * span
        let fw = 14 + oh * 212 / 414
        let rw = fw + WB / L * span
        sxIn = [14, 134, 318, 690, 872, 982]
        sxOut = [14, fw - 92, fw + 92, rw - 92, rw + 92, 982]
        let hu = span * H / L
        sd = max(1, (0.60 * hu - 88) / 36)
        sg = max(0.6, (0.40 * hu) / 110)
        sshift = 40 - 186 + 36 * sd + 110 * sg
        sideH = 340 + sshift
        let fu = 486 * H / W
        fd = max(1, (0.60 * fu - 110) / 66)
        fg = max(0.6, (0.40 * fu) / 104)
        fshift = 56 - 226 + 66 * fd + 104 * fg
        frontH = 400 + fshift
        topAspect = (900.0 / 400.0) * (L / W) / (860.0 / 360.0)
    }

    func sideX(_ x: CGFloat) -> CGFloat {
        for i in 0..<(sxIn.count - 1) where x <= sxIn[i + 1] || i == sxIn.count - 2 {
            let t = (x - sxIn[i]) / (sxIn[i + 1] - sxIn[i])
            return sxOut[i] + t * (sxOut[i + 1] - sxOut[i])
        }
        return x
    }

    func sideY(_ y: CGFloat) -> CGFloat {
        if y >= 186 { return y + sshift }
        if y >= 150 { return 186 + sshift - (186 - y) * sd }
        return 186 + sshift - 36 * sd - (150 - y) * sg
    }

    func frontY(_ y: CGFloat) -> CGFloat {
        if y >= 226 { return y + fshift }
        if y >= 160 { return 226 + fshift - (226 - y) * fd }
        return 226 + fshift - 66 * fd - (160 - y) * fg
    }

    static let leon = CarGeometry(4263, 1810, 1446, 2636)
    static let ibiza = CarGeometry(4059, 1780, 1444, 2564)
    static let arona = CarGeometry(4138, 1780, 1552, 2566)
    static let grandI10 = CarGeometry(3765, 1660, 1520, 2425)
    static let i10 = CarGeometry(3645, 1660, 1500, 2385)

    /// Known models get their real proportions; others fall back to the closest body type.
    static func forModel(_ name: String, body: BodyType) -> CarGeometry {
        let n = name.lowercased()
        if n.contains("grand i10") { return .grandI10 }
        if n.contains("i10") { return .i10 }
        if n.contains("arona") { return .arona }
        if n.contains("ibiza") { return .ibiza }
        if n.contains("leon") || n.contains("león") { return .leon }
        switch body {
        case .suv, .van: return .arona
        case .hatch: return .ibiza
        default: return .leon
        }
    }
}
