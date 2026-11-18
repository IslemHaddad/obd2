import SwiftUI

// MARK: - Dashboard tile model (persisted)

struct Tile: Identifiable, Codable, Hashable {
    enum Style: String, Codable, CaseIterable, Identifiable {
        case ring, arc, bar, number, graph
        var id: String { rawValue }
        var label: String {
            switch self { case .ring: "Ring"; case .arc: "Speedo"; case .bar: "Bar"; case .number: "Digital"; case .graph: "Graph" }
        }
        var icon: String {
            switch self {
            case .ring: "circle.circle"; case .arc: "gauge.with.needle"; case .bar: "chart.bar.fill"
            case .number: "textformat.123"; case .graph: "waveform.path.ecg"
            }
        }
    }
    enum Size: String, Codable, CaseIterable, Identifiable {
        case small, wide, large
        var id: String { rawValue }
        var label: String { rawValue.capitalized }
        var height: CGFloat { switch self { case .small: 170; case .wide: 150; case .large: 300 } }
    }

    var id = UUID()
    var pid: UInt8
    var style: Style
    var size: Size
    var warnAt: Double?          // value above which the tile turns red

    private static let key = "dashboard.tiles.v1"

    static let defaults: [Tile] = [
        Tile(pid: 0x0C, style: .arc, size: .large, warnAt: 6000),
        Tile(pid: 0x0D, style: .ring, size: .small),
        Tile(pid: 0x05, style: .ring, size: .small, warnAt: 110),
        Tile(pid: 0xFF, style: .ring, size: .small, warnAt: 125),      // SEAT/VW oil temp
        Tile(pid: 0x04, style: .graph, size: .wide),
        Tile(pid: 0x11, style: .bar, size: .small),
        Tile(pid: 0x42, style: .number, size: .small),
    ]

    static func load() -> [Tile] {
        guard let d = UserDefaults.standard.data(forKey: key),
              let t = try? JSONDecoder().decode([Tile].self, from: d) else { return defaults }
        return t
    }
    static func save(_ t: [Tile]) {
        if let d = try? JSONEncoder().encode(t) { UserDefaults.standard.set(d, forKey: key) }
    }
}

// MARK: - Appearance

enum Accent: String, CaseIterable, Identifiable {
    case cyan, blue, indigo, purple, pink, red, orange, yellow, green, mint
    var id: String { rawValue }
    var color: Color {
        switch self {
        case .cyan: .cyan; case .blue: .blue; case .indigo: .indigo; case .purple: .purple; case .pink: .pink
        case .red: .red; case .orange: .orange; case .yellow: .yellow; case .green: .green; case .mint: .mint
        }
    }
    /// Two-stop gradient used on gauges.
    var gradient: [Color] { [color.opacity(0.65), color] }
}

enum Appearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var scheme: ColorScheme? { switch self { case .system: nil; case .light: .light; case .dark: .dark } }
}

enum TileBackground: String, CaseIterable, Identifiable {
    case glass, solid, tinted
    var id: String { rawValue }
}

struct TileBackgroundModifier: ViewModifier {
    let kind: TileBackground
    let tint: Color
    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: 24, style: .continuous)
        switch kind {
        case .glass:
            content.background(.regularMaterial, in: shape)
                .overlay(shape.strokeBorder(.white.opacity(0.08)))
        case .solid:
            content.background(Color(.secondarySystemGroupedBackground), in: shape)
        case .tinted:
            content.background(
                LinearGradient(colors: [tint.opacity(0.28), tint.opacity(0.06)], startPoint: .topLeading, endPoint: .bottomTrailing),
                in: shape)
                .overlay(shape.strokeBorder(tint.opacity(0.25)))
        }
    }
}

extension View {
    func tileBackground(_ k: TileBackground, tint: Color) -> some View { modifier(TileBackgroundModifier(kind: k, tint: tint)) }
}
