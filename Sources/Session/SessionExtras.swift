import Foundation

// MARK: - Persistence helpers

enum LastAdapter: Codable, Equatable {
    case ble(UUID, String)
    case wifi(String, UInt16)

    private static let key = "adapter.last.v1"
    static func load() -> LastAdapter? {
        guard let d = UserDefaults.standard.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(LastAdapter.self, from: d)
    }
    static func save(_ a: LastAdapter) {
        if let d = try? JSONEncoder().encode(a) { UserDefaults.standard.set(d, forKey: key) }
    }
    var label: String {
        switch self {
        case .ble(_, let n): return n
        case .wifi(let h, let p): return "\(h):\(p)"
        }
    }
}

extension LastAdapter {
    var key: String {
        switch self {
        case .ble(let id, _): return "ble:\(id.uuidString)"
        case .wifi(let h, let p): return "tcp:\(h):\(p)"
        }
    }
}

/// Every adapter used, with its chip profile and the voltmeter correction learned against the car's own voltage.
struct SavedAdapter: Codable, Identifiable, Equatable {
    let link: LastAdapter
    var name: String
    var profile: AdapterProfile
    var voltOffset: Double?
    var lastUsed: Date
    var id: String { link.key }

    private static let key = "adapters.saved.v1"
    static func load() -> [SavedAdapter] {
        guard let d = UserDefaults.standard.data(forKey: key),
              let a = try? JSONDecoder().decode([SavedAdapter].self, from: d) else { return [] }
        return a.sorted { $0.lastUsed > $1.lastUsed }
    }
    static func save(_ a: [SavedAdapter]) {
        if let d = try? JSONEncoder().encode(a) { UserDefaults.standard.set(d, forKey: key) }
    }
    static func remember(_ link: LastAdapter, profile: AdapterProfile) {
        var all = load()
        let old = all.first { $0.id == link.key }
        all.removeAll { $0.id == link.key }
        all.append(SavedAdapter(link: link, name: old?.name ?? link.label, profile: profile,
                                voltOffset: old?.voltOffset, lastUsed: Date()))
        save(all)
    }
    static func learnVoltage(_ link: LastAdapter, adapterV: Double, carV: Double) {
        var all = load()
        guard let i = all.firstIndex(where: { $0.id == link.key }) else { return }
        let d = adapterV - carV
        all[i].voltOffset = all[i].voltOffset.map { $0 * 0.8 + d * 0.2 } ?? d
        save(all)
    }
    static func offset(_ link: LastAdapter?) -> Double? {
        guard let link else { return nil }
        return load().first { $0.id == link.key }?.voltOffset
    }
}

/// Hyundai/Kia modules found on a car, remembered per VIN so later scans skip the 2-minute search.
enum HyundaiModuleMemory {
    private static let key = "hyundai.modules.byVIN.v1"
    static func load(_ vin: String) -> [String] {
        (UserDefaults.standard.dictionary(forKey: key) as? [String: [String]])?[vin] ?? []
    }
    static func save(_ vin: String, _ addrs: [String]) {
        var d = (UserDefaults.standard.dictionary(forKey: key) as? [String: [String]]) ?? [:]
        d[vin] = addrs
        UserDefaults.standard.set(d, forKey: key)
    }
}

struct FaultEvent: Codable, Identifiable, Hashable {
    var id = UUID()
    let date: Date
    let vin: String
    let module: String
    let moduleName: String
    let code: String          // "" = module OK, "CLEARED" = clear event
    let state: String

    private static let key = "faults.history.v1"
    static func load() -> [FaultEvent] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([FaultEvent].self, from: d)) ?? []
    }
    static func save(_ e: [FaultEvent]) {
        if let d = try? JSONEncoder().encode(Array(e.suffix(4000))) { UserDefaults.standard.set(d, forKey: key) }
    }
}

struct FaultSummary: Identifiable {
    let module: String, moduleName: String, code: String
    var first: Date, last: Date, seen: Int, state: String, cleared: Int, cameBack: Bool
    var id: String { module + code }
}

// MARK: - Report model

struct VehicleReport {
    struct Module: Identifiable {
        let address: String, name: String, present: Bool
        let faults: [(code: String, state: String, description: String, detail: String)]
        let part: String?, system: String?
        var id: String { address }
    }
    var date = Date()
    var brand: String?
    var vin: String?
    var adapter = "", proto = ""
    var battery: Double?
    var mil: Bool?
    var readiness: [(String, Bool)] = []
    var obdCodes: [(String, [DTC])] = []
    var modules: [Module] = []
    var mileage: [(String, Int)] = []
    var snapshot: [(String, String)] = []
    var notes: [(String, String)] = []
    var faultCount: Int { modules.reduce(0) { $0 + $1.faults.count } + obdCodes.reduce(0) { $0 + $1.1.count } }
}

// MARK: - OBDService extras

extension OBDService {
    /// SEAT/VW engine oil temperature (DID 11BD, 0.1 K) — found on the KJ 1.6 MPI.
    func readOilTemp() async -> Double? {
        guard let m = VAGModule.all.first(where: { $0.address == "01" }) else { return nil }
        await vagOpen(m)
        let p = try? await readDID(0x11BD)
        await vagClose()
        guard let p, p.count >= 2 else { return nil }
        return Double(UInt16(p[0]) << 8 | UInt16(p[1])) / 10 - 273.15
    }

    /// Odometer copies kept by other modules (VW Group: engine 10E0, infotainment 02BD; km in bytes 1…3).
    func vagMileage() async -> [(String, Int)] {
        var out = [(String, Int)]()
        for (addr, did, name) in [("01", UInt16(0x10E0), "Engine"), ("5F", UInt16(0x02BD), "Infotainment")] {
            guard let m = VAGModule.all.first(where: { $0.address == addr }) else { continue }
            await vagOpen(m)
            if let p = try? await readDID(did), p.count >= 4 {
                let km = Int(p[1]) << 16 | Int(p[2]) << 8 | Int(p[3])
                if km > 0 { out.append((name, km)) }
            }
            await vagClose()
        }
        return out
    }
}

// MARK: - Session extras

extension VehicleSession {
    func refreshModuleList() {
        if family == .hyundai {
            vagModules = HyundaiModuleMemory.load(vin ?? "").map(VAGModule.hyundai)
        } else {
            vagModules = VAGModule.all
        }
        vagReports = []
    }

    func recordFaults(module m: VAGModule, faults: [VAGFault]) {
        let now = Date()
        if faults.isEmpty {
            faultHistory.append(FaultEvent(date: now, vin: vin ?? "", module: m.address, moduleName: m.name, code: "", state: "OK"))
        }
        for f in faults {
            faultHistory.append(FaultEvent(date: now, vin: vin ?? "", module: m.address, moduleName: m.name,
                                           code: f.code, state: f.state))
        }
    }

    func recordClear(module m: VAGModule) {
        faultHistory.append(FaultEvent(date: Date(), vin: vin ?? "", module: m.address, moduleName: m.name,
                                       code: "", state: "CLEARED"))
    }

    var faultSummaries: [FaultSummary] {
        var by = [String: FaultSummary]()
        let clears = faultHistory.filter { $0.state == "CLEARED" }
        for e in faultHistory where !e.code.isEmpty {
            let k = e.module + e.code
            if var s = by[k] {
                s.seen += 1
                if e.date >= s.last { s.last = e.date; s.state = e.state }
                by[k] = s
            } else {
                by[k] = FaultSummary(module: e.module, moduleName: e.moduleName, code: e.code, first: e.date, last: e.date,
                                     seen: 1, state: e.state, cleared: 0, cameBack: false)
            }
        }
        for k in by.keys {
            let s = by[k]!
            let cl = clears.filter { $0.module == s.module && $0.date > s.first }
            by[k]!.cleared = cl.count
            by[k]!.cameBack = cl.contains { s.last > $0.date }
        }
        return by.values.sorted { $0.last > $1.last }
    }

    /// Alerts while driving: high coolant / oil, voltage out of range. Debounced per kind.
    func checkAlerts() {
        let coolantMax = UserDefaults.standard.object(forKey: "alertCoolant") as? Double ?? 110
        let oilMax = UserDefaults.standard.object(forKey: "alertOil") as? Double ?? 125
        if let c = values[0x05], c >= coolantMax { raise("coolant", "Coolant temperature high: \(Int(c)) °C") }
        if let o = oilTemp, o >= oilMax { raise("oil", "Oil temperature high: \(Int(o)) °C") }
        if let v = batteryVoltage {
            if v >= 15.0 { raise("vhigh", String(format: "High system voltage: %.1f V", v)) }
            if v <= 11.8, (values[0x0C] ?? 0) > 400 { raise("vlow", String(format: "Low voltage while running: %.1f V", v)) }
        }
    }

    private static var lastAlert = [String: Date]()
    private func raise(_ key: String, _ text: String) {
        if let t = Self.lastAlert[key], Date().timeIntervalSince(t) < 60 { return }
        Self.lastAlert[key] = Date()
        alert = text
        Task { try? await Task.sleep(nanoseconds: 8_000_000_000); if alert == text { alert = nil } }
    }

    /// Every couple of minutes: generic stored + pending codes; a new code raises an alert.
    func watchFaults(_ svc: OBDService) async {
        let codes = Set((await svc.dtcs(mode: "03", kind: .stored) + svc.dtcs(mode: "07", kind: .pending)).map(\.code))
        if let known = knownFaultCodes, !codes.subtracting(known).isEmpty {
            raise("dtc", "New fault detected: " + codes.subtracting(known).sorted().joined(separator: ", "))
        }
        knownFaultCodes = codes
    }

    // MARK: Full scan report
    func buildReport() async {
        reportProgress = (0, "Vehicle identification")
        let fam = family
        let brandName = vehicle?.brand.rawValue
        await exclusive { svc in
            var r = VehicleReport()
            r.brand = brandName
            r.adapter = adapterVersion
            r.proto = protocolName
            r.vin = await svc.vin()
            if let ready = await svc.readiness() {
                r.mil = ready.milOn
                r.readiness = ready.monitors.filter(\.supported).map { ($0.name, $0.complete) }
            }
            let snapIDs: [UInt8] = [0x0C, 0x0D, 0x05, 0x0F, 0x46, 0x04, 0x11, 0x42, 0x33, 0x2F, 0x06, 0x07, 0x1F, 0x31]
            let snap = await svc.read(snapIDs.filter { supported.isEmpty || supported.contains($0) }.compactMap { PIDs.byID[$0] })
            r.battery = snap[0x42]
            r.snapshot = snapIDs.compactMap { id in
                guard let v = snap[id], let p = PIDs.byID[id] else { return nil }
                return (p.name, String(format: "%.1f %@", v, p.unit))
            }
            reportProgress = (0.1, "Generic OBD-II codes")
            for ecu in await svc.discoverECUs() { r.obdCodes.append((ecu.name, await svc.dtcs(for: ecu))) }
            if await svc.supportsVAG {
                var mods = fam == .hyundai ? HyundaiModuleMemory.load(r.vin ?? "").map(VAGModule.hyundai) : VAGModule.all
                if fam == .hyundai && mods.isEmpty {
                    reportProgress = (0.12, "Searching for modules on the car")
                    let found = await svc.hyundaiDiscover { _, _ in }
                    HyundaiModuleMemory.save(r.vin ?? "", found.map(\.address))
                    mods = found
                }
                for (i, m) in mods.enumerated() {
                    reportProgress = (0.15 + 0.75 * Double(i) / Double(max(mods.count, 1)), "\(m.address) · \(m.name)")
                    let rep: VAGReport = fam == .hyundai ? await svc.hyundaiReport(m)
                        : (await svc.vagReport(m) ?? VAGReport(module: m, present: false, faults: []))
                    if rep.present { recordFaults(module: m, faults: rep.faults) }
                    r.modules.append(.init(address: m.address, name: m.name, present: rep.present,
                                           faults: rep.faults.map { ($0.code, $0.state, $0.description, $0.detail) },
                                           part: rep.partNumber, system: rep.systemName))
                }
                if fam == .vag {
                    reportProgress = (0.92, "Mileage cross-check")
                    r.mileage = await svc.vagMileage()
                }
            }
            if let ab = r.modules.first(where: { $0.name.lowercased().contains("airbag") }), ab.present {
                r.notes.append(("Airbag", ab.faults.isEmpty
                                ? "No airbag faults stored — no deployment crash recorded in this module."
                                : "Airbag module has \(ab.faults.count) fault(s) — check for crash data stored."))
            }
            if r.mileage.count >= 2 {
                let kms = r.mileage.map(\.1)
                let list = r.mileage.map { "\($0.0) \($0.1.formatted()) km" }.joined(separator: ", ")
                r.notes.append(("Mileage", (kms.max()! - kms.min()!) <= 50
                                ? "Consistent across modules (\(list)) — no sign of tampering."
                                : "MISMATCH between modules (\(list)) — a module may have been swapped or the odometer altered."))
            }
            report = r
        }
        reportProgress = nil
    }
}
