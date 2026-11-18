import Foundation
import Observation
import SwiftUI

@MainActor
@Observable
final class VehicleSession {
    enum State: Equatable { case idle, connecting(String), connected, reconnecting(Int), failed(String) }

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
    var vehicle: SelectedVehicle? = SelectedVehicle.load() {
        didSet {
            SelectedVehicle.save(vehicle)
            if oldValue?.brand.family != vehicle?.brand.family { refreshModuleList() }
        }
    }
    var vagReports = [VAGReport]()
    var vagScanProgress: Double?            // 0…1 while scanning
    var vagSupported = false
    var vagFaulty: [VAGReport] { vagReports.filter(\.faulty) }
    /// Modules for the current brand: VW Group fixed table, Hyundai/Kia discovered on the car.
    var vagModules: [VAGModule] = VAGModule.all
    var discoverProgress: (Double, Int)?
    var family: VAGBrand.Family { vehicle?.brand.family ?? .vag }

    // Extras (dashboard, alerts, history, report)
    var oilTemp: Double?
    var wantOil = false
    struct SpeedSample { let t: Double; let v: Double }
    var speedTrace: [SpeedSample] = []      // for live power (acceleration method)
    var alert: String?
    var faultHistory: [FaultEvent] = FaultEvent.load() { didSet { FaultEvent.save(faultHistory) } }
    var report: VehicleReport?
    var reportProgress: (Double, String)?
    var userDisconnected = false
    var currentLink: LastAdapter?
    var adapterProfile: AdapterProfile?
    var savedAdapters: [SavedAdapter] = SavedAdapter.load()
    var knownFaultCodes: Set<String>?

    // VAG live data & coding
    var measurements: [Measurement] = VehicleSession.seededMeasurements() { didSet { Measurement.save(measurements) } }

    /// Oil temperature found on the SEAT KJ 1.6 MPI engine (DID 11BD, 0.1 K) — seeded once.
    private static func seededMeasurements() -> [Measurement] {
        var m = Measurement.load()
        if !m.contains(where: { $0.module == "01" && $0.did == 0x11BD }) {
            m.append(Measurement(module: "01", did: 0x11BD, name: "Oil Temp", kind: .number, offset: 0, length: 2,
                                 signed: false, scale: 0.1, add: -273.15, unit: "°C"))
            Measurement.save(m)
        }
        return m
    }
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
    var service: OBDService? { elm.map(OBDService.init) }
    private var pollTask: Task<Void, Never>?
    private let historyLimit = 120

    var supportedPIDs: [PID] { PIDs.all.filter { supported.isEmpty || supported.contains($0.id) } }

    // MARK: Connection
    func connectBLE(_ device: BLEDevice) {
        guard let t = scanner.transport(for: device) else { return }
        LastAdapter.save(.ble(device.id, device.name))
        currentLink = .ble(device.id, device.name)
        connect(t, label: device.name)
    }

    func connectWiFi(host: String, port: UInt16) {
        LastAdapter.save(.wifi(host, port))
        currentLink = .wifi(host, port)
        connect(WiFiTransport(host: host, port: port), label: "\(host):\(port)")
    }

    /// Reconnects to the adapter used last time (BLE by peripheral id, or Wi-Fi host).
    func connectSaved(_ a: SavedAdapter) {
        LastAdapter.save(a.link)
        connectLast()
    }

    func connectLast() {
        currentLink = LastAdapter.load()
        switch LastAdapter.load() {
        case .ble(let id, let name)?:
            guard let t = scanner.transport(forID: id) else { state = .failed("\(name) not found — scan once"); return }
            connect(t, label: name)
        case .wifi(let h, let p)?:
            connect(WiFiTransport(host: h, port: p), label: "\(h):\(p)")
        case nil: break
        }
    }

    private func connect(_ t: OBDTransport, label: String, attempt: Int = 0) {
        teardown()
        userDisconnected = false
        state = attempt > 0 ? .reconnecting(attempt) : .connecting(label)
        transport = t
        t.onDisconnect = { [weak self] err in
            Task { @MainActor in
                guard let self, self.transport === t else { return }
                self.teardown()
                if !self.userDisconnected && UserDefaults.standard.object(forKey: "autoReconnect") as? Bool ?? true {
                    self.autoReconnect(after: err)
                } else {
                    self.state = .failed(err?.localizedDescription ?? "Disconnected")
                }
            }
        }
        Task {
            do {
                try await t.connect()
                let elm = ELM327(transport: t)
                try await elm.initialize()
                self.elm = elm
                adapterVersion = await elm.version
                let prof = await elm.profile
                adapterProfile = prof
                if let link = currentLink ?? LastAdapter.load() {
                    SavedAdapter.remember(link, profile: prof)
                    savedAdapters = SavedAdapter.load()
                }
                protocolName = Self.protocolNames[await elm.protocolNumber] ?? "Unknown"
                supported = await OBDService(elm: elm).supportedPIDs()
                state = .connected
                startPolling()
                Task { await loadInfo() }
            } catch {
                teardown()
                if attempt > 0 && attempt < 40 && !userDisconnected {
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    if !userDisconnected { reconnect(attempt: attempt + 1) }
                } else {
                    state = .failed(error.localizedDescription)
                }
            }
        }
    }

    private func autoReconnect(after err: Error?) { reconnect(attempt: 1) }

    private func reconnect(attempt: Int) {
        switch LastAdapter.load() {
        case .ble(let id, let name)?:
            if let t = scanner.transport(forID: id) { connect(t, label: name, attempt: attempt) }
            else { state = .failed("Link lost") }
        case .wifi(let h, let p)?: connect(WiFiTransport(host: h, port: p), label: "\(h):\(p)", attempt: attempt)
        case nil: state = .failed("Link lost")
        }
    }

    func disconnect() {
        userDisconnected = true
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
        discoverProgress = nil
        knownFaultCodes = nil
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
                var ids = self.selected
                for extra: UInt8 in [0x05, 0x0C, 0x0D, 0x11, 0x42, 0x62, 0x63] where !ids.contains(extra) &&
                    (self.supported.isEmpty || self.supported.contains(extra)) { ids.append(extra) }
                let pids = ids.compactMap { PIDs.byID[$0] }
                if pids.isEmpty { try? await Task.sleep(nanoseconds: 200_000_000); continue }
                let r = await svc.read(pids)
                self.apply(r)
                if let v = r[0x0D] {
                    self.speedTrace.append(SpeedSample(t: Date().timeIntervalSince1970, v: v))
                    if self.speedTrace.count > 100 { self.speedTrace.removeFirst(self.speedTrace.count - 100) }
                }
                cycle += 1
                // Car's own module voltage (PID 42) is accurate; cheap adapters' ATRV can read volts off.
                if let v = r[0x42] {
                    self.batteryVoltage = v
                    if cycle % 50 == 5, let link = self.currentLink, let av = await svc.batteryVoltage() {
                        SavedAdapter.learnVoltage(link, adapterV: av, carV: v)      // learn this adapter's voltmeter error
                    }
                } else if cycle % 25 == 0, let av = await svc.batteryVoltage() {
                    self.batteryVoltage = av - (SavedAdapter.offset(self.currentLink) ?? 0)
                }
                if self.wantOil, self.family == .vag, self.vagSupported, cycle % 8 == 0 {
                    self.oilTemp = await svc.readOilTemp()
                }
                if cycle % 600 == 0 { await self.watchFaults(svc) }
                self.checkAlerts()
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
    func exclusive<T>(_ work: (OBDService) async throws -> T) async rethrows -> T? {
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
            refreshModuleList()
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
    func scanVAG(rediscover: Bool = false) async {
        await exclusive { svc in
            vagSupported = await svc.supportsVAG
            guard vagSupported else { return }
            if family.discovered {
                let key = vin ?? ""
                if rediscover || HyundaiModuleMemory.load(key).isEmpty {
                    vagScanProgress = 0
                    discoverProgress = (0, 0)
                    let found = await svc.hyundaiDiscover(family: family) { p, n in await MainActor.run { self.discoverProgress = (p, n) } }
                    HyundaiModuleMemory.save(key, found.map(\.address))
                    discoverProgress = nil
                }
                vagModules = HyundaiModuleMemory.load(key).map { VAGModule.discovered($0, family) }
            } else {
                vagModules = VAGModule.all
            }
            var out = [VAGReport]()
            let all = vagModules
            for (i, m) in all.enumerated() {
                vagScanProgress = Double(i) / Double(max(all.count, 1))
                let r: VAGReport
                if family.discovered { r = await svc.hyundaiReport(m) }
                else { r = await svc.vagReport(m) ?? VAGReport(module: m, present: false, faults: []) }
                if r.present { recordFaults(module: m, faults: r.faults) }
                out.append(r)
                vagReports = out
            }
            vagScanProgress = nil
        }
    }

    /// Clears one VAG module only, then re-reads that module.
    func clearVAG(_ m: VAGModule) async throws {
        try await exclusive { svc in
            if family.discovered { try await svc.hyundaiClear(m) } else { try await svc.vagClear(m) }
            recordClear(module: m)
            let r = family.discovered ? await svc.hyundaiReport(m) : await svc.vagReport(m)
            if let r, let i = vagReports.firstIndex(where: { $0.module == m }) {
                vagReports[i] = r
                recordFaults(module: m, faults: r.faults)
            }
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
        if family.discovered {
            return (await exclusive { svc in await svc.hyundaiIdentification(m) }) ?? []
        }
        return (await exclusive { svc in
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
