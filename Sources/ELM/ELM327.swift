import Foundation

/// What kind of adapter this is and which workarounds it needs.
struct AdapterProfile: Codable, Equatable {
    let ati: String
    let sti: String
    var isSTN: Bool { !sti.isEmpty }
    /// Elm Electronics never sold v1.5 / v2.x firmware → those strings mean a clone.
    var isClone: Bool {
        let a = ati.uppercased()
        return !isSTN && (["V1.5", "V2.1", "V2.2", "V2.3"].contains { a.contains($0) } || !a.hasPrefix("ELM327"))
    }
    var chip: String { isSTN ? "\(sti) (genuine STN)" : "\(ati) (\(isClone ? "clone" : "ELM327"))" }
    var summary: String {
        if isSTN { return "Genuine STN chip: fast mode, long replies OK" }
        if isClone { return "Clone chip: reply re-sync, short fault lists, busy-retry and voltage correction enabled" }
        return "ELM327: standard mode"
    }
}

enum ELMError: LocalizedError {
    case timeout(String), noData, unableToConnect, error(String)
    var errorDescription: String? {
        switch self {
        case .timeout(let c): "Timeout on \(c)"
        case .noData: "NO DATA"
        case .unableToConnect: "Adapter unable to connect to vehicle (ignition on?)"
        case .error(let s): s
        }
    }
}

/// Serialized ELM327 command channel. One command in flight; response ends at '>' prompt.
actor ELM327 {
    private let transport: OBDTransport
    private var buffer = [UInt8]()
    private var waiter: CheckedContinuation<String, Error>?
    private var timeoutTask: Task<Void, Never>?
    private(set) var protocolNumber = 0
    private(set) var isCAN = true
    private(set) var version = ""
    private(set) var profile = AdapterProfile(ati: "", sti: "")

    init(transport: OBDTransport) {
        self.transport = transport
        transport.onReceive = { [weak self] data in
            guard let self else { return }
            Task { await self.ingest(data) }
        }
    }

    private func ingest(_ data: Data) {
        for b in data where b != 0 {
            if b == UInt8(ascii: ">") {
                let s = String(decoding: buffer, as: UTF8.self)
                buffer.removeAll(keepingCapacity: true)
                timeoutTask?.cancel()
                waiter?.resume(returning: s); waiter = nil
            } else {
                buffer.append(b)
            }
        }
    }

    /// Sends a raw command and returns cleaned response lines.
    func send(_ cmd: String, timeout: Double = 2.0) async throws -> [String] {
        while waiter != nil { try await Task.sleep(nanoseconds: 2_000_000) }   // serialize across actor reentrancy
        buffer.removeAll(keepingCapacity: true)
        let raw: String = try await withCheckedThrowingContinuation { cont in
            waiter = cont
            timeoutTask = Task { [weak self] in
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                guard !Task.isCancelled else { return }
                await self?.expire(cmd)
            }
            transport.send(Data((cmd + "\r").utf8))
        }
        let lines = raw.split(whereSeparator: { $0 == "\r" || $0 == "\n" })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && $0 != cmd && !$0.hasPrefix("SEARCHING") && $0 != "BUS INIT: ...OK" }
        if let bad = lines.first(where: { Self.errorTokens.contains(where: $0.contains) }) {
            if bad.contains("NO DATA") { throw ELMError.noData }
            if bad.contains("UNABLE TO CONNECT") { throw ELMError.unableToConnect }
            throw ELMError.error(bad)
        }
        return lines
    }

    private static let errorTokens = ["NO DATA", "UNABLE TO CONNECT", "CAN ERROR", "BUS ERROR",
                                      "BUS BUSY", "FB ERROR", "DATA ERROR", "STOPPED", "?", "ERR"]

    private func expire(_ cmd: String) {
        guard let w = waiter else { return }
        waiter = nil
        buffer.removeAll()
        w.resume(throwing: ELMError.timeout(cmd))
    }

    /// Fast init: no echo/spaces/headers/linefeeds, adaptive timing, auto protocol.
    func initialize() async throws {
        _ = try? await send("ATZ", timeout: 5)          // reset; slow on BLE clones
        try? await Task.sleep(nanoseconds: 600_000_000)  // let late reset output arrive, then discard it
        buffer.removeAll()
        // Re-align command/response: send ATE0 until a clean OK comes back.
        var synced = false
        for _ in 0..<4 where !synced {
            if let l = try? await send("ATE0", timeout: 2), l.contains(where: { $0.contains("OK") }) { synced = true }
            else { try? await Task.sleep(nanoseconds: 400_000_000); buffer.removeAll() }
        }
        guard synced else { throw ELMError.error("Adapter is not answering (powered? used by another app?)") }
        for c in ["ATL0", "ATS0", "ATH0", "ATAT2", "ATSP0"] {
            _ = try await send(c, timeout: 2)
        }
        version = (try? await send("ATI").first) ?? ""
        let sti = (try? await send("STI", timeout: 1).first) ?? ""     // only STN chips understand ST commands
        profile = AdapterProfile(ati: version, sti: sti)
        _ = try await send("0100", timeout: 10)          // triggers protocol search
        if let dp = try? await send("ATDPN").first {
            let digits = String(dp.uppercased().drop(while: { $0 == "A" }))
            protocolNumber = Int(digits, radix: 16) ?? 0
        }
        isCAN = (6...9).contains(protocolNumber) || protocolNumber >= 0xA
    }

    /// Sends an OBD request and returns its payload bytes (all frames merged, all ECUs concatenated).
    func request(_ hex: String, timeout: Double = 2.0) async throws -> [UInt8] {
        let lines = try await send(hex, timeout: timeout)
        return Self.merge(lines: lines, isCAN: isCAN)
    }

    /// UDS request that survives "7F xx 78" (response pending): cheap clones stop listening after printing it,
    /// so retry with the adapter's maximum receive timeout (ATST FF).
    func requestUDS(_ hex: String, timeout: Double = 2.0, pendingWait: Double = 5.0) async throws -> [UInt8] {
        var d = try await request(hex, timeout: timeout)
        guard Self.onlyPending(d) else { return d }
        _ = try? await send("ATSTFF", timeout: 1)
        let end = Date().addingTimeInterval(pendingWait)
        while Self.onlyPending(d), Date() < end {
            d = (try? await request(hex, timeout: timeout + 2)) ?? []
        }
        _ = try? await send("ATST32", timeout: 1)
        _ = try? await send("ATAT2", timeout: 1)
        return d
    }

    static func onlyPending(_ d: [UInt8]) -> Bool {
        guard d.count >= 3, d.count % 3 == 0 else { return false }
        return stride(from: 0, to: d.count, by: 3).allSatisfy { d[$0] == 0x7F && d[$0 + 2] == 0x78 }
    }

    /// Per-line byte arrays (one per ECU frame), useful for non-CAN DTC parsing.
    func requestLines(_ hex: String, timeout: Double = 3.0) async throws -> [[UInt8]] {
        let lines = try await send(hex, timeout: timeout)
        return lines.map { Self.hexBytes(Self.stripFrameIndex($0)) }
    }

    static func merge(lines: [String], isCAN: Bool) -> [UInt8] {
        var out = [UInt8]()
        for l in lines {
            // CAN multi-frame: first line is byte count ("014"), following "0:..." "1:..."
            if isCAN, l.count == 3, !l.contains(":"), Int(l, radix: 16) != nil { continue }
            out += hexBytes(stripFrameIndex(l))
        }
        return out
    }

    static func stripFrameIndex(_ l: String) -> Substring {
        if let i = l.firstIndex(of: ":") { return l[l.index(after: i)...] }
        return Substring(l)
    }

    static func hexBytes<S: StringProtocol>(_ s: S) -> [UInt8] {
        var out = [UInt8](); out.reserveCapacity(s.utf8.count / 2)
        var hi: UInt8? = nil
        for c in s.utf8 {
            let v: UInt8
            switch c {
            case 48...57: v = c - 48
            case 65...70: v = c - 55
            case 97...102: v = c - 87
            default: continue
            }
            if let h = hi { out.append(h << 4 | v); hi = nil } else { hi = v }
        }
        return out
    }
}
