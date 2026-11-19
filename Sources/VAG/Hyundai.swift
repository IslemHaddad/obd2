import Foundation

/// Hyundai / Kia diagnostics (ported from the desktop app, verified on a 2018 Grand i10).
/// - Discovery: every 11-bit physical address, several "are you there" probes (modules differ:
///   3E00 / 3E01 / 10 81 / 10 03); any reply on request+8 means the module exists.
/// - DTCs: UDS 19 02 with mask fallbacks and extended session, else KWP2000 18 00 FF 00, else SAE mode 03/07.
/// - Clear: UDS 14 FFFFFF / KWP 14 FF00 (default then extended session), engine falls back to SAE 04.
extension OBDService {
    static let hyundaiProbes = ["3E00", "3E01", "1081", "1003"]

    func hyundaiDiscover(family: VAGBrand.Family = .hyundai, progress: @escaping (Double, Int) async -> Void) async -> [VAGModule] {
        var found = [VAGModule]()
        let ids = (0x700..<0x7E8).filter { $0 != 0x7DF }
        _ = try? await elm.send("ATH1", timeout: 1)
        _ = try? await elm.send("ATST19", timeout: 1)            // ~100 ms receive timeout per probe
        for (n, rid) in ids.enumerated() {
            if n % 8 == 0 { await progress(Double(n) / Double(ids.count), found.count) }
            let req = String(format: "%03X", rid)
            let wants = family.offsets.map { String(format: "%03X", rid + $0) }
            guard (try? await elm.send("ATSH" + req, timeout: 1)) != nil else { continue }
            for probe in Self.hyundaiProbes {
                guard let lines = try? await elm.send(probe, timeout: 0.4) else { continue }
                let flat = lines.map { $0.replacingOccurrences(of: " ", with: "").uppercased() }
                if let hit = wants.first(where: { w in flat.contains { $0.hasPrefix(w) } }) {
                    var m = VAGModule.discovered(req, family)
                    if m.response != hit {
                        m = VAGModule(address: m.address, name: m.name, request: m.request, response: hit,
                                      category: m.category, spot: m.spot, icon: m.icon)
                    }
                    found.append(m)
                    _ = try? await elm.send("1001", timeout: 0.4)   // back to default session
                    break
                }
            }
        }
        for c in ["ATST32", "ATAT2", "ATH0", "ATSH7DF"] { _ = try? await elm.send(c, timeout: 1) }
        await progress(1, found.count)
        return found
    }

    private func hyFault(_ a: UInt8, _ b: UInt8, _ ftb: UInt8, _ status: UInt8) -> VAGFault {
        VAGFault(dtc: OBDService.decodeDTC(a, b), failureType: ftb, status: status,
                 raw: UInt32(a) << 16 | UInt32(b) << 8 | UInt32(ftb), powertrain: true)
    }

    /// UDS 19 02: some modules reject mask FF (NRC 31 → narrower mask), some need extended session first.
    private func hyUDSFaults() async -> (faults: [VAGFault]?, inExtended: Bool) {
        var inExt = false
        for mask in ["FF", "2F", "09", "08", "0D", "0F"] {
            var attempt = 0
            while attempt < 2 {
                attempt += 1
                guard let d = try? await elm.requestUDS("1902" + mask, timeout: 2) else { return (nil, inExt) }
                if let r = positive(d, sid: 0x59, sub: 0x02) {
                    let rec = Array(r.dropFirst(3))
                    var out = [VAGFault]()
                    var j = 0
                    while j + 3 < rec.count {
                        if (rec[j] | rec[j + 1]) != 0, rec[j + 3] & VAGFault.faultMask != 0 {
                            out.append(hyFault(rec[j], rec[j + 1], rec[j + 2], rec[j + 3]))
                        }
                        j += 4
                    }
                    return (out, inExt)
                }
                guard let n = negative(d, sid: 0x19) else { return (nil, inExt) }
                if [0x7F, 0x7E, 0x22].contains(n.nrc), !inExt {
                    if (try? await session(0x03)) != nil { inExt = true; continue }
                    return (nil, inExt)
                }
                if n.nrc == 0x31 { break }            // next mask
                return (nil, inExt)                    // service not supported etc.
            }
        }
        return (nil, inExt)
    }

    private func hyKWPFaults() async -> [VAGFault]? {
        // 18 = KWP readDTCByStatus (Hyundai/Kia); 17 FF00 = readStatusOfDTC on older Renault ECUs
        for (cmd, pos) in [("1800FF00", UInt8(0x58)), ("1802FF00", 0x58), ("17FF00", 0x57)] {
            guard let d = try? await elm.requestUDS(cmd, timeout: 2), let r = positive(d, sid: pos), r.count >= 2 else { continue }
            let rec = Array(r.dropFirst(2))
            var out = [VAGFault]()
            var j = 0
            while j + 2 < rec.count {
                if (rec[j] | rec[j + 1]) != 0 {
                    out.append(hyFault(rec[j], rec[j + 1], 0, rec[j + 2] & 0x20 != 0 ? 0x09 : 0x08))
                }
                j += 3
            }
            return out
        }
        return nil
    }

    func hyundaiReport(_ m: VAGModule) async -> VAGReport {
        await vagOpen(m)
        let uds = await hyUDSFaults()
        var faults = uds.faults
        let inExt = uds.inExtended
        if faults == nil { faults = await hyKWPFaults() }
        if faults == nil, m.category == .powertrain {
            let stored = await dtcs(mode: "03", kind: .stored)
            let pending = await dtcs(mode: "07", kind: .pending)
            faults = stored.map { d in VAGFault(dtc: d.code, failureType: 0, status: 0x08) }
                + pending.map { d in VAGFault(dtc: d.code, failureType: 0, status: 0x04) }
        }
        if inExt { _ = try? await session(0x01) }
        let part = await hyText(uds: 0xF187, kwp: 0x87)
        let serial = await hyText(uds: 0xF18C, kwp: 0x8C)
        await vagClose()
        guard let fs = faults else { return VAGReport(module: m, present: false, faults: []) }
        var seen = Set<String>()
        let uniq = fs.filter { seen.insert($0.code).inserted }
        return VAGReport(module: m, present: true, faults: uniq, partNumber: part, systemName: serial)
    }

    /// Fault list of a discovered (Hyundai/Kia/Renault) module whose channel is already open.
    func discoveredFaultsOpen(_ m: VAGModule) async -> [VAGFault]? {
        let uds = await hyUDSFaults()
        if uds.inExtended { _ = try? await session(0x01) }
        if let f = uds.faults { return f }
        return await hyKWPFaults()
    }

    private func hyText(uds: UInt16, kwp: UInt8) async -> String? {
        if let p = try? await readDID(uds) {
            var q = p
            while let l = q.last, [0x00, 0xAA, 0xFF, 0x20].contains(l) { q.removeLast() }
            let s = String(decoding: q.filter { (0x20...0x7E).contains($0) }, as: UTF8.self)
            if !s.isEmpty { return s }
        }
        if let d = try? await elm.requestUDS(String(format: "1A%02X", kwp), timeout: 1),
           let r = positive(d, sid: 0x5A, sub: kwp) {
            let s = String(decoding: r.dropFirst(2).filter { (0x20...0x7E).contains($0) }, as: UTF8.self)
                .trimmingCharacters(in: .whitespaces)
            if !s.isEmpty { return s }
        }
        return nil
    }

    func hyundaiClear(_ m: VAGModule) async throws {
        await vagOpen(m)
        var ok = false
        var reason = ""
        outer: for ext in [false, true] {
            if ext { guard (try? await session(0x03)) != nil else { break } }
            for cmd in ["14FFFFFF", "14FF00"] {
                if let d = try? await elm.requestUDS(cmd, timeout: 3, pendingWait: 8), positive(d, sid: 0x54) != nil {
                    ok = true
                    if ext { _ = try? await session(0x01) }
                    break outer
                }
            }
        }
        if !ok, m.category == .powertrain, let d = try? await elm.requestUDS("04", timeout: 5, pendingWait: 8) {
            if d.contains(0x44) { ok = true }
            else if let n = negative(d, sid: 0x04), n.nrc == 0x22 { reason = " — switch the engine OFF, ignition ON" }
        }
        await vagClose()
        if !ok { throw ELMError.error("\(m.name) refused to clear codes\(reason)") }
    }

    func hyundaiIdentification(_ m: VAGModule) async -> [(String, String)] {
        await vagOpen(m)
        var out = [(String, String)]()
        for (did, name) in StandardDID.all where did != 0x0600 {
            if let p = try? await readDID(did) {
                var q = p
                while let l = q.last, [0x00, 0xAA, 0xFF, 0x20].contains(l) { q.removeLast() }
                let ascii = !q.isEmpty && q.allSatisfy { (0x20...0x7E).contains($0) }
                out.append((name, ascii ? String(decoding: q, as: UTF8.self) : p.map { String(format: "%02X", $0) }.joined()))
            }
        }
        if out.isEmpty {
            for (lid, name) in [(UInt8(0x87), "Part number"), (0x88, "Software"), (0x8A, "Supplier"),
                                (0x8C, "Serial"), (0x90, "VIN")] {
                if let d = try? await elm.requestUDS(String(format: "1A%02X", lid), timeout: 1),
                   let r = positive(d, sid: 0x5A, sub: lid) {
                    out.append((name, String(decoding: r.dropFirst(2).filter { (0x20...0x7E).contains($0) }, as: UTF8.self)))
                }
            }
        }
        await vagClose()
        return out
    }
}
