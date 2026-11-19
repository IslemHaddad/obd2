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

    /// Reads the fault list of a module whose channel is already open (19 02 2F, falls back to FF).
    func vagFaultsOpen(_ m: VAGModule) async -> [VAGFault]? {
        // Ask only for real faults (mask 2F). Listing all supported DTCs (FF) can be hundreds of records that
        // cheap ELM clones truncate, and most of them are just "test not completed" (status 0x10).
        var resp = try? await elm.requestUDS(String(format: "1902%02X", VAGFault.faultMask), timeout: 2)
        if let d = resp, positive(d, sid: 0x59, sub: 0x02) == nil, d.first == 0x7F {
            resp = try? await elm.requestUDS("1902FF", timeout: 2)
        }
        guard let d = resp, let r = positive(d, sid: 0x59, sub: 0x02) else { return nil }
        var faults = [VAGFault]()
        let rec = Array(r.dropFirst(3))           // 59 02 <availabilityMask>
        var j = 0
        while j + 3 < rec.count {
            let dtc = OBDService.decodeDTC(rec[j], rec[j + 1])
            let f = VAGFault(dtc: dtc, failureType: rec[j + 2], status: rec[j + 3],
                             raw: UInt32(rec[j]) << 16 | UInt32(rec[j + 1]) << 8 | UInt32(rec[j + 2]),
                             powertrain: m.category == .powertrain)
            if (rec[j] | rec[j + 1] | rec[j + 2]) != 0, rec[j + 3] & VAGFault.faultMask != 0,
               !faults.contains(where: { $0.id == f.id }) { faults.append(f) }
            j += 4
        }
        return faults
    }

    /// Reads one module. Returns nil when the module is not fitted / not answering.
    func vagReport(_ m: VAGModule) async -> VAGReport? {
        await vagOpen(m)
        guard let faults = await vagFaultsOpen(m) else { await vagClose(); return nil }
        let part = await readID(0xF187)
        let name = await readID(0xF197)
        await vagClose()
        return VAGReport(module: m, present: true, faults: faults, partNumber: part, systemName: name)
    }

    private func readID(_ did: UInt16) async -> String? {
        let cmd = String(format: "22%04X", did)
        guard let d = try? await elm.requestUDS(cmd, timeout: 1),
              let r = positive(d, sid: 0x62, sub: UInt8(did >> 8)) else { return nil }
        var p = Array(r.dropFirst(3))
        while let last = p.last, [0x00, 0xAA, 0xFF].contains(last) { p.removeLast() }   // VAG padding
        let s = String(decoding: p.filter { (0x20...0x7E).contains($0) }, as: UTF8.self)
            .trimmingCharacters(in: .whitespaces)
        return s.isEmpty ? nil : s
    }

    /// Clears one module. Retries in extended session if the module refuses in default session.
    func vagClear(_ m: VAGModule) async throws {
        await vagOpen(m)
        var ok = false
        var reason = ""
        if let d = try? await elm.requestUDS("14FFFFFF", timeout: 3, pendingWait: 8), positive(d, sid: 0x54) != nil { ok = true }
        if !ok {
            _ = try? await elm.requestUDS("1003", timeout: 1)
            if let d = try? await elm.requestUDS("14FFFFFF", timeout: 3, pendingWait: 8), positive(d, sid: 0x54) != nil { ok = true }
            _ = try? await elm.requestUDS("1001", timeout: 1)
        }
        if !ok && m.category == .powertrain {
            // Engine/gearbox ECUs often only accept SAE mode 04, and some only functionally (7DF).
            if let d = try? await elm.requestUDS("04", timeout: 5, pendingWait: 8), d.contains(0x44) { ok = true }
            if !ok {
                for c in ["ATFCSM0", "ATCRA", "ATSH7DF"] { _ = try? await elm.send(c, timeout: 1) }
                if let d = try? await elm.requestUDS("04", timeout: 5, pendingWait: 8) {
                    if d.contains(0x44) { ok = true }
                    else if d.count >= 3, d[0] == 0x7F, d[2] == 0x22 { reason = " — switch the engine OFF, ignition ON" }
                }
            }
        }
        await vagClose()
        if !ok { throw ELMError.error("\(m.name) refused to clear codes\(reason)") }
    }
}
