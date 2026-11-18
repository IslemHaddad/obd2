import SwiftUI

struct DashboardView: View {
    @Environment(VehicleSession.self) private var s
    @AppStorage("accent") private var accent: Accent = .cyan
    @AppStorage("tileBackground") private var bg: TileBackground = .glass
    @State private var editing = false
    @State private var editingTile: Tile?
    @State private var adding = false
    @State private var settings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    statusStrip
                    ForEach(rows, id: \.self) { row in
                        HStack(spacing: 12) {
                            ForEach(row) { tile in cell(tile) }
                            if row.count == 1, row[0].size == .small { Color.clear.frame(maxWidth: .infinity) }
                        }
                    }
                    if editing {
                        Button { adding = true } label: {
                            Label("Add Gauge", systemImage: "plus")
                                .font(.headline)
                                .frame(maxWidth: .infinity, minHeight: 64)
                                .background(RoundedRectangle(cornerRadius: 24, style: .continuous)
                                    .strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
                                    .foregroundStyle(accent.color.opacity(0.6)))
                        }
                        .transition(.scale.combined(with: .opacity))
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
                .animation(.spring(response: 0.35, dampingFraction: 0.8), value: s.tiles)
                .animation(.spring(response: 0.35, dampingFraction: 0.8), value: editing)
            }
            .background(background.ignoresSafeArea())
            .navigationTitle("Live")
            .onAppear { s.wantOil = true }
            .onDisappear { s.wantOil = false }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { settings = true } label: { Image(systemName: "paintpalette") }
                }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if !editing {
                        Button { s.isLogging ? s.stopLogging() : s.startLogging() } label: {
                            Image(systemName: s.isLogging ? "stop.circle.fill" : "record.circle")
                                .symbolEffect(.pulse, isActive: s.isLogging)
                                .foregroundStyle(s.isLogging ? .red : accent.color)
                        }
                        .disabled(s.state != .connected)
                    }
                    Button(editing ? "Done" : "Edit") { editing.toggle() }
                        .fontWeight(editing ? .semibold : .regular)
                }
            }
            .sensoryFeedback(.impact(weight: .medium), trigger: editing)
            .sheet(item: $editingTile) { t in TileEditor(tile: t).presentationDetents([.medium, .large]) }
            .sheet(isPresented: $adding) {
                TileEditor(tile: Tile(pid: s.supportedPIDs.first?.id ?? 0x0C, style: .ring, size: .small), isNew: true)
                    .presentationDetents([.medium, .large])
            }
            .sheet(isPresented: $settings) { AppearanceSettings().presentationDetents([.medium]) }
        }
        .tint(accent.color)
    }

    // Pack tiles into rows: two smalls side by side; wide/large take a full row.
    private var rows: [[Tile]] {
        var out = [[Tile]](), pending: Tile?
        for t in s.tiles {
            if t.size == .small {
                if let p = pending { out.append([p, t]); pending = nil } else { pending = t }
            } else {
                if let p = pending { out.append([p]); pending = nil }
                out.append([t])
            }
        }
        if let p = pending { out.append([p]) }
        return out
    }

    @ViewBuilder private func cell(_ tile: Tile) -> some View {
        let pid = PIDs.byID[tile.pid]
        GaugeTile(tile: tile, pid: pid, value: s.values[tile.pid], history: s.history[tile.pid] ?? [],
                  accent: accent, background: bg)
            .frame(maxWidth: .infinity)
            .frame(height: tile.size.height)
            .overlay(alignment: .topLeading) {
                if editing {
                    Button { withAnimation { s.tiles.removeAll { $0.id == tile.id } } } label: {
                        Image(systemName: "minus.circle.fill")
                            .font(.title2).symbolRenderingMode(.palette).foregroundStyle(.white, .red)
                    }
                    .offset(x: -8, y: -8)
                    .transition(.scale)
                }
            }
            .modifier(Jiggle(active: editing, seed: tile.id.hashValue))
            .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: 24, style: .continuous))
            .onTapGesture { if editing { editingTile = tile } }
            .contextMenu {
                Button { editingTile = tile } label: { Label("Customize", systemImage: "slider.horizontal.3") }
                Menu {
                    ForEach(Tile.Style.allCases) { st in
                        Button { update(tile.id) { $0.style = st } } label: { Label(st.label, systemImage: st.icon) }
                    }
                } label: { Label("Style", systemImage: "paintbrush") }
                Menu {
                    ForEach(Tile.Size.allCases) { sz in Button(sz.label) { update(tile.id) { $0.size = sz } } }
                } label: { Label("Size", systemImage: "arrow.up.left.and.arrow.down.right") }
                Divider()
                Button(role: .destructive) { s.tiles.removeAll { $0.id == tile.id } } label: { Label("Remove", systemImage: "trash") }
            }
            .draggable(tile.id.uuidString) {
                GaugeTile(tile: tile, pid: pid, value: s.values[tile.pid], history: [], accent: accent, background: bg)
                    .frame(width: 160, height: 140)
            }
            .dropDestination(for: String.self) { items, _ in
                guard let str = items.first, let from = UUID(uuidString: str) else { return false }
                s.move(from, before: tile.id)
                return true
            } isTargeted: { _ in }
    }

    private func update(_ id: Tile.ID, _ change: (inout Tile) -> Void) {
        guard let i = s.tiles.firstIndex(where: { $0.id == id }) else { return }
        change(&s.tiles[i])
    }

    private var statusStrip: some View {
        HStack(spacing: 8) {
            Pill(icon: s.state == .connected ? "bolt.fill" : "bolt.slash",
                 text: s.state == .connected ? s.protocolName.components(separatedBy: " ").prefix(2).joined(separator: " ") : "Offline",
                 color: s.state == .connected ? .green : .secondary)
            if s.state == .connected {
                Pill(icon: "speedometer", text: String(format: "%.1f Hz", s.refreshHz), color: accent.color)
            }
            if let v = s.batteryVoltage {
                Pill(icon: "minus.plus.batteryblock", text: String(format: "%.1f V", v), color: v < 12 ? .orange : .green)
            }
            if let o = s.oilTemp {
                Pill(icon: "drop.fill", text: String(format: "Oil %.0f °C", o), color: o >= 125 ? .red : .orange)
            }
            Spacer()
        }
        .padding(.top, 4)
    }

    private var background: some View {
        LinearGradient(colors: [accent.color.opacity(0.12), Color(.systemBackground)], startPoint: .top, endPoint: .center)
    }
}

struct Pill: View {
    let icon: String, text: String, color: Color
    var body: some View {
        Label(text, systemImage: icon)
            .font(.caption.weight(.semibold)).monospacedDigit()
            .foregroundStyle(color)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(color.opacity(0.14), in: Capsule())
            .contentTransition(.numericText())
    }
}

struct Jiggle: ViewModifier {
    let active: Bool
    let seed: Int
    @State private var phase = false
    func body(content: Content) -> some View {
        content
            .rotationEffect(.degrees(active ? (phase ? 1.2 : -1.2) : 0))
            .animation(active ? .easeInOut(duration: 0.13 + Double(abs(seed % 5)) * 0.01).repeatForever(autoreverses: true) : .default, value: phase)
            .onChange(of: active, initial: true) { _, on in phase = on }
    }
}

// MARK: - Tile

struct GaugeTile: View {
    let tile: Tile
    let pid: PID?
    let value: Double?
    let history: [Double]
    let accent: Accent
    let background: TileBackground

    private var lo: Double { pid?.min ?? 0 }
    private var hi: Double { pid?.max ?? 100 }
    private var fraction: Double { value.map { min(max(($0 - lo) / (hi - lo), 0), 1) } ?? 0 }
    private var warn: Bool { if let w = tile.warnAt, let v = value { v >= w } else { false } }
    private var tint: Color { warn ? .red : accent.color }
    private var text: String {
        guard let v = value else { return "—" }
        return abs(v) >= 100 ? String(format: "%.0f", v) : String(format: "%.1f", v)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(pid?.name ?? "PID \(String(format: "%02X", tile.pid))")
                    .font(.footnote.weight(.semibold)).foregroundStyle(.secondary).lineLimit(1)
                Spacer(minLength: 0)
                if warn { Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red).font(.caption) }
            }
            content.frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(14)
        .tileBackground(background, tint: tint)
        .animation(.smooth(duration: 0.25), value: value)
    }

    @ViewBuilder private var content: some View {
        switch tile.style {
        case .ring:
            ZStack {
                Circle().stroke(tint.opacity(0.15), lineWidth: 10)
                Circle().trim(from: 0, to: fraction)
                    .stroke(AngularGradient(colors: accentGradient, center: .center, startAngle: .degrees(0), endAngle: .degrees(360 * max(fraction, 0.01))),
                            style: StrokeStyle(lineWidth: 10, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .shadow(color: tint.opacity(0.5), radius: 6)
                readout(size: tile.size == .large ? 48 : 26)
            }
            .padding(4)
        case .arc:
            ArcGauge(fraction: fraction, colors: accentGradient, tint: tint, lo: lo, hi: hi) {
                readout(size: tile.size == .large ? 56 : 30)
            }
        case .bar:
            VStack(alignment: .leading, spacing: 10) {
                Spacer(minLength: 0)
                readout(size: tile.size == .large ? 56 : 34, leading: true)
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        Capsule().fill(tint.opacity(0.15))
                        Capsule().fill(LinearGradient(colors: accentGradient, startPoint: .leading, endPoint: .trailing))
                            .frame(width: max(g.size.width * fraction, 8))
                            .shadow(color: tint.opacity(0.5), radius: 4)
                    }
                }
                .frame(height: 10)
            }
        case .number:
            VStack(alignment: .leading) {
                Spacer(minLength: 0)
                readout(size: tile.size == .large ? 84 : 44, leading: true)
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        case .graph:
            VStack(alignment: .leading, spacing: 4) {
                readout(size: 26, leading: true)
                AreaSparkline(values: history, lo: lo, hi: hi, colors: accentGradient)
            }
        }
    }

    private var accentGradient: [Color] { warn ? [.orange, .red] : accent.gradient }

    private func readout(size: CGFloat, leading: Bool = false) -> some View {
        VStack(alignment: leading ? .leading : .center, spacing: 0) {
            Text(text)
                .font(.system(size: size, weight: .bold, design: .rounded)).monospacedDigit()
                .contentTransition(.numericText(value: value ?? 0))
                .minimumScaleFactor(0.5).lineLimit(1)
            Text(pid?.unit ?? "").font(.caption.weight(.medium)).foregroundStyle(.secondary)
        }
    }
}

struct ArcGauge<Center: View>: View {
    let fraction: Double
    let colors: [Color]
    let tint: Color
    let lo: Double, hi: Double
    @ViewBuilder let center: Center
    private let sweep = 270.0

    var body: some View {
        GeometryReader { g in
            let d = min(g.size.width, g.size.height)
            let line = d * 0.07
            ZStack {
                arc(to: 1).stroke(tint.opacity(0.15), style: StrokeStyle(lineWidth: line, lineCap: .round))
                arc(to: fraction)
                    .stroke(AngularGradient(colors: colors, center: .center,
                                            startAngle: .degrees(135), endAngle: .degrees(135 + sweep)),
                            style: StrokeStyle(lineWidth: line, lineCap: .round))
                    .shadow(color: tint.opacity(0.6), radius: 8)
                ForEach(0..<11) { i in
                    Capsule().fill(.secondary.opacity(i % 5 == 0 ? 0.8 : 0.35))
                        .frame(width: 2, height: i % 5 == 0 ? line * 0.9 : line * 0.5)
                        .offset(y: -(d / 2 - line * 2))
                        .rotationEffect(.degrees(-135 + sweep * Double(i) / 10))
                }
                Capsule().fill(tint)
                    .frame(width: 3, height: d * 0.32)
                    .offset(y: -d * 0.16)
                    .rotationEffect(.degrees(-135 + sweep * fraction))
                    .shadow(color: tint, radius: 4)
                Circle().fill(tint).frame(width: line * 0.9)
                center.offset(y: d * 0.28)
            }
            .frame(width: d, height: d)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func arc(to f: Double) -> some Shape {
        ArcShape(start: 135, end: 135 + sweep * f).inset(by: 0)
    }
}

struct ArcShape: InsettableShape {
    var start: Double, end: Double, inset: CGFloat = 0
    var animatableData: Double { get { end } set { end = newValue } }
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.addArc(center: CGPoint(x: r.midX, y: r.midY), radius: min(r.width, r.height) / 2 - inset - r.width * 0.05,
                 startAngle: .degrees(start), endAngle: .degrees(end), clockwise: false)
        return p
    }
    func inset(by a: CGFloat) -> ArcShape { var c = self; c.inset += a; return c }
}

struct AreaSparkline: View {
    let values: [Double]
    let lo: Double, hi: Double
    let colors: [Color]
    var body: some View {
        Canvas { ctx, size in
            guard values.count > 1 else { return }
            let range = max(hi - lo, .ulpOfOne)
            let dx = size.width / CGFloat(values.count - 1)
            func y(_ v: Double) -> CGFloat { size.height * (1 - CGFloat(min(max((v - lo) / range, 0), 1))) }
            var line = Path()
            for (i, v) in values.enumerated() {
                let pt = CGPoint(x: CGFloat(i) * dx, y: y(v))
                i == 0 ? line.move(to: pt) : line.addLine(to: pt)
            }
            var area = line
            area.addLine(to: CGPoint(x: size.width, y: size.height))
            area.addLine(to: CGPoint(x: 0, y: size.height))
            area.closeSubpath()
            ctx.fill(area, with: .linearGradient(Gradient(colors: [colors.last!.opacity(0.35), .clear]),
                                                  startPoint: .zero, endPoint: CGPoint(x: 0, y: size.height)))
            ctx.stroke(line, with: .linearGradient(Gradient(colors: colors), startPoint: .zero, endPoint: CGPoint(x: size.width, y: 0)),
                       style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        }
    }
}

// MARK: - Editors

struct TileEditor: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    @AppStorage("accent") private var accent: Accent = .cyan
    @AppStorage("tileBackground") private var bg: TileBackground = .glass
    @State var tile: Tile
    var isNew = false
    @State private var warnOn = false
    @State private var warnValue = 0.0

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    GaugeTile(tile: tile, pid: PIDs.byID[tile.pid], value: s.values[tile.pid] ?? preview,
                              history: s.history[tile.pid] ?? [], accent: accent, background: bg)
                        .frame(height: min(tile.size.height, 220))
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets())
                }
                Section("Sensor") {
                    Picker("Sensor", selection: $tile.pid) {
                        ForEach(s.supportedPIDs) { Text($0.name).tag($0.id) }
                    }
                    .pickerStyle(.navigationLink)
                }
                Section("Style") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(Tile.Style.allCases) { st in
                                Button { tile.style = st } label: {
                                    VStack(spacing: 6) {
                                        Image(systemName: st.icon).font(.title2)
                                        Text(st.label).font(.caption)
                                    }
                                    .frame(width: 72, height: 64)
                                    .background(tile.style == st ? accent.color.opacity(0.2) : Color(.tertiarySystemFill),
                                                in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                                        .strokeBorder(tile.style == st ? accent.color : .clear, lineWidth: 1.5))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    Picker("Size", selection: $tile.size) {
                        ForEach(Tile.Size.allCases) { Text($0.label).tag($0) }
                    }
                    .pickerStyle(.segmented)
                }
                if let p = PIDs.byID[tile.pid] {
                    Section("Warning") {
                        Toggle("Alert above value", isOn: $warnOn)
                        if warnOn {
                            HStack {
                                Slider(value: $warnValue, in: p.min...p.max)
                                Text(String(format: "%.0f %@", warnValue, p.unit)).monospacedDigit().frame(minWidth: 80, alignment: .trailing)
                            }
                        }
                    }
                }
            }
            .navigationTitle(isNew ? "Add Gauge" : "Customize")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button(isNew ? "Add" : "Save") { commit() }.fontWeight(.semibold) }
            }
            .onAppear {
                warnOn = tile.warnAt != nil
                let p = PIDs.byID[tile.pid]
                warnValue = tile.warnAt ?? ((p?.min ?? 0) + (p?.max ?? 100)) * 0.8
            }
            .onChange(of: warnOn) { _, on in tile.warnAt = on ? warnValue : nil }
            .onChange(of: warnValue) { _, v in if warnOn { tile.warnAt = v } }
            .sensoryFeedback(.selection, trigger: tile.style)
            .sensoryFeedback(.selection, trigger: tile.size)
        }
    }

    /// Mid-range placeholder so the preview looks alive when offline.
    private var preview: Double? {
        guard let p = PIDs.byID[tile.pid] else { return nil }
        return p.min + (p.max - p.min) * 0.62
    }

    private func commit() {
        if isNew { s.tiles.append(tile) }
        else if let i = s.tiles.firstIndex(where: { $0.id == tile.id }) { s.tiles[i] = tile }
        dismiss()
    }
}

struct AppearanceSettings: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(VehicleSession.self) private var s
    @AppStorage("accent") private var accent: Accent = .cyan
    @AppStorage("appearance") private var appearance: Appearance = .system
    @AppStorage("tileBackground") private var bg: TileBackground = .glass

    var body: some View {
        NavigationStack {
            Form {
                Section("Accent") {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 5), spacing: 14) {
                        ForEach(Accent.allCases) { a in
                            Circle().fill(a.color.gradient)
                                .frame(width: 40, height: 40)
                                .overlay(Circle().strokeBorder(.white, lineWidth: accent == a ? 3 : 0))
                                .shadow(color: a.color.opacity(accent == a ? 0.6 : 0), radius: 6)
                                .onTapGesture { withAnimation(.snappy) { accent = a } }
                        }
                    }
                    .padding(.vertical, 6)
                }
                Section("Appearance") {
                    Picker("Mode", selection: $appearance) {
                        ForEach(Appearance.allCases) { Text($0.rawValue.capitalized).tag($0) }
                    }.pickerStyle(.segmented)
                    Picker("Tiles", selection: $bg) {
                        ForEach(TileBackground.allCases) { Text($0.rawValue.capitalized).tag($0) }
                    }.pickerStyle(.segmented)
                }
                Section {
                    Button("Reset Dashboard Layout", role: .destructive) { s.tiles = Tile.defaults }
                }
            }
            .navigationTitle("Appearance")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Done") { dismiss() } }
            .sensoryFeedback(.selection, trigger: accent)
        }
    }
}
