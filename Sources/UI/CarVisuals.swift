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

// MARK: - Side profile (modern hatch, Leon-5F style; paths in CarArtPaths, generated from tools/carart)

struct CarSideView: View {
    let art: CarArt
    var body: some View {
        Canvas { ctx, size in
            let k = CarArtPaths.sideSize.width / CarArtPaths.sideSize.height
            let w = min(size.width, size.height * k), h = w / k
            let r = CGRect(x: (size.width - w) / 2, y: (size.height - h) / 2, width: w, height: h)
            let sx = w / CarArtPaths.sideSize.width, sy = h / CarArtPaths.sideSize.height
            ctx.fill(Path(ellipseIn: CGRect(x: r.minX + 30 * sx, y: r.minY + 272 * sy, width: 940 * sx, height: 26 * sy)),
                     with: .color(.black.opacity(0.45)))
            ctx.fill(CarArtPaths.sideBody(r), with: .linearGradient(Gradient(colors: [art.color.opacity(0.95), art.color, art.color.opacity(0.55)]),
                                                                    startPoint: CGPoint(x: 0, y: r.minY + 40 * sy), endPoint: CGPoint(x: 0, y: r.minY + 280 * sy)))
            ctx.stroke(CarArtPaths.sideBody(r), with: .color(.white.opacity(0.18)), lineWidth: 1)
            ctx.fill(CarArtPaths.sideGlass(r), with: .linearGradient(Gradient(colors: [Color(white: 0.35), Color(white: 0.06)]),
                                                                     startPoint: CGPoint(x: 0, y: r.minY + 50 * sy), endPoint: CGPoint(x: 0, y: r.minY + 150 * sy)))
            ctx.fill(CarArtPaths.sideCPillar(r), with: .color(Color(white: 0.04)))
            ctx.fill(CarArtPaths.sideBPillar(r), with: .color(Color(white: 0.04)))
            if art.twoTone { ctx.stroke(CarArtPaths.sideCPillar(r), with: .color(.black), lineWidth: 3) }
            ctx.fill(CarArtPaths.sideMirror(r), with: .color(art.color.opacity(0.8)))
            ctx.fill(CarArtPaths.sideHeadlight(r), with: .color(.white.opacity(0.95)))
            ctx.fill(CarArtPaths.sideTaillight(r), with: .color(.red))
            ctx.stroke(CarArtPaths.sideShoulder(r), with: .color(.white.opacity(0.4)), lineWidth: 1.5)
            ctx.stroke(CarArtPaths.sideSill(r), with: .color(.black.opacity(0.35)), lineWidth: 2)
            ctx.stroke(CarArtPaths.sideDrl(r), with: .color(Color(red: 0.7, green: 0.95, blue: 1)), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
            ctx.stroke(CarArtPaths.sideHandle(r), with: .color(.black.opacity(0.45)), style: StrokeStyle(lineWidth: 2, lineCap: .round))
            for wh in CarArtPaths.sideWheels {
                let c = CGPoint(x: r.minX + wh[0] * sx, y: r.minY + wh[1] * sy)
                let rad = wh[2] * sy
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - rad, y: c.y - rad, width: rad * 2, height: rad * 2)), with: .color(Color(white: 0.05)))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - rad * 0.66, y: c.y - rad * 0.66, width: rad * 1.32, height: rad * 1.32)),
                         with: .color(Color(white: 0.7)))
                var spokes = Path()
                for i in 0..<10 {
                    let ang = Double(i) * .pi / 5
                    spokes.move(to: CGPoint(x: c.x + cos(ang) * rad * 0.14, y: c.y + sin(ang) * rad * 0.14))
                    spokes.addLine(to: CGPoint(x: c.x + cos(ang + 0.18) * rad * 0.62, y: c.y + sin(ang + 0.18) * rad * 0.62))
                }
                ctx.stroke(spokes, with: .color(Color(white: 0.18)), style: StrokeStyle(lineWidth: max(1.5, rad * 0.09), lineCap: .round))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - rad * 0.13, y: c.y - rad * 0.13, width: rad * 0.26, height: rad * 0.26)),
                         with: .color(Color(white: 0.25)))
            }
        }
    }
}

// MARK: - Front view (full-LED triangle lights, brand grille)

struct CarFrontView: View {
    let art: CarArt
    var body: some View {
        Canvas { ctx, size in
            let k = CarArtPaths.frontSize.width / CarArtPaths.frontSize.height
            let w = min(size.width, size.height * k), h = w / k
            let r = CGRect(x: (size.width - w) / 2, y: (size.height - h) / 2, width: w, height: h)
            let sx = w / CarArtPaths.frontSize.width, sy = h / CarArtPaths.frontSize.height
            ctx.fill(Path(ellipseIn: CGRect(x: r.minX + 30 * sx, y: r.minY + 330 * sy, width: 540 * sx, height: 24 * sy)),
                     with: .color(.black.opacity(0.45)))
            for t in CarArtPaths.frontTyres {
                ctx.fill(Path(roundedRect: CGRect(x: r.minX + t[0] * sx, y: r.minY + (t[1] - t[3]) * sy, width: t[2] * sx, height: t[3] * sy),
                              cornerRadius: 6), with: .color(Color(white: 0.05)))
            }
            ctx.fill(CarArtPaths.frontBody(r), with: .linearGradient(Gradient(colors: [art.color.opacity(0.6), art.color, art.color.opacity(0.6)]),
                                                                     startPoint: CGPoint(x: r.minX, y: 0), endPoint: CGPoint(x: r.maxX, y: 0)))
            ctx.stroke(CarArtPaths.frontBody(r), with: .color(.white.opacity(0.18)), lineWidth: 1)
            ctx.fill(CarArtPaths.frontGlass(r), with: .linearGradient(Gradient(colors: [Color(white: 0.38), Color(white: 0.06)]),
                                                                      startPoint: CGPoint(x: 0, y: r.minY + 60 * sy), endPoint: CGPoint(x: 0, y: r.minY + 160 * sy)))
            ctx.fill(CarArtPaths.frontMirrorL(r), with: .color(art.color.opacity(0.8)))
            ctx.fill(CarArtPaths.frontMirrorR(r), with: .color(art.color.opacity(0.8)))
            ctx.fill(CarArtPaths.frontHeadlightL(r), with: .color(Color(white: 0.12)))
            ctx.fill(CarArtPaths.frontHeadlightR(r), with: .color(Color(white: 0.12)))
            let led = Color(red: 0.78, green: 0.96, blue: 1)
            ctx.stroke(CarArtPaths.frontDrlL(r), with: .color(led), style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
            ctx.stroke(CarArtPaths.frontDrlR(r), with: .color(led), style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
            let grille: Path
            switch art.grille {
            case .hyundai: grille = CarArtPaths.frontGrilleHyundai(r)
            case .kia: grille = CarArtPaths.frontGrilleKia(r)
            default: grille = CarArtPaths.frontGrilleSeat(r)
            }
            ctx.fill(grille, with: .color(Color(white: 0.06)))
            ctx.stroke(grille, with: .color(Color(white: 0.8)), lineWidth: 2)
            ctx.fill(CarArtPaths.frontIntakeL(r), with: .color(Color(white: 0.06)))
            ctx.fill(CarArtPaths.frontIntakeR(r), with: .color(Color(white: 0.06)))
            ctx.fill(CarArtPaths.frontLower(r), with: .color(Color(white: 0.06)))
            ctx.draw(Text(art.brand).font(.system(size: max(8, 16 * sx), weight: .heavy, design: .rounded)).foregroundColor(.white),
                     at: CGPoint(x: r.midX, y: r.minY + 251 * sy))
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
