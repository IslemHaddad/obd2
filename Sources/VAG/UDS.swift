import Foundation

/// UDS (ISO 14229) access to VW Group modules through the ELM327.
extension OBDService {
    var supportsVAG: Bool { get async { [6, 8].contains(await elm.protocolNumber) } }   // CAN 11-bit

    /// Physically address one module: header, receive filter and flow-control to the right IDs.
    func vagOpen(_ m: VAGModule) async {
        for c in ["ATSH" + m.request, "ATCRA" + m.response, "ATFCSH" + m.request, "ATFCSD300000", "ATFCSM1"] {
            _ = try? await elm.send(c, timeout: 1)
        }
    }

    func vagClose() async {
        for c in ["ATFCSM0", "ATCRA", "ATSH7DF"] { _ = try? await elm.send(c, timeout: 1) }
    }

    /// Strips "response pending" (7F xx 78) frames and returns the bytes from the first positive response `sid`.
    func positive(_ d: [UInt8], sid: UInt8, sub: UInt8? = nil) -> ArraySlice<UInt8>? {
        var i = 0
        while i < d.count {
            if d[i] == sid, sub == nil || (i + 1 < d.count && d[i + 1] == sub) { return d[i...] }
            i += 1
        }
        return nil
    }

    /// Reads one module. Returns nil when the module is not fitted / not answering.
    func vagReport(_ m: VAGModule) async -> VAGReport? {
        await vagOpen(m)
        guard let d = try? await elm.request("1902FF", timeout: 1.2),
              let r = positive(d, sid: 0x59, sub: 0x02) else { await vagClose(); return nil }
        var faults = [VAGFault]()
        let rec = Array(r.dropFirst(3))           // 59 02 <availabilityMask>
        var j = 0
        while j + 3 < rec.count {
            let dtc = OBDService.decodeDTC(rec[j], rec[j + 1])
            let f = VAGFault(dtc: dtc, failureType: rec[j + 2], status: rec[j + 3])
            if (rec[j] | rec[j + 1] | rec[j + 2]) != 0, rec[j + 3] != 0, !faults.contains(f) { faults.append(f) }
            j += 4
        }
        let part = await readID(0xF187)
        let name = await readID(0xF197)
        await vagClose()
        return VAGReport(module: m, present: true, faults: faults, partNumber: part, systemName: name)
    }

    private func readID(_ did: UInt16) async -> String? {
        let cmd = String(format: "22%04X", did)
        guard let d = try? await elm.request(cmd, timeout: 1),
              let r = positive(d, sid: 0x62, sub: UInt8(did >> 8)) else { return nil }
        let s = String(decoding: r.dropFirst(3).filter { (0x20...0x7E).contains($0) }, as: UTF8.self)
            .trimmingCharacters(in: .whitespaces)
        return s.isEmpty ? nil : s
    }

    /// Clears one module. Retries in extended session if the module refuses in default session.
    func vagClear(_ m: VAGModule) async throws {
        await vagOpen(m)
        var ok = false
        if let d = try? await elm.request("14FFFFFF", timeout: 3), positive(d, sid: 0x54) != nil { ok = true }
        if !ok {
            _ = try? await elm.request("1003", timeout: 1)
            if let d = try? await elm.request("14FFFFFF", timeout: 3), positive(d, sid: 0x54) != nil { ok = true }
            _ = try? await elm.request("1001", timeout: 1)
        }
        await vagClose()
        if !ok { throw ELMError.error("\(m.name) refused to clear codes") }
    }
}
