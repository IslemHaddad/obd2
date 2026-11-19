import Foundation

struct DTC: Identifiable, Hashable {
    enum Kind: String { case stored = "Stored", pending = "Pending", permanent = "Permanent" }
    let code: String
    let kind: Kind
    var id: String { kind.rawValue + code }
    var description: String { DTCDatabase.describe(code) }
}

struct ReadinessMonitor: Identifiable {
    let name: String
    let supported: Bool
    let complete: Bool
    var id: String { name }
}

struct ReadinessStatus {
    let milOn: Bool
    let dtcCount: Int
    let monitors: [ReadinessMonitor]
}

struct MonitorTest: Identifiable {
    let mid: UInt8
    let tid: UInt8
    let value: Double
    let low: Double
    let high: Double
    var unit: String = ""
    var id: String { String(format: "%02X-%02X", mid, tid) }
    var passed: Bool { low <= value && value <= high }
    var name: String {
        (MonitorTest.midNames[mid] ?? String(format: "Monitor $%02X", mid)) + String(format: " · test $%02X", tid)
    }

    /// SAE J1979 unit-and-scaling IDs: (scale, unit).
    static func unit(_ uas: UInt8) -> (Double, String) {
        switch uas {
        case 0x01: (1.0, ""); case 0x02: (0.1, ""); case 0x03: (0.01, ""); case 0x04: (0.001, "")
        case 0x07: (0.25, "rpm"); case 0x08: (0.01, "km/h"); case 0x09: (1.0, "km/h")
        case 0x0A: (0.122, "mV"); case 0x0B: (0.001, "V"); case 0x0C: (0.01, "V")
        case 0x10: (1.0, "ms"); case 0x12: (0.1, "s"); case 0x1A: (1.0, "kPa")
        case 0x22: (0.1, "°C"); case 0x27: (0.1, "%"); case 0x30: (1.0, "count"); case 0x31: (1.0, "km")
        default: (1.0, "")
        }
    }
    static let midNames: [UInt8: String] = [
        0x01: "O2 Sensor B1S1", 0x02: "O2 Sensor B1S2", 0x05: "O2 Sensor B2S1", 0x06: "O2 Sensor B2S2",
        0x21: "Catalyst Bank 1", 0x22: "Catalyst Bank 2", 0x31: "EGR Monitor", 0x39: "EVAP Monitor",
        0x41: "O2 Heater B1", 0x42: "O2 Heater B2", 0xA1: "Misfire General",
        0xA2: "Misfire Cyl.1", 0xA3: "Misfire Cyl.2", 0xA4: "Misfire Cyl.3", 0xA5: "Misfire Cyl.4"]
}

/// High-level OBD-II services on top of the ELM327 channel.
struct OBDService {
    let elm: ELM327

    // MARK: Supported PIDs
    func supportedPIDs() async -> Set<UInt8> {
        var set = Set<UInt8>()
        var base: UInt8 = 0x00
        while true {
            guard let d = try? await elm.request(String(format: "01%02X", base)),
                  let i = indexAfter(d, 0x41, base), d.count >= i + 4 else { break }
            let mask = UInt32(d[i]) << 24 | UInt32(d[i+1]) << 16 | UInt32(d[i+2]) << 8 | UInt32(d[i+3])
            for bit in 0..<32 where mask & (1 << (31 - bit)) != 0 { set.insert(base &+ UInt8(bit + 1)) }
            guard set.contains(base &+ 0x20), base < 0xE0 else { break }
            base &+= 0x20
        }
        return set
    }

    // MARK: Live data (batched: up to 6 PIDs per CAN request)
    func read(_ pids: [PID]) async -> [UInt8: Double] {
        var out = [UInt8: Double]()
        let can = await elm.isCAN
        let chunk = can ? 6 : 1
        var i = 0
        while i < pids.count {
            let group = Array(pids[i..<min(i + chunk, pids.count)])
            i += chunk
            let cmd = "01" + group.map(\.hex).joined()
            guard let d = try? await elm.request(cmd) else { continue }
            parseMode01(d, into: &out)
        }
        return out
    }

    private func parseMode01(_ d: [UInt8], into out: inout [UInt8: Double]) {
        var i = 0
        while i < d.count {
            guard d[i] == 0x41 else { i += 1; continue }
            i += 1
            while i < d.count, d[i] != 0x41 {
                let pid = d[i]
                guard let len = PIDs.length(of: pid), i + 1 + len <= d.count else { i = d.count; break }
                if let p = PIDs.byID[pid], out[pid] == nil {
                    out[pid] = p.decode(Array(d[(i + 1)...(i + len)]))
                }
                i += 1 + len
            }
        }
    }

    // MARK: DTCs
    func dtcs(mode: String, kind: DTC.Kind) async -> [DTC] {
        let resp = UInt8(Int(mode, radix: 16)! + 0x40)
        let can = await elm.isCAN
        var bytes = [UInt8]()
        if can {
            guard let merged = try? await elm.request(mode, timeout: 4) else { return [] }
            // Multiple ECUs may answer: each block = 43 NN codes...
            var i = 0
            while i < merged.count {
                guard merged[i] == resp, i + 1 < merged.count else { i += 1; continue }
                let n = Int(merged[i + 1])
                let start = i + 2, end = min(start + n * 2, merged.count)
                bytes += merged[start..<end]
                i = end
            }
        } else {
            guard let lines = try? await elm.requestLines(mode, timeout: 4) else { return [] }
            for l in lines where l.first == resp { bytes += l.dropFirst() }
        }
        var codes = [DTC]()
        var seen = Set<String>()
        stride(from: 0, to: bytes.count - 1, by: 2).forEach { j in
            let a = bytes[j], b = bytes[j + 1]
            guard a != 0 || b != 0 else { return }
            let c = Self.decodeDTC(a, b)
            if seen.insert(c).inserted { codes.append(DTC(code: c, kind: kind)) }
        }
        return codes
    }

    func allDTCs() async -> [DTC] {
        await dtcs(mode: "03", kind: .stored) + dtcs(mode: "07", kind: .pending) + dtcs(mode: "0A", kind: .permanent)
    }

    func clearDTCs() async throws { _ = try await elm.send("04", timeout: 5) }

    static func decodeDTC(_ a: UInt8, _ b: UInt8) -> String {
        let sys = ["P", "C", "B", "U"][Int(a >> 6)]
        return String(format: "%@%X%X%02X", sys, (a >> 4) & 0x3, a & 0xF, b)
    }

    // MARK: Readiness (PID 01)
    func readiness() async -> ReadinessStatus? {
        guard let d = try? await elm.request("0101"), let i = indexAfter(d, 0x41, 0x01), d.count >= i + 4 else { return nil }
        let A = d[i], B = d[i+1], C = d[i+2], D = d[i+3]
        let diesel = B & 0x08 != 0
        var m: [ReadinessMonitor] = [
            .init(name: "Misfire", supported: B & 0x01 != 0, complete: B & 0x10 == 0),
            .init(name: "Fuel System", supported: B & 0x02 != 0, complete: B & 0x20 == 0),
            .init(name: "Components", supported: B & 0x04 != 0, complete: B & 0x40 == 0),
        ]
        let names = diesel
            ? ["NMHC Catalyst", "NOx/SCR", "", "Boost Pressure", "", "Exhaust Gas Sensor", "PM Filter", "EGR/VVT"]
            : ["Catalyst", "Heated Catalyst", "Evaporative", "Secondary Air", "A/C Refrigerant", "O2 Sensor", "O2 Heater", "EGR/VVT"]
        for bit in 0..<8 where !names[bit].isEmpty {
            m.append(.init(name: names[bit], supported: C & (1 << bit) != 0, complete: D & (1 << bit) == 0))
        }
        return ReadinessStatus(milOn: A & 0x80 != 0, dtcCount: Int(A & 0x7F), monitors: m)
    }

    // MARK: Freeze frame (mode 02, frame 0)
    func freezeFrame(_ pids: [PID]) async -> [UInt8: Double] {
        var out = [UInt8: Double]()
        for p in pids {
            guard let d = try? await elm.request("02\(p.hex)00"),
                  let i = indexAfter(d, 0x42, p.id), d.count >= i + 1 + p.bytes else { continue }
            out[p.id] = p.decode(Array(d[(i + 1)..<(i + 1 + p.bytes)]))
        }
        return out
    }

    // MARK: Mode 06 — on-board monitor test results
    func supportedMIDs() async -> Set<UInt8> {
        var set = Set<UInt8>()
        var base: UInt8 = 0x00
        while base < 0xA0 {
            guard let d = try? await elm.request(String(format: "06%02X", base)),
                  let i = indexAfter(d, 0x46, base), d.count >= i + 4 else { break }
            let mask = UInt32(d[i]) << 24 | UInt32(d[i+1]) << 16 | UInt32(d[i+2]) << 8 | UInt32(d[i+3])
            for bit in 0..<32 where mask & (1 << (31 - bit)) != 0 { set.insert(base &+ UInt8(bit + 1)) }
            guard mask & 1 != 0 else { break }
            base &+= 0x20
        }
        return set
    }

    func monitorTests(_ mids: Set<UInt8>? = nil) async -> [MonitorTest] {
        let base: Set<UInt8>
        if let mids { base = mids } else { base = await supportedMIDs() }
        let ids = base.filter { $0 % 0x20 != 0 }.sorted()
        var out = [MonitorTest]()
        for mid in ids {
            guard let d = try? await elm.request(String(format: "06%02X", mid)),
                  let start = d.firstIndex(of: 0x46) else { continue }
            var j = start + 1
            while j + 8 < d.count {
                let gMid = d[j], tid = d[j + 1], uas = d[j + 2]
                if gMid == 0 || gMid % 0x20 == 0 { break }
                let val = UInt16(d[j + 3]) << 8 | UInt16(d[j + 4])
                let lo = UInt16(d[j + 5]) << 8 | UInt16(d[j + 6])
                let hi = UInt16(d[j + 7]) << 8 | UInt16(d[j + 8])
                let (sc, unit) = MonitorTest.unit(uas)
                out.append(MonitorTest(mid: gMid, tid: tid, value: Double(val) * sc,
                                       low: Double(lo) * sc, high: Double(hi) * sc, unit: unit))
                j += 9
            }
        }
        return out
    }

    // MARK: Vehicle info (mode 09)
    func vin() async -> String? { await mode09String(0x02) }
    func calibrationID() async -> String? { await mode09String(0x04) }
    func ecuName() async -> String? { await mode09String(0x0A) }

    private func mode09String(_ pid: UInt8) async -> String? {
        guard let d = try? await elm.request(String(format: "09%02X", pid), timeout: 4),
              let i = indexAfter(d, 0x49, pid) else { return nil }
        let s = String(decoding: d[i...].filter { (0x20...0x7E).contains($0) }, as: UTF8.self)
            .trimmingCharacters(in: .whitespaces)
        return s.isEmpty ? nil : s
    }

    func batteryVoltage() async -> Double? {
        guard let s = try? await elm.send("ATRV").first else { return nil }
        return Double(s.filter { $0.isNumber || $0 == "." })
    }

    /// Index right after [mode, pid] header.
    private func indexAfter(_ d: [UInt8], _ mode: UInt8, _ pid: UInt8) -> Int? {
        guard d.count >= 2 else { return nil }
        for i in 0..<(d.count - 1) where d[i] == mode && d[i + 1] == pid { return i + 2 }
        return nil
    }
}

// MARK: - Per-module (ECU) addressing — CAN only

struct ECU: Identifiable, Hashable {
    let request: String     // header we send to (e.g. 7E0 / 18DA10F1)
    let response: String    // header it answers from (e.g. 7E8 / 18DAF110)
    var id: String { request }
    var name: String {
        switch request {
        case "7E0", "18DA10F1": "Engine (ECM)"
        case "7E1", "18DA18F1": "Transmission (TCM)"
        default: "Module \(response)"
        }
    }
    static let broadcast = ECU(request: "*", response: "*")
}

extension OBDService {
    private func is29bit() async -> Bool { [7, 9].contains(await elm.protocolNumber) }
    private func functionalHeader() async -> String { await is29bit() ? "18DB33F1" : "7DF" }

    /// Asks every emissions ECU to answer 0100 with headers on, collects responder IDs.
    func discoverECUs() async -> [ECU] {
        guard await elm.isCAN else { return [.broadcast] }
        let wide = await is29bit()
        _ = try? await elm.send("ATH1")
        guard let lines = try? await elm.send("0100", timeout: 3) else { _ = try? await elm.send("ATH0"); return [.broadcast] }
        _ = try? await elm.send("ATH0")
        var seen = [String]()
        for l in lines {
            let hdr = String(l.prefix(wide ? 8 : 3))
            guard hdr.count == (wide ? 8 : 3), Int(hdr, radix: 16) != nil, !seen.contains(hdr) else { continue }
            if wide ? hdr.hasPrefix("18DAF1") : (0x7E8...0x7EF).contains(Int(hdr, radix: 16)!) { seen.append(hdr) }
        }
        let ecus = seen.sorted().map { r -> ECU in
            if wide { return ECU(request: "18DA" + r.suffix(2) + "F1", response: r) }
            return ECU(request: String(format: "%03X", Int(r, radix: 16)! - 8), response: r)
        }
        return ecus.isEmpty ? [.broadcast] : ecus
    }

    /// Runs `body` with requests physically addressed to one ECU, then restores broadcast.
    func on<T>(_ ecu: ECU, _ body: () async throws -> T) async throws -> T {
        guard ecu != .broadcast else { return try await body() }
        _ = try? await elm.send("ATSH" + ecu.request)
        do {
            let r = try await body()
            _ = try? await elm.send("ATSH" + (await functionalHeader()))
            return r
        } catch {
            _ = try? await elm.send("ATSH" + (await functionalHeader()))
            throw error
        }
    }

    func dtcs(for ecu: ECU) async -> [DTC] { (try? await on(ecu) { await allDTCs() }) ?? [] }

    func clearDTCs(for ecu: ECU) async throws { try await on(ecu) { try await clearDTCs() } }
}
