import Foundation

// MARK: - UDS errors

struct UDSNegative: LocalizedError {
    let sid: UInt8, nrc: UInt8
    static let names: [UInt8: String] = [
        0x10: "General reject", 0x11: "Service not supported", 0x12: "Sub-function not supported",
        0x13: "Incorrect message length", 0x22: "Conditions not correct", 0x24: "Request sequence error",
        0x31: "Request out of range", 0x33: "Security access denied (login required)", 0x35: "Invalid key",
        0x72: "General programming failure", 0x7E: "Not supported in active session",
        0x7F: "Service not supported in active session",
    ]
    var errorDescription: String? {
        String(format: "Module rejected 0x%02X: ", sid) + (Self.names[nrc] ?? String(format: "NRC 0x%02X", nrc))
    }
}

// MARK: - Measurement (live data) definitions

struct Measurement: Identifiable, Codable, Hashable {
    enum Kind: String, Codable, CaseIterable { case number, hex, ascii }
    var id = UUID()
    var module: String            // VAG address, e.g. "01"
    var did: UInt16
    var name: String
    var kind: Kind = .number
    var offset: Int = 0           // byte offset inside DID payload
    var length: Int = 2           // 1, 2 or 4 bytes
    var signed = false
    var scale: Double = 1
    var add: Double = 0
    var unit: String = ""

    var didHex: String { String(format: "%04X", did) }

    func decode(_ p: [UInt8]) -> String {
        switch kind {
        case .hex: return p.map { String(format: "%02X", $0) }.joined(separator: " ")
        case .ascii: return String(decoding: p.filter { (0x20...0x7E).contains($0) }, as: UTF8.self)
        case .number:
            guard let v = numeric(p) else { return "—" }
            return (abs(v) >= 100 || v == v.rounded() ? String(format: "%.0f", v) : String(format: "%.2f", v))
                + (unit.isEmpty ? "" : " " + unit)
        }
    }

    func numeric(_ p: [UInt8]) -> Double? {
        guard kind == .number, offset >= 0, offset + length <= p.count else { return nil }
        var raw: UInt64 = 0
        for b in p[offset..<(offset + length)] { raw = raw << 8 | UInt64(b) }
        let bits = UInt64(length * 8)
        let v: Double = signed && raw & (1 << (bits - 1)) != 0
            ? Double(Int64(bitPattern: raw | (~0 << bits)))
            : Double(raw)
        return v * scale + add
    }

    private static let key = "vag.measurements.v1"
    static func load() -> [Measurement] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([Measurement].self, from: d)) ?? []
    }
    static func save(_ m: [Measurement]) {
        if let d = try? JSONEncoder().encode(m) { UserDefaults.standard.set(d, forKey: key) }
    }
}

/// Standard UDS identification DIDs every VAG UDS module answers.
enum StandardDID {
    static let all: [(UInt16, String)] = [
        (0xF187, "Spare Part Number"), (0xF189, "Software Version"), (0xF191, "Hardware Number"),
        (0xF197, "System Name"), (0xF18C, "Serial Number"), (0xF19E, "ASAM/ODX File"),
        (0xF1A2, "ODX Version"), (0xF1A3, "Hardware Version"), (0xF190, "VIN"), (0x0600, "Coding"),
    ]
}

// MARK: - Coding backups & recipes

struct CodingBackup: Identifiable, Codable, Hashable {
    var id = UUID()
    let module: String
    let vin: String
    let date: Date
    let coding: [UInt8]
    var note: String
    var hex: String { coding.map { String(format: "%02X", $0) }.joined() }

    private static let key = "vag.coding.backups.v1"
    static func load() -> [CodingBackup] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([CodingBackup].self, from: d)) ?? []
    }
    static func save(_ b: [CodingBackup]) {
        if let d = try? JSONEncoder().encode(b) { UserDefaults.standard.set(d, forKey: key) }
    }
}

/// A saved one-tap change: set the masked bits of one coding byte to `value`.
struct CodingRecipe: Identifiable, Codable, Hashable {
    var id = UUID()
    var module: String
    var name: String
    var byte: Int
    var mask: UInt8
    var value: UInt8

    func apply(to c: [UInt8]) -> [UInt8]? {
        guard byte < c.count else { return nil }
        var out = c
        out[byte] = (c[byte] & ~mask) | (value & mask)
        return out
    }
    func isApplied(_ c: [UInt8]) -> Bool { byte < c.count && c[byte] & mask == value & mask }

    private static let key = "vag.coding.recipes.v1"
    static func load() -> [CodingRecipe] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([CodingRecipe].self, from: d)) ?? []
    }
    static func save(_ r: [CodingRecipe]) {
        if let d = try? JSONEncoder().encode(r) { UserDefaults.standard.set(d, forKey: key) }
    }
}

// MARK: - Service

extension OBDService {
    /// Finds a negative response (7F sid nrc) that is not "response pending".
    func negative(_ d: [UInt8], sid: UInt8) -> UDSNegative? {
        var i = 0
        while i + 2 < d.count {
            if d[i] == 0x7F, d[i + 1] == sid, d[i + 2] != 0x78 { return UDSNegative(sid: sid, nrc: d[i + 2]) }
            i += 1
        }
        return nil
    }

    /// 22 DID → payload (after 62 DIDhi DIDlo). Channel must already be open.
    func readDID(_ did: UInt16, timeout: Double = 1) async throws -> [UInt8] {
        let d = try await elm.requestUDS(String(format: "22%04X", did), timeout: timeout, pendingWait: 3)
        if let p = positive(d, sid: 0x62, sub: UInt8(did >> 8)), p.count >= 3, p[p.startIndex + 2] == UInt8(did & 0xFF) {
            return Array(p.dropFirst(3))
        }
        throw negative(d, sid: 0x22) ?? ELMError.noData
    }

    func session(_ type: UInt8) async throws {
        let d = try await elm.requestUDS(String(format: "10%02X", type), timeout: 1.5)
        if positive(d, sid: 0x50, sub: type) == nil { throw negative(d, sid: 0x10) ?? ELMError.noData }
    }

    func writeDID(_ did: UInt16, _ data: [UInt8]) async throws {
        let cmd = String(format: "2E%04X", did) + data.map { String(format: "%02X", $0) }.joined()
        let d = try await elm.requestUDS(cmd, timeout: 5)
        if positive(d, sid: 0x6E, sub: UInt8(did >> 8)) == nil { throw negative(d, sid: 0x2E) ?? ELMError.noData }
    }

    func readCoding(_ m: VAGModule) async throws -> [UInt8] {
        await vagOpen(m)
        do { let c = try await readDID(0x0600); await vagClose(); return c }
        catch { await vagClose(); throw error }
    }

    /// Writes long coding in extended session, then reads back to verify.
    func writeCoding(_ m: VAGModule, _ coding: [UInt8]) async throws -> [UInt8] {
        await vagOpen(m)
        do {
            try await session(0x03)
            try await writeDID(0x0600, coding)
            let back = try await readDID(0x0600)
            try? await session(0x01)
            await vagClose()
            return back
        } catch {
            try? await session(0x01)
            await vagClose()
            throw error
        }
    }
}
