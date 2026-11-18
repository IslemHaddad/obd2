import Foundation
import Observation
import SwiftUI

@MainActor
@Observable
final class VehicleSession {
    enum State: Equatable { case idle, connecting(String), connected, failed(String) }

    var state: State = .idle
    var adapterVersion = ""
    var protocolName = ""
    var supported = Set<UInt8>()
    var values = [UInt8: Double]()
    var history = [UInt8: [Double]]()          // ring buffer per PID for sparklines
    var tiles: [Tile] = Tile.load() {
        didSet {
            Tile.save(tiles)
            if isLogging, oldValue.map(\.pid) != tiles.map(\.pid) { stopLogging(); startLogging() }
        }
    }
    /// Unique PIDs to poll, in tile order.
    var selected: [UInt8] {
        var seen = Set<UInt8>()
        return tiles.map(\.pid).filter { seen.insert($0).inserted }
    }
    var refreshHz: Double = 0
    var batteryVoltage: Double?

    struct ModuleReport: Identifiable {
        let ecu: ECU
        var dtcs: [DTC]
        var id: String { ecu.id }
        var faulty: Bool { !dtcs.isEmpty }
    }
    var modules = [ModuleReport]()
    var dtcs: [DTC] { modules.flatMap(\.dtcs) }
    var faultyModules: [ModuleReport] { modules.filter(\.faulty) }
    private var knownECUs: [ECU] = []

    // VW Group
    var vehicle: SelectedVehicle? = SelectedVehicle.load() { didSet { SelectedVehicle.save(vehicle) } }
    var vagReports = [VAGReport]()
    var vagScanProgress: Double?            // 0…1 while scanning
    var vagSupported = false
    var vagFaulty: [VAGReport] { vagReports.filter(\.faulty) }

    // VAG live data & coding
    var measurements: [Measurement] = Measurement.load() { didSet { Measurement.save(measurements) } }
    var vagLive: [UUID: String] = [:]
    var vagLiveNumeric: [UUID: [Double]] = [:]
    var vagLiveModule: VAGModule?
    var backups: [CodingBackup] = CodingBackup.load() { didSet { CodingBackup.save(backups) } }
    var recipes: [CodingRecipe] = CodingRecipe.load() { didSet { CodingRecipe.save(recipes) } }
    var adaptations: [Adaptation] = Adaptation.load() { didSet { Adaptation.save(adaptations) } }
    var outputTests: [OutputTest] = OutputTest.load() { didSet { OutputTest.save(outputTests) } }

    enum OutputRun: Equatable { case starting, running(remaining: Double, response: String), stopping }
    var activeTest: UUID?
    var testState: OutputRun?
    var testError: String?
    private var testStopRequested = false

    // Basic settings
    var basicSettings: [BasicSetting] = BasicSetting.load() { didSet { BasicSetting.save(basicSettings) } }
    struct BasicRun: Equatable {
        enum Phase: Equatable { case starting, running, stopping, done, failed, stopped, timedOut, error(String) }
        var setting: UUID
        var phase: Phase = .starting
        var elapsed: Double = 0
        var result = ""
        var watch: [UUID: String] = [:]
        var finished: Bool {
            switch phase {
            case .starting, .running, .stopping: false
            case .done, .failed, .stopped, .timedOut, .error: true
            }
        }
    }
    var basicRun: BasicRun?
    private var basicStopRequested = false
    var readiness: ReadinessStatus?
    var freeze = [UInt8: Double]()
    var vin: String?
    var calID: String?
    var ecuName: String?

    var isLogging = false
    private(set) var logURL: URL?
    private var logHandle: FileHandle?

    let scanner = BLEScanner()
    private var transport: OBDTransport?
    private var elm: ELM327?
    private var service: OBDService? { elm.map(OBDService.init) }
    private var pollTask: Task<Void, Never>?
    private let historyLimit = 120

    var supportedPIDs: [PID] { PIDs.all.filter { supported.isEmpty || supported.contains($0.id) } }

    // MARK: Connection
    func connectBLE(_ device: BLEDevice) {
        guard let t = scanner.transport(for: device) else { return }
        connect(t, label: device.name)
    }

    func connectWiFi(host: String, port: UInt16) {
        connect(WiFiTransport(host: host, port: port), label: "\(host):\(port)")
    }

    private func connect(_ t: OBDTransport, label: String) {
        disconnect()
        state = .connecting(label)
        transport = t
        t.onDisconnect = { [weak self] err in
            Task { @MainActor in
                guard let self, self.transport === t else { return }
                self.teardown()
                self.state = .failed(err?.localizedDescription ?? "Disconnected")
            }
        }
        Task {
            do {
                try await t.connect()
                let elm = ELM327(transport: t)
                try await elm.initialize()
                self.elm = elm
                adapterVersion = await elm.version
                protocolName = Self.protocolNames[await elm.protocolNumber] ?? "Unknown"
                supported = await OBDService(elm: elm).supportedPIDs()
                state = .connected
                startPolling()
                Task { await loadInfo() }
            } catch {
                teardown()
                state = .failed(error.localizedDescription)
            }
        }
    }

    func disconnect() {
        teardown()
        state = .idle
    }

    private func teardown() {
        pollTask?.cancel(); pollTask = nil
        stopLogging()
        transport?.onDisconnect = nil
        transport?.disconnect()
        transport = nil
        elm = nil
        knownECUs = []
        modules = []
        vagReports = []
        vagScanProgress = nil
    }

    // MARK: Live polling — runs flat-out, one batched request per cycle.
    func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            var frames = 0
            var windowStart = Date()
            var cycle = 0
            while !Task.isCancelled {
                guard let self, let svc = self.service else { return }
                let pids = self.selected.compactMap { PIDs.byID[$0] }
                if pids.isEmpty { try? await Task.sleep(nanoseconds: 200_000_000); continue }
                let r = await svc.read(pids)
                self.apply(r)
                cycle += 1
                if cycle % 25 == 0 { self.batteryVoltage = await svc.batteryVoltage() }
                frames += 1
                let dt = Date().timeIntervalSince(windowStart)
                if dt >= 1 { self.refreshHz = Double(frames) / dt; frames = 0; windowStart = Date() }
            }
        }
    }

    private func apply(_ r: [UInt8: Double]) {
        for (k, v) in r {
            values[k] = v
            var h = history[k, default: []]
            h.append(v)
            if h.count > historyLimit { h.removeFirst(h.count - historyLimit) }
            history[k] = h
        }
        if isLogging, !r.isEmpty { writeLogRow() }
    }

    func move(_ id: Tile.ID, before target: Tile.ID) {
        guard id != target, let from = tiles.firstIndex(where: { $0.id == id }),
              let to = tiles.firstIndex(where: { $0.id == target }) else { return }
        tiles.move(fromOffsets: [from], toOffset: to > from ? to + 1 : to)
    }

    // MARK: Diagnostics — pause polling so the bus is ours.
    private func exclusive<T>(_ work: (OBDService) async throws -> T) async rethrows -> T? {
        guard let svc = service else { return nil }
        let running = pollTask
        pollTask = nil
        running?.cancel()
        await running?.value
        defer {
            if state == .connected {
                if let m = vagLiveModule { startVAGLive(m) } else { startPolling() }
            }
        }
        return try await work(svc)
    }

    func loadInfo() async {
        await exclusive { svc in
            vagSupported = await svc.supportsVAG
            vin = await svc.vin()
            if let v = vin, let b = VAGBrand.from(vin: v), vehicle?.brand != b {
                vehicle = SelectedVehicle(brand: b, model: b.models[0], year: nil)
            }
            calID = await svc.calibrationID()
            ecuName = await svc.ecuName()
        }
    }

    /// Scans every module; each one keeps its own code list.
    func scanDTCs() async {
        await exclusive { svc in
            if knownECUs.isEmpty { knownECUs = await svc.discoverECUs() }
            var out = [ModuleReport]()
            for ecu in knownECUs { out.append(ModuleReport(ecu: ecu, dtcs: await svc.dtcs(for: ecu))) }
            modules = out
            readiness = await svc.readiness()
            freeze = await svc.freezeFrame(supportedPIDs)
        }
    }

    /// Clears one module only, then re-reads just that module.
    func clear(_ ecu: ECU) async throws {
        try await exclusive { svc in
            try await svc.clearDTCs(for: ecu)
            let fresh = await svc.dtcs(for: ecu)
            if let i = modules.firstIndex(where: { $0.ecu == ecu }) { modules[i].dtcs = fresh }
            readiness = await svc.readiness()
        }
    }

    // MARK: VW Group full scan (UDS per module)
    func scanVAG() async {
        await exclusive { svc in
            vagSupported = await svc.supportsVAG
            guard vagSupported else { return }
            var out = [VAGReport]()
            let all = VAGModule.all
            for (i, m) in all.enumerated() {
                vagScanProgress = Double(i) / Double(all.count)
                out.append(await svc.vagReport(m) ?? VAGReport(module: m, present: false, faults: []))
                vagReports = out
            }
            vagScanProgress = nil
        }
    }

    /// Clears one VAG module only, then re-reads that module.
    func clearVAG(_ m: VAGModule) async throws {
        try await exclusive { svc in
            try await svc.vagClear(m)
            if let r = await svc.vagReport(m), let i = vagReports.firstIndex(where: { $0.module == m }) { vagReports[i] = r }
        }
    }

    // MARK: VAG live data — module channel stays open, DIDs polled back-to-back.
    func startVAGLive(_ m: VAGModule) {
        Task {
            let running = pollTask
            pollTask = nil
            running?.cancel()
            await running?.value
            guard let svc = service else { return }
            vagLiveModule = m
            vagLive = [:]; vagLiveNumeric = [:]
            pollTask = Task { [weak self] in
                await svc.vagOpen(m)
                while !Task.isCancelled {
                    guard let self else { break }
                    let defs = self.measurements.filter { $0.module == m.address }
                    if defs.isEmpty { try? await Task.sleep(nanoseconds: 200_000_000); continue }
                    var cache = [UInt16: [UInt8]]()        // one request per DID even if several fields use it
                    for d in defs where !Task.isCancelled {
                        if cache[d.did] == nil { cache[d.did] = (try? await svc.readDID(d.did)) ?? [] }
                        let p = cache[d.did]!
                        self.vagLive[d.id] = p.isEmpty ? "—" : d.decode(p)
                        if let v = d.numeric(p) {
                            var h = self.vagLiveNumeric[d.id, default: []]
                            h.append(v); if h.count > 120 { h.removeFirst() }
                            self.vagLiveNumeric[d.id] = h
                        }
                    }
                }
                await svc.vagClose()
            }
        }
    }

    func stopVAGLive() {
        guard vagLiveModule != nil else { return }
        vagLiveModule = nil
        Task {
            let running = pollTask
            pollTask = nil
            running?.cancel()
            await running?.value
            if state == .connected { startPolling() }
        }
    }

    func scanDIDs(_ m: VAGModule, _ range: ClosedRange<UInt16>, progress: @escaping (Double, Int) async -> Bool) async -> [(UInt16, [UInt8])] {
        (await exclusive { svc in await svc.scanDIDs(m, range, progress: progress) }) ?? []
    }

    func readIdentification(_ m: VAGModule) async -> [(String, String)] {
        (await exclusive { svc in
            await svc.vagOpen(m)
            var out = [(String, String)]()
            for (did, name) in StandardDID.all {
                if let p = try? await svc.readDID(did) {
                    let ascii = p.allSatisfy { (0x20...0x7E).contains($0) || $0 == 0 }
                    out.append((name, ascii ? String(decoding: p.filter { $0 != 0 }, as: UTF8.self).trimmingCharacters(in: .whitespaces)
                                            : p.map { String(format: "%02X", $0) }.joined()))
                }
            }
            await svc.vagClose()
            return out
        }) ?? []
    }

    // MARK: VAG coding
    func readCoding(_ m: VAGModule) async throws -> [UInt8] {
        guard let c = try await exclusive({ svc in try await svc.readCoding(m) }) else { throw TransportError.notConnected }
        return c
    }

    /// Backs up current coding, writes new coding, verifies. Returns verified coding.
    func writeCoding(_ m: VAGModule, from old: [UInt8], to new: [UInt8], note: String) async throws -> [UInt8] {
        backups.insert(CodingBackup(module: m.address, vin: vin ?? "", date: Date(), coding: old, note: note), at: 0)
        guard let back = try await exclusive({ svc in try await svc.writeCoding(m, new) }) else { throw TransportError.notConnected }
        if back != new { throw ELMError.error("Verify failed: module reports \(back.map { String(format: "%02X", $0) }.joined())") }
        return back
    }

    // MARK: VAG adaptations
    func readAdaptation(_ a: Adaptation, _ m: VAGModule) async throws -> [UInt8] {
        guard let p = try await exclusive({ svc in try await svc.readAdaptation(m, a.did) }) else { throw TransportError.notConnected }
        return p
    }

    func writeAdaptation(_ a: Adaptation, _ m: VAGModule, old: [UInt8], new: [UInt8]) async throws -> [UInt8] {
        backups.insert(CodingBackup(module: a.backupKey, vin: vin ?? "", date: Date(), coding: old, note: a.name), at: 0)
        guard let back = try await exclusive({ svc in try await svc.writeAdaptation(m, a.did, new) }) else { throw TransportError.notConnected }
        if back != new { throw ELMError.error("Verify failed: module reports \(back.map { String(format: "%02X", $0) }.joined())") }
        return back
    }

    // MARK: VAG output tests — owns the bus while running, keeps session alive with 3E 00.
    func startOutputTest(_ t: OutputTest, _ m: VAGModule) {
        guard activeTest == nil, basicRun == nil || basicRun!.finished else { return }
        activeTest = t.id
        testState = .starting
        testError = nil
        Task {
            let running = pollTask
            pollTask = nil
            running?.cancel()
            await running?.value
            guard let svc = service else { activeTest = nil; testState = nil; return }
            pollTask = Task { [weak self] in
                await svc.vagOpen(m)
                do {
                    try await svc.session(0x03)
                    let resp = try await svc.uds(t.startCommand, positive: t.positiveSID, request: t.requestSID)
                    let hex = resp.map { String(format: "%02X", $0) }.joined(separator: " ")
                    let end = Date().addingTimeInterval(t.duration)
                    var lastTP = Date()
                    while !Task.isCancelled, Date() < end {
                        self?.testState = .running(remaining: end.timeIntervalSinceNow, response: hex)
                        if Date().timeIntervalSince(lastTP) >= 2 { await svc.testerPresent(); lastTP = Date() }
                        try? await Task.sleep(nanoseconds: 250_000_000)
                    }
                } catch {
                    self?.testError = error.localizedDescription
                }
                self?.testState = .stopping
                _ = try? await svc.uds(t.stopCommand, positive: t.positiveSID, request: t.requestSID)
                try? await svc.session(0x01)
                await svc.vagClose()
                guard let self else { return }
                self.activeTest = nil
                self.testState = nil
                // Resume polling unless another operation cancelled us to take the bus.
                let resume = !Task.isCancelled || self.testStopRequested
                self.testStopRequested = false
                if resume { self.pollTask = nil; if self.state == .connected { self.startPolling() } }
            }
        }
    }

    func stopOutputTest() {
        guard activeTest != nil else { return }
        testStopRequested = true
        pollTask?.cancel()
    }

    // MARK: VAG basic settings
    func startBasicSetting(_ b: BasicSetting, _ m: VAGModule) {
        guard basicRun == nil || basicRun!.finished, activeTest == nil else { return }
        basicRun = BasicRun(setting: b.id)
        basicStopRequested = false
        let watchDefs = measurements.filter { b.watch.contains($0.id) }
        Task {
            let running = pollTask
            pollTask = nil
            running?.cancel()
            await running?.value
            guard let svc = service else { basicRun?.phase = .error("Not connected"); return }
            pollTask = Task { [weak self] in
                await svc.vagOpen(m)
                var startedRoutine = false
                var final: BasicRun.Phase = .stopped
                do {
                    try await svc.session(0x03)
                    let first = try await svc.uds(b.startCommand, positive: 0x71, request: 0x31, timeout: 5)
                    startedRoutine = true
                    self?.basicRun?.phase = .running
                    self?.basicRun?.result = Self.hex(first.dropFirst(4))
                    let t0 = Date()
                    while !Task.isCancelled {
                        let el = Date().timeIntervalSince(t0)
                        self?.basicRun?.elapsed = el
                        if el >= b.timeout { final = .timedOut; break }
                        if let r = try? await svc.uds(b.resultCommand, positive: 0x71, request: 0x31, timeout: 1.5) {
                            let payload = Array(r.dropFirst(4))       // 71 03 RIDhi RIDlo <status record>
                            self?.basicRun?.result = Self.hex(payload)
                            switch b.verdict(payload) {
                            case .done: final = .done
                            case .failed: final = .failed
                            case .running: break
                            }
                            if final == .done || final == .failed { break }
                        } else {
                            await svc.testerPresent()
                        }
                        for d in watchDefs {
                            let p = (try? await svc.readDID(d.did, timeout: 0.8)) ?? []
                            self?.basicRun?.watch[d.id] = p.isEmpty ? "—" : d.decode(p)
                        }
                        try? await Task.sleep(nanoseconds: 400_000_000)
                    }
                } catch {
                    final = .error(error.localizedDescription)
                }
                if startedRoutine, final != .done, final != .failed {
                    self?.basicRun?.phase = .stopping
                    _ = try? await svc.uds(b.stopCommand, positive: 0x71, request: 0x31)
                }
                try? await svc.session(0x01)
                await svc.vagClose()
                guard let self else { return }
                self.basicRun?.phase = final
                let resume = !Task.isCancelled || self.basicStopRequested
                self.basicStopRequested = false
                if resume { self.pollTask = nil; if self.state == .connected { self.startPolling() } }
            }
        }
    }

    func stopBasicSetting() {
        guard let r = basicRun, !r.finished else { return }
        basicStopRequested = true
        pollTask?.cancel()
    }

    nonisolated private static func hex<S: Sequence>(_ b: S) -> String where S.Element == UInt8 {
        b.map { String(format: "%02X", $0) }.joined(separator: " ")
    }

    /// Clears only VAG modules that have faults.
    func clearVAGFaulty() async throws {
        for r in vagFaulty { try await clearVAG(r.module) }
    }

    /// Clears only modules that currently have codes; healthy modules are not touched.
    func clearFaulty() async throws {
        for m in faultyModules { try await clear(m.ecu) }
    }

    func refreshReadiness() async {
        await exclusive { svc in readiness = await svc.readiness() }
    }

    // MARK: CSV logging
    func startLogging() {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let f = DateFormatter(); f.dateFormat = "yyyyMMdd_HHmmss"
        let url = dir.appendingPathComponent("obd_\(f.string(from: Date())).csv")
        let header = "timestamp," + selected.compactMap { PIDs.byID[$0] }.map { "\($0.name) (\($0.unit))" }.joined(separator: ",") + "\n"
        FileManager.default.createFile(atPath: url.path, contents: Data(header.utf8))
        logHandle = try? FileHandle(forWritingTo: url)
        logHandle?.seekToEndOfFile()
        logURL = url
        isLogging = logHandle != nil
    }

    func stopLogging() {
        try? logHandle?.close()
        logHandle = nil
        isLogging = false
    }

    private func writeLogRow() {
        let ts = String(format: "%.3f", Date().timeIntervalSince1970)
        let row = ts + "," + selected.map { values[$0].map { String(format: "%.3f", $0) } ?? "" }.joined(separator: ",") + "\n"
        logHandle?.write(Data(row.utf8))
    }

    var logFiles: [URL] {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return ((try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.creationDateKey])) ?? [])
            .filter { $0.pathExtension == "csv" }
            .sorted { $0.lastPathComponent > $1.lastPathComponent }
    }

    static let protocolNames: [Int: String] = [
        1: "SAE J1850 PWM", 2: "SAE J1850 VPW", 3: "ISO 9141-2", 4: "ISO 14230-4 KWP (5 baud)",
        5: "ISO 14230-4 KWP (fast)", 6: "ISO 15765-4 CAN 11/500", 7: "ISO 15765-4 CAN 29/500",
        8: "ISO 15765-4 CAN 11/250", 9: "ISO 15765-4 CAN 29/250", 10: "SAE J1939 CAN",
    ]
}
