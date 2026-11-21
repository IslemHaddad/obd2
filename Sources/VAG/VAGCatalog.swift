import SwiftUI

// MARK: - VW Group brands / models

enum BodyType: String, Codable, CaseIterable {
    case hatch, sedan, estate, suv, coupe, van
    /// Length / width ratio of the top-view silhouette.
    var aspect: CGFloat {
        switch self { case .hatch: 2.15; case .sedan: 2.45; case .estate: 2.5; case .suv: 2.25; case .coupe: 2.35; case .van: 2.55 }
    }
    /// Drag area CdA (Cd × frontal area, m²) for the crank-power estimate.
    var cda: Double {
        switch self { case .hatch: 0.65; case .sedan: 0.64; case .estate: 0.70; case .suv: 0.90; case .coupe: 0.60; case .van: 1.05 }
    }
}

struct CarModel: Identifiable, Hashable, Codable {
    let name: String
    let body: BodyType
    var id: String { name }
}

enum VAGBrand: String, CaseIterable, Identifiable, Codable {
    case seat = "SEAT", cupra = "CUPRA", vw = "Volkswagen", audi = "Audi", skoda = "Škoda",
         porsche = "Porsche", bentley = "Bentley", lamborghini = "Lamborghini",
         hyundai = "Hyundai", kia = "Kia", renault = "Renault"
    var id: String { rawValue }

    enum Family {
        case vag, hyundai, renault
        /// Modules are discovered on the car (not a fixed table).
        var discovered: Bool { self != .vag }
        /// CAN response offsets to look for during discovery.
        var offsets: [Int] { self == .renault ? [0x20, 8] : [8] }
    }
    /// Which diagnostic scheme the brand uses.
    var family: Family {
        switch self {
        case .hyundai, .kia: return .hyundai
        case .renault: return .renault
        default: return .vag
        }
    }

    var color: Color {
        switch self {
        case .seat: Color(red: 0.86, green: 0.12, blue: 0.16)
        case .cupra: Color(red: 0.72, green: 0.45, blue: 0.29)
        case .vw: Color(red: 0.0, green: 0.28, blue: 0.6)
        case .audi: Color(white: 0.75)
        case .skoda: Color(red: 0.31, green: 0.66, blue: 0.24)
        case .porsche: Color(red: 0.8, green: 0.6, blue: 0.2)
        case .bentley: Color(red: 0.1, green: 0.35, blue: 0.25)
        case .lamborghini: Color(red: 0.95, green: 0.75, blue: 0.1)
        case .hyundai: Color(red: 0.12, green: 0.44, blue: 0.70)
        case .kia: Color(red: 0.73, green: 0.09, blue: 0.17)
        case .renault: Color(red: 0.95, green: 0.72, blue: 0.02)
        }
    }

    var models: [CarModel] {
        func m(_ n: String, _ b: BodyType) -> CarModel { CarModel(name: n, body: b) }
        switch self {
        case .seat: return [m("Ibiza", .hatch), m("Leon", .hatch), m("Leon Sportstourer", .estate), m("Arona", .suv),
                            m("Ateca", .suv), m("Tarraco", .suv), m("Alhambra", .van), m("Toledo", .sedan),
                            m("Mii", .hatch), m("Altea", .van), m("Exeo", .sedan)]
        case .cupra: return [m("Born", .hatch), m("Formentor", .suv), m("Leon", .hatch), m("Ateca", .suv),
                             m("Tavascan", .suv), m("Terramar", .suv)]
        case .vw: return [m("Up!", .hatch), m("Polo", .hatch), m("Golf", .hatch), m("Golf Variant", .estate),
                          m("Golf Plus", .van), m("Jetta", .sedan), m("Passat", .sedan), m("Passat Variant", .estate),
                          m("Arteon", .coupe), m("Scirocco", .coupe), m("Beetle", .coupe), m("Taigo", .suv),
                          m("T-Cross", .suv), m("T-Roc", .suv), m("Tiguan", .suv), m("Touareg", .suv),
                          m("Touran", .van), m("Sharan", .van), m("Caddy", .van), m("Transporter", .van),
                          m("Amarok", .suv), m("ID.3", .hatch), m("ID.4", .suv), m("ID.5", .suv), m("ID.7", .sedan),
                          m("ID. Buzz", .van)]
        case .audi: return [m("A1", .hatch), m("A3", .hatch), m("A4", .sedan), m("A4 Avant", .estate), m("A5", .coupe),
                            m("A6", .sedan), m("A6 Avant", .estate), m("A7", .coupe), m("A8", .sedan), m("Q2", .suv),
                            m("Q3", .suv), m("Q4 e-tron", .suv), m("Q5", .suv), m("Q7", .suv), m("Q8", .suv),
                            m("e-tron GT", .coupe), m("TT", .coupe), m("R8", .coupe)]
        case .skoda: return [m("Citigo", .hatch), m("Fabia", .hatch), m("Rapid", .sedan), m("Scala", .hatch),
                             m("Octavia", .sedan), m("Octavia Combi", .estate), m("Superb", .sedan),
                             m("Superb Combi", .estate), m("Kamiq", .suv), m("Karoq", .suv), m("Kodiaq", .suv),
                             m("Yeti", .suv), m("Roomster", .van), m("Enyaq", .suv), m("Elroq", .suv)]
        case .porsche: return [m("911", .coupe), m("718", .coupe), m("Panamera", .sedan), m("Taycan", .sedan),
                               m("Macan", .suv), m("Cayenne", .suv)]
        case .bentley: return [m("Continental GT", .coupe), m("Flying Spur", .sedan), m("Bentayga", .suv)]
        case .lamborghini: return [m("Huracán", .coupe), m("Revuelto", .coupe), m("Urus", .suv)]
        case .hyundai: return [m("Grand i10", .hatch), m("i10", .hatch), m("Grand i10 Nios", .hatch),
                               m("Grand i10 Sedan / Xcent", .sedan), m("i20", .hatch), m("Accent", .sedan),
                               m("Elantra", .sedan), m("Venue", .suv), m("Creta", .suv), m("Kona", .suv),
                               m("Tucson", .suv), m("Santa Fe", .suv), m("Ioniq", .hatch), m("Ioniq 5", .suv)]
        case .renault: return [m("Clio IV", .hatch), m("Clio V", .hatch), m("Captur", .suv), m("Mégane", .hatch),
                               m("Symbol", .sedan), m("Kadjar", .suv), m("Austral", .suv), m("Arkana", .suv), m("Duster", .suv),
                               m("Twingo", .hatch), m("Kangoo", .van), m("Scénic", .van), m("Talisman", .sedan)]
        case .kia: return [m("Picanto", .hatch), m("Rio", .hatch), m("Ceed", .hatch), m("Sonet", .suv),
                           m("Seltos", .suv), m("Sportage", .suv), m("Sorento", .suv), m("Niro", .suv), m("EV6", .suv)]
        }
    }

    /// World Manufacturer Identifier → brand.
    static func from(vin: String) -> VAGBrand? {
        let w = String(vin.prefix(3)).uppercased()
        switch w {
        case "VSS": return .seat
        case "WVW", "WVG", "WV1", "WV2", "1VW", "3VW", "9BW", "LSV", "LFV", "XW8", "AAV": return .vw
        case "WAU", "WUA", "TRU", "WA1": return .audi
        case "TMB", "TMP": return .skoda
        case "WP0", "WP1": return .porsche
        case "SCB", "SJA": return .bentley
        case "ZHW": return .lamborghini
        case "KMH", "MAL", "NLH", "TMA", "5NP", "5NM", "KM8", "MAJ": return .hyundai
        case "KNA", "KNC", "KND", "U5Y", "U6Y", "MZB", "5XY", "3KP": return .kia
        case "VF1", "8A1", "93Y", "X7L", "MEE", "KNM": return .renault
        default: return nil
        }
    }
}

struct SelectedVehicle: Codable, Equatable {
    var brand: VAGBrand
    var model: CarModel
    var year: Int?

    private static let key = "vehicle.selected.v1"
    static func load() -> SelectedVehicle? {
        guard let d = UserDefaults.standard.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(SelectedVehicle.self, from: d)
    }
    static func save(_ v: SelectedVehicle?) {
        if let v, let d = try? JSONEncoder().encode(v) { UserDefaults.standard.set(d, forKey: key) }
        else { UserDefaults.standard.removeObject(forKey: key) }
    }
}

// MARK: - VAG control modules (UDS on CAN 11-bit, MQB/MLB-evo/MEB platforms)

struct VAGModule: Identifiable, Hashable {
    enum Category { case powertrain, chassis, safety, electronics
        /// Glow colour on the car diagram.
        var color: Color {
            switch self { case .powertrain: .orange; case .chassis: .orange; case .safety: .red; case .electronics: .yellow }
        }
    }
    let address: String          // VAG address word, e.g. "17"
    let name: String
    let request: String          // CAN ID we send on
    let response: String         // CAN ID module answers on
    let category: Category
    let spot: CGPoint            // normalized position on top-view (x: 0 left…1 right, y: 0 front…1 rear)
    let icon: String
    var id: String { address }
    static func == (a: VAGModule, b: VAGModule) -> Bool { a.address == b.address }
    func hash(into h: inout Hasher) { h.combine(address) }

    static let all: [VAGModule] = [
        .init(address: "01", name: "Engine Electronics", request: "7E0", response: "7E8", category: .powertrain, spot: .init(x: 0.5, y: 0.14), icon: "engine.combustion"),
        .init(address: "02", name: "Transmission", request: "7E1", response: "7E9", category: .powertrain, spot: .init(x: 0.5, y: 0.27), icon: "gearshape.2"),
        .init(address: "03", name: "Brakes / ABS", request: "713", response: "77D", category: .chassis, spot: .init(x: 0.27, y: 0.2), icon: "exclamationmark.brakesignal"),
        .init(address: "44", name: "Steering Assist", request: "712", response: "77C", category: .chassis, spot: .init(x: 0.7, y: 0.22), icon: "steeringwheel"),
        .init(address: "08", name: "Air Conditioning", request: "746", response: "7B0", category: .electronics, spot: .init(x: 0.5, y: 0.41), icon: "fan"),
        .init(address: "09", name: "Central Electrics", request: "70E", response: "778", category: .electronics, spot: .init(x: 0.2, y: 0.42), icon: "bolt.car"),
        .init(address: "15", name: "Airbags", request: "715", response: "77F", category: .safety, spot: .init(x: 0.5, y: 0.5), icon: "airbag"),
        .init(address: "16", name: "Steering Column Electr.", request: "70C", response: "776", category: .electronics, spot: .init(x: 0.33, y: 0.41), icon: "dial.medium"),
        .init(address: "17", name: "Instruments", request: "714", response: "77E", category: .electronics, spot: .init(x: 0.33, y: 0.34), icon: "gauge.open.with.lines.needle.33percent"),
        .init(address: "19", name: "Gateway", request: "710", response: "77A", category: .electronics, spot: .init(x: 0.66, y: 0.44), icon: "point.3.connected.trianglepath.dotted"),
        .init(address: "5F", name: "Infotainment", request: "773", response: "7DD", category: .electronics, spot: .init(x: 0.5, y: 0.34), icon: "music.note.tv"),
        .init(address: "42", name: "Driver Door", request: "74A", response: "7B4", category: .electronics, spot: .init(x: 0.06, y: 0.5), icon: "door.left.hand.open"),
        .init(address: "52", name: "Passenger Door", request: "74B", response: "7B5", category: .electronics, spot: .init(x: 0.94, y: 0.5), icon: "door.right.hand.open"),
    ]
}

struct VAGFault: Identifiable, Hashable {
    /// ISO 14229 status bits meaning "real fault": testFailed | thisCycle | pending | confirmed | sinceLastClear.
    static let faultMask: UInt8 = 0x2F

    let dtc: String          // e.g. "B116C"
    let failureType: UInt8   // ISO 15031-6 FTB
    let status: UInt8
    var raw: UInt32 = 0
    var powertrain = true
    var id: String { dtc + String(format: "%02X", failureType) }
    /// VW body/chassis modules: the VW fault number (decimal, as VCDS/OBDeleven show it). Powertrain: SAE code.
    var code: String { powertrain ? String(format: "%@ %02X", dtc, failureType) : String(raw) }
    var active: Bool { status & 0x01 != 0 }
    var confirmed: Bool { status & 0x08 != 0 }
    var state: String { active ? "Active" : confirmed ? "Stored" : status & 0x04 != 0 ? "Pending" : "Intermittent" }
    var description: String {
        if powertrain, let k = DTCDatabase.lookup(dtc) { return k }
        return "\(FaultKnowledge.category(failureType).name): \(FaultKnowledge.ftbText(failureType))"
    }
    var detail: String {
        (powertrain ? "" : "\(dtc) \(String(format: "%02X", failureType)) · ") + FaultKnowledge.flags(status).joined(separator: " · ")
    }
}

// MARK: - Hyundai / Kia modules (11-bit CAN, response = request + 8). Names are best-effort labels;
// only modules that answer on the car are used (discovered at scan time).
extension VAGModule {
    static let hyundaiKnown: [String: (String, Category, CGPoint, String)] = [
        "7E0": ("Engine (ECU)", .powertrain, .init(x: 0.50, y: 0.14), "engine.combustion"),
        "7E1": ("Transmission (TCU)", .powertrain, .init(x: 0.50, y: 0.27), "gearshape.2"),
        "7D1": ("ABS / ESC", .chassis, .init(x: 0.27, y: 0.20), "exclamationmark.brakesignal"),
        "7D2": ("Airbag (SRS)", .safety, .init(x: 0.50, y: 0.50), "airbag"),
        "7D4": ("Power steering (MDPS)", .chassis, .init(x: 0.66, y: 0.24), "steeringwheel"),
        "7C6": ("Instrument cluster", .electronics, .init(x: 0.33, y: 0.35), "gauge.open.with.lines.needle.33percent"),
        "7A0": ("Body control (BCM)", .electronics, .init(x: 0.20, y: 0.42), "bolt.car"),
        "770": ("Integrated body unit (IPM)", .electronics, .init(x: 0.22, y: 0.46), "cpu"),
        "7B3": ("Air conditioning", .electronics, .init(x: 0.50, y: 0.41), "fan"),
        "7C4": ("Smart key / immobilizer", .electronics, .init(x: 0.62, y: 0.45), "key"),
        "7A5": ("Tyre pressure (TPMS)", .chassis, .init(x: 0.50, y: 0.80), "tirepressure"),
        "780": ("Audio / head unit", .electronics, .init(x: 0.50, y: 0.34), "music.note.tv"),
    ]

    /// Renault / Dacia: request 7xx, response usually +0x20 (engine/gearbox keep OBD +8). Best-effort labels.
    static let renaultKnown: [String: (String, Category, CGPoint, String)] = [
        "7E0": ("Engine (UCE)", .powertrain, .init(x: 0.50, y: 0.14), "engine.combustion"),
        "7E1": ("Automatic gearbox (BVA)", .powertrain, .init(x: 0.50, y: 0.27), "gearshape.2"),
        "740": ("ABS / ESP", .chassis, .init(x: 0.27, y: 0.20), "exclamationmark.brakesignal"),
        "742": ("Power steering (DAE)", .chassis, .init(x: 0.66, y: 0.24), "steeringwheel"),
        "743": ("Instrument cluster (TdB)", .electronics, .init(x: 0.33, y: 0.35), "gauge.open.with.lines.needle.33percent"),
        "744": ("Climate control", .electronics, .init(x: 0.50, y: 0.41), "fan"),
        "745": ("Body control (UCH)", .electronics, .init(x: 0.20, y: 0.42), "bolt.car"),
        "752": ("Airbag", .safety, .init(x: 0.50, y: 0.50), "airbag"),
        "74D": ("Parking sensors", .electronics, .init(x: 0.50, y: 0.92), "sensor"),
        "747": ("Radio / multimedia", .electronics, .init(x: 0.50, y: 0.34), "music.note.tv"),
        "76D": ("Hands-free card / keyless", .electronics, .init(x: 0.62, y: 0.45), "key"),
    ]

    static func discovered(_ req: String, _ family: VAGBrand.Family) -> VAGModule {
        guard family == .renault else { return hyundai(req) }
        let v = Int(req, radix: 16) ?? 0x700
        let resp = String(format: "%03X", v + (["7E0", "7E1"].contains(req) ? 8 : 0x20))
        if let k = renaultKnown[req] {
            return VAGModule(address: req, name: k.0, request: req, response: resp, category: k.1, spot: k.2, icon: k.3)
        }
        let spot = CGPoint(x: 0.3 + Double((v * 37) % 40) / 100, y: 0.55 + Double((v * 53) % 30) / 100)
        return VAGModule(address: req, name: "Module \(req)", request: req, response: resp, category: .electronics,
                         spot: spot, icon: "cpu")
    }

    static func hyundai(_ req: String) -> VAGModule {
        let v = Int(req, radix: 16) ?? 0x700
        let resp = String(format: "%03X", v + 8)
        if let k = hyundaiKnown[req] {
            return VAGModule(address: req, name: k.0, request: req, response: resp, category: k.1, spot: k.2, icon: k.3)
        }
        let spot = CGPoint(x: 0.3 + Double((v * 37) % 40) / 100, y: 0.55 + Double((v * 53) % 30) / 100)
        return VAGModule(address: req, name: "Module \(req)", request: req, response: resp, category: .electronics,
                         spot: spot, icon: "cpu")
    }
}

struct VAGReport: Identifiable {
    let module: VAGModule
    var present: Bool
    var faults: [VAGFault]
    var partNumber: String?
    var systemName: String?
    var id: String { module.id }
    var faulty: Bool { !faults.isEmpty }
}
