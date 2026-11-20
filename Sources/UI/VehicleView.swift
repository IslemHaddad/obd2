import SwiftUI

struct VehicleView: View {
    @Environment(VehicleSession.self) private var s
    @State private var picking = false
    @State private var detail: VAGReport?
    @State private var confirmAll = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    header
                    if let v = s.vehicle {
                        if let p = s.vagScanProgress {
                            ScanShowcase(vehicle: v, progress: s.discoverProgress?.0 ?? p, status: scanStatus)
                                .transition(.opacity.combined(with: .scale(scale: 0.96)))
                        } else {
                            CarGallery(vehicle: v)
                        }
                        CarDiagram(vehicle: v, modules: s.vagModules, reports: s.vagReports) { r in detail = r }
                            .frame(height: 440)
                            .padding(.horizontal, 24)
                        legend
                        scanControls
                        moduleList
                    } else {
                        ContentUnavailableView {
                            Label("Choose your car", systemImage: "car.side")
                        } description: {
                            Text("Connect to auto-detect from VIN, or pick a VW Group model.")
                        } actions: {
                            Button("Choose Vehicle") { picking = true }.buttonStyle(.borderedProminent)
                        }
                        .padding(.top, 60)
                    }
                    infoCard
                }
                .padding(.bottom, 24)
            }
            .background(backdrop.ignoresSafeArea())
            .navigationTitle("Vehicle")
            .toolbar {
                if s.vehicle != nil {
                    NavigationLink { CarInfoView() } label: { Image(systemName: "info.circle") }
                }
                Button { picking = true } label: { Image(systemName: "car.2") }
            }
            .sheet(isPresented: $picking) { VehiclePicker() }
            .sheet(item: $detail) { r in ModuleDetail(reportID: r.id).presentationDetents([.medium, .large]) }
            .confirmationDialog("Clear \(s.vagFaulty.count) faulty module(s) only?", isPresented: $confirmAll, titleVisibility: .visible) {
                Button("Clear Faulty Modules", role: .destructive) { run { try await s.clearVAGFaulty() } }
            } message: { Text("Modules without faults are not touched. Engine OFF, ignition ON.") }
            .alert("Error", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
                Button("OK") { error = nil }
            } message: { Text(error ?? "") }
            .refreshable { await s.loadInfo() }
        }
    }

    private var scanStatus: String {
        if let d = s.discoverProgress { return "Searching for modules on the car… \(d.1) found" }
        let done = s.vagReports.count, total = max(s.vagModules.count, 1)
        if let last = s.vagReports.last { return "Scanned \(done)/\(total) · \(last.module.name)" }
        return "Starting scan…"
    }

    private var backdrop: some View {
        LinearGradient(colors: [(s.vehicle?.brand.color ?? .gray).opacity(0.18), Color(.systemBackground)],
                       startPoint: .top, endPoint: .center)
    }

    private var header: some View {
        Button { picking = true } label: {
            HStack(spacing: 12) {
                Text(s.vehicle?.brand.rawValue.uppercased() ?? "VW GROUP")
                    .font(.system(.caption, design: .rounded).weight(.heavy)).tracking(1.5)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background((s.vehicle?.brand.color ?? .gray).gradient, in: Capsule())
                    .foregroundStyle(.white)
                VStack(alignment: .leading, spacing: 2) {
                    Text(s.vehicle?.model.name ?? "No vehicle").font(.title2.bold())
                    if let vin = s.vin { Text(vin).font(.caption.monospaced()).foregroundStyle(.secondary) }
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 20)
        }
        .buttonStyle(.plain)
    }

    private var legend: some View {
        HStack(spacing: 14) {
            LegendDot(color: .yellow, text: "Electronics")
            LegendDot(color: .orange, text: "Powertrain/Chassis")
            LegendDot(color: .red, text: "Safety")
            LegendDot(color: .green, text: "OK")
        }
        .font(.caption2)
    }

    private var scanControls: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                Button { run { await s.scanVAG() } } label: {
                    Label("Full Scan", systemImage: "waveform.badge.magnifyingglass").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || s.state != .connected)
                Button(role: .destructive) { confirmAll = true } label: {
                    Label("Clear Faulty", systemImage: "trash").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(busy || s.vagFaulty.isEmpty)
            }
            .controlSize(.large)
            .padding(.horizontal, 20)
            if s.family.discovered {
                Button { run { await s.scanVAG(rediscover: true) } } label: {
                    Label("Re-discover modules (≈2 min)", systemImage: "dot.radiowaves.left.and.right")
                }
                .font(.caption)
                .disabled(busy || s.state != .connected)
            }
            if s.state == .connected, !s.vagSupported {
                Text("Module scan needs a CAN 11-bit car. Generic codes are on Diagnose.")
                    .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).padding(.horizontal)
            }
        }
    }

    @ViewBuilder private var moduleList: some View {
        let present = s.vagReports.filter(\.present)
        if !present.isEmpty {
            VStack(spacing: 0) {
                ForEach(present.sorted { ($0.faulty ? 0 : 1, $0.module.address) < ($1.faulty ? 0 : 1, $1.module.address) }) { r in
                    Button { detail = r } label: {
                        HStack(spacing: 12) {
                            Image(systemName: r.module.icon)
                                .frame(width: 32, height: 32)
                                .foregroundStyle(r.faulty ? r.module.category.color : .green)
                                .background((r.faulty ? r.module.category.color : .green).opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
                            VStack(alignment: .leading, spacing: 1) {
                                Text("\(r.module.address) · \(r.module.name)").font(.subheadline.weight(.semibold))
                                Text(r.faulty ? "\(r.faults.count) fault(s)" : "No faults")
                                    .font(.caption).foregroundStyle(r.faulty ? r.module.category.color : .secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                        }
                        .padding(.vertical, 10).padding(.horizontal, 14)
                    }
                    .buttonStyle(.plain)
                    if r.id != present.last?.id { Divider().padding(.leading, 58) }
                }
            }
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .padding(.horizontal, 16)
        }
    }

    private var infoCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            row("Calibration ID", s.calID)
            row("ECU", s.ecuName)
            row("Adapter", s.adapterVersion.isEmpty ? nil : s.adapterVersion)
            row("Protocol", s.protocolName.isEmpty ? nil : s.protocolName)
            row("Battery", s.batteryVoltage.map { String(format: "%.2f V", $0) })
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .padding(.horizontal, 16)
    }

    private func row(_ k: String, _ v: String?) -> some View {
        HStack { Text(k).foregroundStyle(.secondary); Spacer(); Text(v ?? "—").monospaced() }.font(.subheadline)
    }

    private func run(_ op: @escaping () async throws -> Void) {
        busy = true
        Task {
            do { try await op() } catch { self.error = error.localizedDescription }
            busy = false
        }
    }
}

struct LegendDot: View {
    let color: Color, text: String
    var body: some View {
        HStack(spacing: 4) { Circle().fill(color).frame(width: 7, height: 7); Text(text).foregroundStyle(.secondary) }
    }
}

// MARK: - Top-view car with module hotspots

struct CarDiagram: View {
    let vehicle: SelectedVehicle
    var modules: [VAGModule] = VAGModule.all
    let reports: [VAGReport]
    let onTap: (VAGReport) -> Void

    var body: some View {
        GeometryReader { g in
            let aspect = CarGeometry.forModel(vehicle.model.name, body: vehicle.model.body).topAspect
            let h = min(g.size.height, g.size.width * aspect)
            let w = h / aspect
            let origin = CGPoint(x: (g.size.width - w) / 2, y: (g.size.height - h) / 2)
            ZStack(alignment: .topLeading) {
                CarTopView(color: vehicle.brand.color, body: vehicle.model.body)
                    .frame(width: w, height: h)
                    .offset(x: origin.x, y: origin.y)
                ForEach(modules) { m in
                    let r = reports.first { $0.module == m }
                    if r?.present != false {
                        Hotspot(module: m, report: r)
                            .position(x: origin.x + m.spot.x * w, y: origin.y + m.spot.y * h)
                            .onTapGesture { if let r { onTap(r) } }
                    }
                }
            }
        }
    }
}

struct Hotspot: View {
    let module: VAGModule
    let report: VAGReport?

    var body: some View {
        if let r = report, r.faulty {
            let c = module.category.color
            ZStack {
                PulseRing(color: c)
                Circle().fill(c.gradient).frame(width: 30, height: 30)
                    .shadow(color: c, radius: 10).shadow(color: c.opacity(0.6), radius: 20)
                Image(systemName: "exclamationmark").font(.system(size: 15, weight: .black)).foregroundStyle(.black)
            }
            .frame(width: 44, height: 44)
            .contentShape(Circle())
            .accessibilityLabel("\(module.name): \(r.faults.count) faults")
        } else if report != nil {
            Circle().fill(.green).frame(width: 10, height: 10).shadow(color: .green.opacity(0.7), radius: 4)
                .frame(width: 32, height: 32).contentShape(Circle())
        } else {
            Circle().fill(.white.opacity(0.35)).frame(width: 7, height: 7)
        }
    }
}

struct PulseRing: View {
    let color: Color
    var body: some View {
        Circle().stroke(color, lineWidth: 2)
            .phaseAnimator([false, true]) { v, on in
                v.scaleEffect(on ? 1.6 : 0.8).opacity(on ? 0 : 0.9)
            } animation: { _ in .easeOut(duration: 1.2) }
            .frame(width: 30, height: 30)
    }
}

struct CarTopView: View {
    let color: Color
    let body_: BodyType
    init(color: Color, body: BodyType) { self.color = color; self.body_ = body }

    var body: some View {
        Canvas { ctx, size in
            let r = CGRect(origin: .zero, size: size)
            let sx = size.width / CarArtPaths.topSize.width, sy = size.height / CarArtPaths.topSize.height
            for w in CarArtPaths.topWheels {
                ctx.fill(Path(roundedRect: CGRect(x: w[0] * sx, y: w[1] * sy, width: w[2] * sx, height: w[3] * sy), cornerRadius: 6),
                         with: .color(Color(white: 0.05)))
            }
            ctx.fill(CarArtPaths.topBody(r), with: .linearGradient(Gradient(colors: [color.opacity(0.7), color, color.opacity(0.7)]),
                                                                   startPoint: .zero, endPoint: CGPoint(x: size.width, y: 0)))
            ctx.stroke(CarArtPaths.topBody(r), with: .color(.white.opacity(0.18)), lineWidth: 1)
            ctx.fill(CarArtPaths.topMirrorL(r), with: .color(color.opacity(0.8)))
            ctx.fill(CarArtPaths.topMirrorR(r), with: .color(color.opacity(0.8)))
            ctx.fill(CarArtPaths.topWindscreen(r), with: .color(Color(white: 0.07)))
            ctx.fill(CarArtPaths.topRearGlass(r), with: .color(Color(white: 0.07)))
            ctx.fill(CarArtPaths.topRoof(r), with: .color(Color(white: 0.1)))
            ctx.fill(CarArtPaths.topPanorama(r), with: .linearGradient(Gradient(colors: [Color(white: 0.35), Color(white: 0.12)]),
                                                                       startPoint: CGPoint(x: 0, y: 400 * sy), endPoint: CGPoint(x: 0, y: 560 * sy)))
            ctx.fill(CarArtPaths.topHeadlightL(r), with: .color(.white))
            ctx.fill(CarArtPaths.topHeadlightR(r), with: .color(.white))
            ctx.fill(CarArtPaths.topTaillight(r), with: .color(.red))
            ctx.stroke(CarArtPaths.topBonnetL(r), with: .color(.white.opacity(0.25)), lineWidth: 1.5)
            ctx.stroke(CarArtPaths.topBonnetR(r), with: .color(.white.opacity(0.25)), lineWidth: 1.5)
        }
    }
}

struct Trapezoid: Shape {
    /// Fraction of width inset on the top edge (negative = inset on bottom edge).
    let topInset: CGFloat
    func path(in r: CGRect) -> Path {
        let t = max(topInset, 0) * r.width, b = max(-topInset, 0) * r.width
        var p = Path()
        p.move(to: CGPoint(x: r.minX + t, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - t, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - b, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX + b, y: r.maxY))
        p.closeSubpath()
        return p
    }
}

// MARK: - Module detail

struct ModuleDetail: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    let reportID: String
    @State private var busy = false
    @State private var error: String?
    @State private var confirm = false

    private var r: VAGReport? { s.vagReports.first { $0.id == reportID } }

    var body: some View {
        NavigationStack {
            List {
                if let r {
                    Section {
                        LabeledContent("Address", value: r.module.address)
                        if let n = r.systemName { LabeledContent("System", value: n) }
                        if let p = r.partNumber { LabeledContent("Part No.", value: p).monospaced() }
                    }
                    Section("Tools") {
                        NavigationLink { FaultTestView(module: r.module) } label: {
                            Label("Fault Test", systemImage: "stethoscope")
                        }
                        NavigationLink { ModuleLiveView(module: r.module) } label: { Label("Live Data", systemImage: "waveform.path.ecg") }
                        if !ServiceFn.functions(for: r.module.address, family: s.family, fuel: s.fuel).isEmpty {
                            NavigationLink { ServiceView(module: r.module) } label: {
                                Label("Service Functions", systemImage: "wrench.and.screwdriver.fill")
                            }
                        }
                        if s.family == .vag {
                            NavigationLink { CodingGateView(module: r.module) } label: {
                                HStack {
                                    Label("Coding", systemImage: "slider.horizontal.below.square.and.square.filled")
                                    Spacer()
                                    if let a = s.codingAbility[s.codingKey(r.module)], a != .yes {
                                        Text(a.label).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                            NavigationLink { AdaptationsView(module: r.module) } label: { Label("Adaptations", systemImage: "dial.low") }
                        }
                        NavigationLink { BasicSettingsView(module: r.module) } label: { Label("Basic Settings", systemImage: "gearshape.arrow.triangle.2.circlepath") }
                        NavigationLink { ModuleIdentView(module: r.module) } label: { Label("Identification", systemImage: "info.circle") }
                    }
                    .disabled(s.state != .connected)
                    Section(r.faulty ? "Faults — tap for details" : "Status") {
                        if !r.faulty { Label("No faults stored", systemImage: "checkmark.seal.fill").foregroundStyle(.green) }
                        ForEach(r.faults) { f in
                            NavigationLink { FaultDetailView(fault: f, module: r.module) } label: {
                                FaultRow(fault: f, module: r.module)
                            }
                        }
                    }
                }
            }
            .navigationTitle(r?.module.name ?? "Module")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    if busy { ProgressView() } else {
                        Button("Clear", role: .destructive) { confirm = true }
                            .disabled(!(r?.faulty ?? false) || s.state != .connected)
                    }
                }
            }
            .confirmationDialog("Clear faults in \(r?.module.name ?? "")?", isPresented: $confirm, titleVisibility: .visible) {
                Button("Clear This Module", role: .destructive) {
                    guard let m = r?.module else { return }
                    busy = true
                    Task {
                        do { try await s.clearVAG(m) } catch { self.error = error.localizedDescription }
                        busy = false
                    }
                }
            }
            .alert("Error", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
                Button("OK") { error = nil }
            } message: { Text(error ?? "") }
        }
    }
}

// MARK: - Picker

struct VehiclePicker: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    @State private var brand: VAGBrand = .seat

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(VAGBrand.allCases) { b in
                            Button { withAnimation(.snappy) { brand = b } } label: {
                                Text(b.rawValue).font(.subheadline.weight(.semibold))
                                    .padding(.horizontal, 14).padding(.vertical, 8)
                                    .background(brand == b ? AnyShapeStyle(b.color.gradient) : AnyShapeStyle(Color(.tertiarySystemFill)), in: Capsule())
                                    .foregroundStyle(brand == b ? .white : .primary)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding()
                }
                ScrollView {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                        ForEach(brand.models) { m in
                            Button {
                                s.vehicle = SelectedVehicle(brand: brand, model: m, year: nil)
                                dismiss()
                            } label: {
                                VStack(spacing: 10) {
                                    CarTopView(color: brand.color, body: m.body)
                                        .frame(width: 44, height: 44 * m.body.aspect)
                                        .rotationEffect(.degrees(-90))
                                        .frame(height: 60)
                                    Text(m.name).font(.subheadline.weight(.semibold))
                                    Text(m.body.rawValue.capitalized).font(.caption2).foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity).padding(.vertical, 14)
                                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
                                    .strokeBorder(s.vehicle?.model == m && s.vehicle?.brand == brand ? brand.color : .clear, lineWidth: 2))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }
            }
            .navigationTitle("Choose Vehicle")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Done") { dismiss() } }
            .onAppear { if let b = s.vehicle?.brand { brand = b } }
        }
    }
}
