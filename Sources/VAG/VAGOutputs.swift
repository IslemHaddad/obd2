import Foundation

// MARK: - Adaptation definitions

struct Adaptation: Identifiable, Codable, Hashable {
    enum Kind: String, Codable, CaseIterable { case number, toggle, ascii, hex }
    var id = UUID()
    var module: String
    var did: UInt16
    var name: String
    var kind: Kind = .number
    var offset: Int = 0          // byte offset of the value inside the DID payload
    var length: Int = 1          // bytes (number/toggle)
    var scale: Double = 1
    var add: Double = 0
    var unit: String = ""

    var didHex: String { String(format: "%04X", did) }
    var backupKey: String { "\(module)/A/\(didHex)" }

    func number(_ p: [UInt8]) -> Double? {
        guard offset + length <= p.count else { return nil }
        var raw: UInt64 = 0
        for b in p[offset..<(offset + length)] { raw = raw << 8 | UInt64(b) }
        return Double(raw) * scale + add
    }

    /// Writes a physical value back into the payload (big-endian, unsigned).
    func patch(_ p: [UInt8], value: Double) -> [UInt8]? {
        guard offset + length <= p.count, scale != 0 else { return nil }
        let raw = ((value - add) / scale).rounded()
        let maxRaw = pow(2.0, Double(length * 8)) - 1
        guard raw >= 0, raw <= maxRaw else { return nil }
        var r = UInt64(raw), out = p
        for i in stride(from: offset + length - 1, through: offset, by: -1) { out[i] = UInt8(r & 0xFF); r >>= 8 }
        return out
    }

    func patch(_ p: [UInt8], ascii: String) -> [UInt8] {
        var bytes = Array(ascii.utf8.prefix(p.count - offset))
        bytes += Array(repeating: 0x20, count: max(0, p.count - offset - bytes.count))
        return Array(p[0..<offset]) + bytes
    }

    private static let key = "vag.adaptations.v1"
    static func load() -> [Adaptation] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([Adaptation].self, from: d)) ?? []
    }
    static func save(_ a: [Adaptation]) {
        if let d = try? JSONEncoder().encode(a) { UserDefaults.standard.set(d, forKey: key) }
    }
}

// MARK: - Output test definitions

struct OutputTest: Identifiable, Codable, Hashable {
    enum Method: String, Codable, CaseIterable {
        case ioControl = "I/O Control (2F)"
        case routine = "Routine (31)"
    }
    var id = UUID()
    var module: String
    var name: String
    var method: Method = .ioControl
    var identifier: UInt16        // DID for 2F, RID for 31
    var data: [UInt8] = []        // control state / routine option record
    var duration: Double = 10     // seconds before auto-stop

    var idHex: String { String(format: "%04X", identifier) }
    var dataHex: String { data.map { String(format: "%02X", $0) }.joined() }

    var startCommand: String {
        switch method {
        case .ioControl: "2F" + idHex + "03" + dataHex      // shortTermAdjustment
        case .routine: "3101" + idHex + dataHex             // startRoutine
        }
    }
    var stopCommand: String {
        switch method {
        case .ioControl: "2F" + idHex + "00"                // returnControlToECU
        case .routine: "3102" + idHex                       // stopRoutine
        }
    }
    var positiveSID: UInt8 { method == .ioControl ? 0x6F : 0x71 }
    var requestSID: UInt8 { method == .ioControl ? 0x2F : 0x31 }

    private static let key = "vag.outputtests.v1"
    static func load() -> [OutputTest] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([OutputTest].self, from: d)) ?? []
    }
    static func save(_ t: [OutputTest]) {
        if let d = try? JSONEncoder().encode(t) { UserDefaults.standard.set(d, forKey: key) }
    }
}

// MARK: - Service

extension OBDService {
    func readAdaptation(_ m: VAGModule, _ did: UInt16) async throws -> [UInt8] {
        await vagOpen(m)
        do { let p = try await readDID(did); await vagClose(); return p }
        catch { await vagClose(); throw error }
    }

    /// Extended session → write → read back.
    func writeAdaptation(_ m: VAGModule, _ did: UInt16, _ payload: [UInt8]) async throws -> [UInt8] {
        await vagOpen(m)
        do {
            try await session(0x03)
            try await writeDID(did, payload)
            let back = try await readDID(did)
            try? await session(0x01)
            await vagClose()
            return back
        } catch {
            try? await session(0x01)
            await vagClose()
            throw error
        }
    }

    /// Sends a raw UDS request, returns positive payload or throws the NRC.
    func uds(_ cmd: String, positive sid: UInt8, request rsid: UInt8, timeout: Double = 3) async throws -> [UInt8] {
        let d = try await elm.requestUDS(cmd, timeout: timeout)
        if let p = positive(d, sid: sid) { return Array(p) }
        throw negative(d, sid: rsid) ?? ELMError.noData
    }

    func testerPresent() async { _ = try? await elm.request("3E00", timeout: 0.5) }
}
