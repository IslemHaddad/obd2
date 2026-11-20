import SwiftUI

/// Live horsepower & torque.
/// 1) If the engine reports torque (PID 62 actual % × PID 63 reference Nm) → real engine torque, hp from rpm.
/// 2) Otherwise estimated from acceleration: crank power = (m·v·dv/dt + aero drag + rolling) / drivetrain eff,
///    torque = P / ω_engine (user-entered weight incl. driver). Drag/rolling/drivetrain are added back (old note:
///    included), so it reads below the factory rating; best during full-throttle pulls in one gear.
struct PowerView: View {
    @Environment(VehicleSession.self) private var s
    @AppStorage("carWeightKg") private var weight = 0
    @State private var peakHP = 0.0
    @State private var peakNm = 0.0
    @State private var editingWeight = false

    private let psPerKW = 1 / 0.73549875

    var body: some View {
        NavigationStack {
            let live = compute()
            ScrollView {
                VStack(spacing: 14) {
                    HStack(spacing: 8) {
                        ClusterDial(title: "hp", value: live.hp ?? 0, maxV: 200, major: 20, red: nil, accent: .orange)
                        ClusterDial(title: "Nm", value: live.nm ?? 0, maxV: 300, major: 50, red: nil, accent: .cyan)
                    }
                    .frame(height: 200)
                    HStack(spacing: 10) {
                        peak("Peak power", String(format: "%.0f hp", peakHP))
                        peak("Peak torque", String(format: "%.0f Nm", peakNm))
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        Label(live.method, systemImage: live.fromECU ? "engine.combustion" : "speedometer")
                            .font(.subheadline.weight(.semibold))
                        Text(live.note).font(.caption).foregroundStyle(.secondary)
                        HStack {
                            Text("RPM \(Int(s.values[0x0C] ?? 0))")
                            Spacer()
                            Text("\(Int(s.values[0x0D] ?? 0)) km/h")
                            Spacer()
                            Text("Throttle \(Int(s.values[0x11] ?? 0))%")
                        }
                        .font(.caption.monospacedDigit())
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    HStack {
                        Button("Car weight: \(weight > 0 ? "\(weight) kg" : "set")") { editingWeight = true }
                        Spacer()
                        Button("Reset peaks") { peakHP = 0; peakNm = 0 }
                    }
                    .font(.subheadline)
                }
                .padding(16)
            }
            .navigationTitle("Power")
            .onChange(of: live.hp ?? -1) { _, v in if v > peakHP, live.valid { peakHP = v } }
            .onChange(of: live.nm ?? -1) { _, v in if v > peakNm, live.valid { peakNm = v } }
            .alert("Car weight incl. driver (kg)", isPresented: $editingWeight) {
                TextField("kg", value: $weight, format: .number.grouping(.never)).keyboardType(.numberPad)
                Button("OK") {}
            } message: { Text("From the registration document (empty weight) + you. Used for the acceleration method.") }
        }
    }

    private func peak(_ t: String, _ v: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(t.uppercased()).font(.caption2.weight(.bold)).foregroundStyle(.secondary)
            Text(v).font(.system(.title2, design: .rounded).weight(.bold)).monospacedDigit()
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    struct Live { var hp: Double?; var nm: Double?; var method: String; var note: String; var fromECU: Bool; var valid: Bool }

    private func compute() -> Live {
        let rpm = s.values[0x0C] ?? 0
        // 1) Engine-reported torque
        if let pct = s.values[0x62], let ref = s.values[0x63], ref > 0 {
            let nm = max(0, pct) / 100 * ref
            let kw = nm * rpm * 2 * .pi / 60 / 1000
            return Live(hp: kw * psPerKW, nm: nm, method: "Engine-reported torque",
                        note: "Read from the engine computer (actual torque × reference torque).", fromECU: true, valid: rpm > 500)
        }
        // 2) Acceleration method
        guard weight > 0 else {
            return Live(hp: nil, nm: nil, method: "Estimated from acceleration",
                        note: "This car doesn't report engine torque. Set the car weight to calculate power from acceleration.",
                        fromECU: false, valid: false)
        }
        let pts = s.speedTrace.suffix(12)                 // ~1 s window
        guard pts.count >= 5, let first = pts.first, let last = pts.last, last.t - first.t > 0.4 else {
            return Live(hp: 0, nm: 0, method: "Estimated from acceleration", note: note, fromECU: false, valid: false)
        }
        let mt = pts.map(\.t).reduce(0, +) / Double(pts.count)
        let mv = pts.map(\.v).reduce(0, +) / Double(pts.count)
        let den = pts.map { ($0.t - mt) * ($0.t - mt) }.reduce(0, +)
        let slope = den > 0 ? pts.map { ($0.t - mt) * ($0.v - mv) }.reduce(0, +) / den : 0   // km/h per s
        let v = mv / 3.6, a = slope / 3.6
        guard a > 0, v > 3, rpm > 800 else {
            return Live(hp: 0, nm: 0, method: "Estimated from acceleration", note: note, fromECU: false, valid: false)
        }
        // Estimate crank power: accel power + aero drag + rolling resistance, / drivetrain efficiency.
        // CdA auto-picked from the car's body type (hatch/suv/sedan…).
        let cda = s.vehicle?.model.body.cda ?? 0.65
        let crr = 0.012, drivetrain = 0.13, rho = 1.225, g = 9.81
        let pAccel = Double(weight) * v * a
        let pDrag = 0.5 * rho * cda * v * v * v
        let pRoll = crr * Double(weight) * g * v
        let kw = (pAccel + pDrag + pRoll) / (1 - drivetrain) / 1000
        let nm = kw * 1000 / (2 * .pi * rpm / 60)
        return Live(hp: kw * psPerKW, nm: nm, method: "Estimated from acceleration", note: note, fromECU: false,
                    valid: (s.values[0x11] ?? 0) > 60)
    }

    private var note: String {
        "Estimated crank power for \(weight) kg — adds back aero drag, rolling resistance and drivetrain loss. Peaks recorded at >60% throttle; 2nd gear full-throttle is most accurate. Still an estimate, not a bench dyno."
    }
}

struct ClusterDial: View {
    let title: String
    let value: Double
    let maxV: Double
    let major: Double
    let red: Double?
    var labelDiv: Double = 1
    let accent: Color
    private let start = 135.0, sweep = 270.0

    var body: some View {
        GeometryReader { g in
            let d = min(g.size.width, g.size.height)
            let r = d / 2
            let f = max(0, min(1, value / maxV))
            ZStack {
                Circle().fill(RadialGradient(colors: [Color(white: 0.12), Color(white: 0.03)], center: .center,
                                             startRadius: 0, endRadius: r))
                Circle().strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                Arc(start: start, end: start + sweep * f).stroke(accent.opacity(0.35), style: StrokeStyle(lineWidth: r * 0.12))
                    .padding(r * 0.08)
                Arc(start: start, end: start + sweep * f).stroke(accent, style: StrokeStyle(lineWidth: r * 0.025))
                    .padding(r * 0.08)
                if let red {
                    Arc(start: start + sweep * red / maxV, end: start + sweep).stroke(Color.red, style: StrokeStyle(lineWidth: r * 0.04))
                        .padding(r * 0.05)
                }
                ForEach(0...Int(maxV / major), id: \.self) { i in
                    let v = Double(i) * major
                    let a = Angle(degrees: start + sweep * v / maxV)
                    Text("\(Int(v / labelDiv))")
                        .font(.system(size: r * 0.11, weight: .semibold, design: .rounded))
                        .foregroundStyle(Color.white.opacity(0.85))
                        .position(x: r + cos(a.radians) * r * 0.62, y: r + sin(a.radians) * r * 0.62)
                }
                Capsule().fill(accent)
                    .frame(width: r * 0.035, height: r * 0.8)
                    .offset(y: -r * 0.35)
                    .rotationEffect(.degrees(start + sweep * f + 90))
                    .shadow(color: accent, radius: 4)
                    .animation(.interpolatingSpring(stiffness: 120, damping: 14), value: f)
                Circle().fill(Color(white: 0.2)).frame(width: r * 0.14)
                VStack(spacing: 0) {
                    Text("\(Int(value))").font(.system(size: r * 0.26, weight: .bold, design: .rounded)).monospacedDigit()
                        .contentTransition(.numericText())
                    Text(title).font(.system(size: r * 0.1)).foregroundStyle(.secondary)
                }
                .offset(y: r * 0.45)
            }
            .frame(width: d, height: d)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

struct Arc: Shape {
    var start: Double, end: Double
    var animatableData: Double { get { end } set { end = newValue } }
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.addArc(center: CGPoint(x: rect.midX, y: rect.midY), radius: min(rect.width, rect.height) / 2,
                 startAngle: .degrees(start), endAngle: .degrees(max(start, end)), clockwise: false)
        return p
    }
}
