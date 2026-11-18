import Combine
import SwiftUI

/// Per-car drawing parameters derived from brand + model (drawn, not photos).
struct CarArt {
    let color: Color
    let body: BodyType
    let brand: String
    let model: String
    let roofHeight: CGFloat      // 0…1 relative to car height in side/front views
    let twoTone: Bool            // contrasting roof (e.g. Arona / Venue)
    let grille: Grille
    enum Grille { case seat, hyundai, kia, vw, generic }

    init(_ v: SelectedVehicle) {
        color = v.brand.color
        body = v.model.body
        brand = v.brand.rawValue.uppercased()
        model = v.model.name
        let n = v.model.name.lowercased()
        twoTone = ["arona", "venue", "kona", "t-cross", "kamiq", "sonet"].contains { n.contains($0) }
        switch v.model.body {
        case .suv: roofHeight = 0.62
        case .van: roofHeight = 0.70
        case .coupe: roofHeight = 0.48
        case .sedan, .estate: roofHeight = 0.52
        case .hatch: roofHeight = n.contains("i10") || n.contains("picanto") || n.contains("up") ? 0.60 : 0.55
        }
        switch v.brand {
        case .seat, .cupra: grille = .seat
        case .hyundai: grille = .hyundai
        case .kia: grille = .kia
        case .vw, .skoda, .audi: grille = .vw
        default: grille = .generic
        }
    }
}

// MARK: - Side profile

struct CarSideView: View {
    let art: CarArt
    var body: some View {
        Canvas { ctx, size in
            let w = size.width, h = size.height
            let ground = h * 0.86
            let wheelR = h * 0.13
            let len: CGFloat = art.body == .hatch ? 0.80 : art.body == .suv ? 0.84 : 0.90
            let x0 = (w - w * len) / 2, x1 = x0 + w * len
            let beltY = ground - h * 0.30
            let roofY = ground - h * art.roofHeight
            let frontWheel = x0 + w * len * 0.18, rearWheel = x1 - w * len * (art.body == .hatch ? 0.16 : 0.19)
            // body
            var bodyP = Path()
            bodyP.move(to: CGPoint(x: x0, y: ground - wheelR * 0.6))
            bodyP.addQuadCurve(to: CGPoint(x: x0 + w * 0.02, y: beltY), control: CGPoint(x: x0 - w * 0.01, y: beltY + h * 0.04))
            bodyP.addLine(to: CGPoint(x: x0 + w * len * 0.30, y: beltY - h * 0.03))                       // bonnet
            bodyP.addLine(to: CGPoint(x: x0 + w * len * 0.45, y: roofY))                                  // windscreen
            let roofEnd = art.body == .hatch || art.body == .suv || art.body == .van ? x1 - w * len * 0.08 : x1 - w * len * 0.22
            bodyP.addLine(to: CGPoint(x: roofEnd, y: roofY + h * 0.01))
            if art.body == .sedan || art.body == .coupe {
                bodyP.addLine(to: CGPoint(x: x1 - w * len * 0.08, y: beltY - h * 0.02))              // boot
                bodyP.addLine(to: CGPoint(x: x1, y: beltY))
            } else {
                bodyP.addQuadCurve(to: CGPoint(x: x1, y: beltY + h * 0.02), control: CGPoint(x: x1 + w * 0.005, y: roofY + h * 0.05))
            }
            bodyP.addLine(to: CGPoint(x: x1, y: ground - wheelR * 0.6))
            bodyP.closeSubpath()
            ctx.fill(bodyP, with: .linearGradient(Gradient(colors: [art.color.opacity(0.95), art.color.opacity(0.6)]),
                                                  startPoint: CGPoint(x: 0, y: roofY), endPoint: CGPoint(x: 0, y: ground)))
            ctx.stroke(bodyP, with: .color(.white.opacity(0.25)), lineWidth: 1)
            if art.twoTone {
                var roof = Path()
                roof.addRect(CGRect(x: x0 + w * len * 0.45, y: roofY, width: roofEnd - (x0 + w * len * 0.45), height: h * 0.025))
                ctx.fill(roof, with: .color(.black.opacity(0.75)))
            }
            // windows
            var win = Path()
            win.move(to: CGPoint(x: x0 + w * len * 0.33, y: beltY - h * 0.035))
            win.addLine(to: CGPoint(x: x0 + w * len * 0.46, y: roofY + h * 0.03))
            win.addLine(to: CGPoint(x: roofEnd - w * 0.02, y: roofY + h * 0.035))
            win.addLine(to: CGPoint(x: roofEnd + w * 0.01, y: beltY - h * 0.035))
            win.closeSubpath()
            ctx.fill(win, with: .color(.black.opacity(0.55)))
            var pillar = Path()
            pillar.addRect(CGRect(x: x0 + w * len * 0.62, y: roofY + h * 0.03, width: w * 0.012, height: beltY - roofY - h * 0.06))
            ctx.fill(pillar, with: .color(art.color.opacity(0.9)))
            // lights
            ctx.fill(Path(roundedRect: CGRect(x: x0 + w * 0.005, y: beltY + h * 0.01, width: w * 0.05, height: h * 0.035), cornerRadius: 3),
                     with: .color(.white.opacity(0.9)))
            ctx.fill(Path(roundedRect: CGRect(x: x1 - w * 0.035, y: beltY + h * 0.01, width: w * 0.03, height: h * 0.04), cornerRadius: 3),
                     with: .color(.red))
            // wheels
            for cx in [frontWheel, rearWheel] {
                let c = CGPoint(x: cx, y: ground - wheelR)
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - wheelR, y: c.y - wheelR, width: wheelR * 2, height: wheelR * 2)), with: .color(.black))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - wheelR * 0.6, y: c.y - wheelR * 0.6, width: wheelR * 1.2, height: wheelR * 1.2)),
                         with: .color(Color(white: 0.55)))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - wheelR * 0.15, y: c.y - wheelR * 0.15, width: wheelR * 0.3, height: wheelR * 0.3)),
                         with: .color(Color(white: 0.25)))
            }
            // ground shadow
            ctx.fill(Path(ellipseIn: CGRect(x: x0, y: ground - 3, width: x1 - x0, height: 8)), with: .color(.black.opacity(0.35)))
        }
    }
}

// MARK: - Front view

struct CarFrontView: View {
    let art: CarArt
    var body: some View {
        Canvas { ctx, size in
            let w = size.width, h = size.height
            let cw = min(w * 0.7, h * 1.15)
            let x0 = (w - cw) / 2
            let ground = h * 0.88
            let roofY = ground - h * art.roofHeight * 0.95
            let beltY = ground - h * 0.34
            // tyres
            for side in [0.0, 1.0] {
                ctx.fill(Path(roundedRect: CGRect(x: x0 + cw * (side == 0 ? 0.04 : 0.80), y: ground - h * 0.1, width: cw * 0.16, height: h * 0.12),
                              cornerRadius: 6), with: .color(.black))
            }
            // body
            var b = Path()
            b.move(to: CGPoint(x: x0, y: ground - h * 0.05))
            b.addLine(to: CGPoint(x: x0 + cw * 0.02, y: beltY))
            b.addLine(to: CGPoint(x: x0 + cw * 0.14, y: roofY + h * 0.02))
            b.addQuadCurve(to: CGPoint(x: x0 + cw * 0.86, y: roofY + h * 0.02), control: CGPoint(x: x0 + cw * 0.5, y: roofY - h * 0.02))
            b.addLine(to: CGPoint(x: x0 + cw * 0.98, y: beltY))
            b.addLine(to: CGPoint(x: x0 + cw, y: ground - h * 0.05))
            b.closeSubpath()
            ctx.fill(b, with: .linearGradient(Gradient(colors: [art.color, art.color.opacity(0.6)]),
                                              startPoint: CGPoint(x: x0, y: 0), endPoint: CGPoint(x: x0 + cw, y: 0)))
            if art.twoTone {
                ctx.fill(Path(roundedRect: CGRect(x: x0 + cw * 0.16, y: roofY, width: cw * 0.68, height: h * 0.03), cornerRadius: 4),
                         with: .color(.black.opacity(0.75)))
            }
            // windscreen
            var ws = Path()
            ws.move(to: CGPoint(x: x0 + cw * 0.12, y: beltY - h * 0.02))
            ws.addLine(to: CGPoint(x: x0 + cw * 0.2, y: roofY + h * 0.05))
            ws.addLine(to: CGPoint(x: x0 + cw * 0.8, y: roofY + h * 0.05))
            ws.addLine(to: CGPoint(x: x0 + cw * 0.88, y: beltY - h * 0.02))
            ws.closeSubpath()
            ctx.fill(ws, with: .color(.black.opacity(0.6)))
            // headlights
            let hlY = beltY + h * 0.05
            for side in [0.0, 1.0] {
                let r = CGRect(x: x0 + cw * (side == 0 ? 0.06 : 0.72), y: hlY, width: cw * 0.22, height: h * 0.06)
                ctx.fill(Path(roundedRect: r.insetBy(dx: -3, dy: -3), cornerRadius: 8), with: .color(.white.opacity(0.25)))
                ctx.fill(Path(roundedRect: r, cornerRadius: 6), with: .color(.white.opacity(0.95)))
            }
            // grille per brand
            let g = CGRect(x: x0 + cw * 0.32, y: hlY + h * 0.06, width: cw * 0.36, height: h * 0.14)
            switch art.grille {
            case .hyundai:   // cascading grille
                var p = Path()
                p.move(to: CGPoint(x: g.minX, y: g.minY)); p.addLine(to: CGPoint(x: g.maxX, y: g.minY))
                p.addLine(to: CGPoint(x: g.maxX - g.width * 0.12, y: g.maxY)); p.addLine(to: CGPoint(x: g.minX + g.width * 0.12, y: g.maxY))
                p.closeSubpath()
                ctx.fill(p, with: .color(.black.opacity(0.85)))
            case .kia:        // tiger nose
                ctx.fill(Path(roundedRect: g.insetBy(dx: 0, dy: g.height * 0.2), cornerRadius: g.height * 0.3), with: .color(.black.opacity(0.85)))
            case .seat:       // trapezoid with mesh
                var p = Path()
                p.move(to: CGPoint(x: g.minX + g.width * 0.08, y: g.minY)); p.addLine(to: CGPoint(x: g.maxX - g.width * 0.08, y: g.minY))
                p.addLine(to: CGPoint(x: g.maxX, y: g.maxY)); p.addLine(to: CGPoint(x: g.minX, y: g.maxY)); p.closeSubpath()
                ctx.fill(p, with: .color(.black.opacity(0.85)))
            case .vw, .generic:
                ctx.fill(Path(roundedRect: g.insetBy(dx: 0, dy: g.height * 0.3), cornerRadius: 4), with: .color(.black.opacity(0.85)))
            }
            // badge
            ctx.draw(Text(art.brand).font(.system(size: max(8, cw * 0.04), weight: .heavy, design: .rounded)).foregroundColor(.white),
                     at: CGPoint(x: g.midX, y: g.minY - h * 0.02))
            // shadow
            ctx.fill(Path(ellipseIn: CGRect(x: x0, y: ground - 2, width: cw, height: 8)), with: .color(.black.opacity(0.35)))
        }
    }
}

// MARK: - Showcase shown while scanning: 3 visuals rotating with a scan sweep

struct ScanShowcase: View {
    let vehicle: SelectedVehicle
    let progress: Double
    let status: String
    @State private var page = 0
    @State private var sweep = false
    private let timer = Timer.publish(every: 2.6, on: .main, in: .common).autoconnect()

    var body: some View {
        let art = CarArt(vehicle)
        VStack(spacing: 12) {
            TabView(selection: $page) {
                CarSideView(art: art).padding(20).tag(0)
                CarFrontView(art: art).padding(20).tag(1)
                CarTopView(color: art.color, body: art.body)
                    .frame(width: 150, height: 150 * art.body.aspect).rotationEffect(.degrees(90))
                    .frame(maxWidth: .infinity, maxHeight: .infinity).tag(2)
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .frame(height: 230)
            .overlay {
                GeometryReader { g in
                    LinearGradient(colors: [.clear, art.color.opacity(0.55), .white.opacity(0.7), art.color.opacity(0.55), .clear],
                                   startPoint: .leading, endPoint: .trailing)
                        .frame(width: 70)
                        .blur(radius: 6)
                        .offset(x: sweep ? g.size.width : -70)
                        .blendMode(.screen)
                        .allowsHitTesting(false)
                }
                .clipped()
            }
            .background(RadialGradient(colors: [art.color.opacity(0.25), .clear], center: .center, startRadius: 10, endRadius: 220))
            VStack(spacing: 6) {
                Text("\(art.brand) \(art.model)").font(.headline)
                ProgressView(value: progress).tint(art.color)
                Text(status).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            .padding(.horizontal, 24)
        }
        .onAppear { withAnimation(.linear(duration: 1.6).repeatForever(autoreverses: false)) { sweep = true } }
        .onReceive(timer) { _ in withAnimation(.easeInOut(duration: 0.6)) { page = (page + 1) % 3 } }
    }
}

/// Static 3-view gallery (side / front / top) for the vehicle header.
struct CarGallery: View {
    let vehicle: SelectedVehicle
    var body: some View {
        let art = CarArt(vehicle)
        TabView {
            CarSideView(art: art).padding(16)
            CarFrontView(art: art).padding(16)
            CarTopView(color: art.color, body: art.body)
                .frame(width: 120, height: 120 * art.body.aspect).rotationEffect(.degrees(90))
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .tabViewStyle(.page(indexDisplayMode: .always))
        .frame(height: 190)
    }
}
