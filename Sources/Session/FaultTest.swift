import Foundation

// MARK: - Fault Test: the module is watched live (fault memory read ~1×/s) while the user operates
// the system step by step, like a technician would. Anything that fails pops up with the step it failed in.

struct TestStep: Hashable {
    let title: String
    let detail: String
}

struct FaultTestRun {
    enum Phase: Equatable { case preparing, clearing, watching, finished, error(String) }
    struct Hit: Identifiable {
        let fault: VAGFault
        let step: Int
        let at: Date
        var id: String { fault.id }
    }
    let module: VAGModule
    let steps: [TestStep]
    var phase: Phase = .preparing
    var step = 0
    var before: [VAGFault] = []      // already in memory when watching started
    var hits: [Hit] = []             // appeared / became active during the test
    var reads = 0
    var missedReads = 0
    var note: String?
    var running: Bool { phase == .preparing || phase == .clearing || phase == .watching }
}

extension SystemKind {
    var testSteps: [TestStep] {
        func s(_ t: String, _ d: String) -> TestStep { TestStep(title: t, detail: d) }
        switch self {
        case .climate: return [
            s("Start the engine", "The compressor and its sensors are only tested with the engine running."),
            s("A/C ON, fan to maximum", "Leave it running for about 30 seconds."),
            s("Temperature to coldest, then hottest", "The temperature flap motor travels end to end. Wait ~10 s at each end."),
            s("Air distribution: windscreen → face → feet", "Tests the distribution flap motors. Pause on each one."),
            s("Recirculation on, then off", "Tests the fresh-air / recirculation flap."),
            s("Fan speed 1 → max → 1", "Tests the blower and its regulator at every speed."),
            s("Front / rear demist on, then off", "Skip if the car doesn't have it."),
            s("AUTO for one minute", "The unit now drives everything itself — just wait."),
        ]
        case .brakes: return [
            s("Start the engine", "The ABS pump and valves self-test when the engine starts."),
            s("Steering lock to lock", "Turn fully left, then fully right (steering-angle signal)."),
            s("Press the brake pedal firmly 3 times", "Tests the brake light switch and pressure sensor."),
            s("Drive slowly above 20 km/h", "Wheel speed sensors are only checked while moving. Let a passenger hold the phone."),
            s("Brake to a stop", "Normal, firm stop."),
        ]
        case .steering: return [
            s("Start the engine", "Power steering works only with the engine running."),
            s("Steering lock to lock, standing still", "Slowly, twice."),
            s("Drive slowly with a few turns", "Torque and angle sensors are checked while moving."),
        ]
        case .column: return [
            s("Ignition ON", ""),
            s("Indicators left, right, hazards", ""),
            s("Wipers: every speed + washer", "Front and rear."),
            s("Horn", ""),
            s("Steering-wheel buttons", "Press every button on the wheel (volume, phone, cruise…)."),
            s("Steering lock to lock", "Tests the steering-angle sensor and clock spring."),
        ]
        case .engine: return [
            s("Start the engine and idle 1 minute", ""),
            s("Rev to ~3000 rpm three times", "Hold each rev for 2–3 seconds."),
            s("Turn on heavy loads", "A/C, headlights, rear demist on — the idle must stay steady."),
            s("Let it reach operating temperature", "Many sensor tests only run warm (coolant ~90 °C)."),
            s("Short drive with acceleration", "Have a passenger hold the phone."),
        ]
        case .transmission: return [
            s("Start the engine, foot on the brake", ""),
            s("Selector P → R → N → D, pause 3 s each", "Manual gearbox: press the clutch and go through the gears."),
            s("Drive and let it shift through all gears", "Have a passenger hold the phone."),
        ]
        case .body: return [
            s("Ignition ON", ""),
            s("Headlights: side, low, high, flash", ""),
            s("Indicators left, right, hazards", ""),
            s("Press the brake pedal", "Brake lights."),
            s("Reverse gear (engine off, clutch in)", "Reverse lights."),
            s("Wipers front and rear + washers", ""),
            s("Lock and unlock with the key", ""),
            s("Open and close each door", "Interior lights and door switches."),
            s("Horn and rear window heater", ""),
        ]
        case .airbag: return [
            s("Ignition ON — don't unplug anything", "Never touch airbag connectors with the ignition on."),
            s("Slide both front seats fully forward and back", "Connectors under the seats are the most common cause."),
            s("Buckle and unbuckle every seat belt", ""),
            s("Steering lock to lock", "Tests the clock spring."),
            s("Wait 30 seconds", "The airbag unit finishes its self-test."),
        ]
        case .cluster: return [
            s("Ignition ON", "Watch for warning lights that stay on."),
            s("Start the engine", "Oil pressure, charging and level checks."),
            s("Press the trip / menu buttons", ""),
            s("Open and close a door, release the handbrake", ""),
        ]
        case .gateway: return [
            s("Ignition OFF for 30 seconds", ""),
            s("Ignition ON, then start the engine", "The gateway checks it hears every module."),
            s("Use a few functions (lights, radio, A/C)", ""),
        ]
        case .infotainment: return [
            s("Radio ON, change station", ""),
            s("Volume up and down", "Listen to every speaker."),
            s("Connect phone Bluetooth / USB", ""),
            s("Navigation / reverse camera", "If fitted."),
        ]
        case .door: return [
            s("Ignition ON", ""),
            s("Window fully down and fully up", ""),
            s("Lock and unlock", ""),
            s("Mirror: move in all directions, fold if electric", ""),
            s("Rear demist on (mirror heater)", ""),
            s("Open and close the door", ""),
        ]
        case .tyres: return [
            s("Drive above 25 km/h for a few minutes", "Tyre sensors only transmit while rolling."),
        ]
        case .parking: return [
            s("Ignition ON, engine running", ""),
            s("Select reverse", "Sensors activate."),
            s("Approach an obstacle slowly", "Every sensor should beep."),
        ]
        case .key: return [
            s("Lock and unlock with the key / card", ""),
            s("Start and stop the engine twice", ""),
        ]
        case .generic: return [
            s("Ignition ON", ""),
            s("Start the engine", ""),
            s("Use every function of this system", ""),
            s("Short drive", "Have a passenger hold the phone."),
        ]
        }
    }
}

// MARK: - Coding capability (is this adapter + module able to write coding without a login?)

enum CodingAbility: Codable, Equatable {
    case yes
    case needsLogin
    case adapterCannot
    case noCoding
    case refused(String)

    var label: String {
        switch self {
        case .yes: "Supported"
        case .needsLogin: "Needs login"
        case .adapterCannot: "Adapter can't"
        case .noCoding: "No coding"
        case .refused: "Refused"
        }
    }
    var explanation: String {
        switch self {
        case .yes: "This adapter can code this module."
        case .needsLogin: "The module only accepts coding after a VW security login (online login like ODIS / OBDeleven Pro). This adapter can read it but not change it."
        case .adapterCannot: "The module accepted the request, but this adapter couldn't send the coding message — coding is too long for its chip. An STN-based adapter (e.g. OBDLink) can."
        case .noCoding: "This module has no long coding."
        case .refused(let r): "The module refused coding: \(r)"
        }
    }

    private static let key = "coding.ability.v1"
    static func load() -> [String: CodingAbility] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [:] }
        return (try? JSONDecoder().decode([String: CodingAbility].self, from: d)) ?? [:]
    }
    static func save(_ v: [String: CodingAbility]) {
        if let d = try? JSONEncoder().encode(v) { UserDefaults.standard.set(d, forKey: key) }
    }
}

extension VehicleSession {
    func codingKey(_ m: VAGModule) -> String {
        "\(adapterProfile?.chip ?? "?")|\(vin ?? "?")|\(m.address)"
    }

    /// Reads the coding and writes the same bytes back unchanged: the only reliable way to know
    /// whether the adapter can send it and the module accepts it without a login.
    func probeCoding(_ m: VAGModule) async -> (CodingAbility, [UInt8]) {
        let r: (CodingAbility, [UInt8], Bool)? = await exclusive { svc in
            guard let current = try? await svc.readCoding(m), !current.isEmpty else { return (.noCoding, [], true) }
            do {
                let back = try await svc.writeCoding(m, current)
                return back == current ? (.yes, current, true) : (.refused("verify mismatch"), current, false)
            } catch let n as UDSNegative {
                switch n.nrc {
                case 0x33, 0x35, 0x36, 0x37: return (.needsLogin, current, true)
                case 0x22: return (.refused("conditions not correct — ignition ON, engine OFF"), current, false)
                default: return (.refused(UDSNegative.names[n.nrc] ?? String(format: "NRC %02X", n.nrc)), current, false)
                }
            } catch {
                // 2E 06 00 + coding > 7 bytes needs a multi-frame send; a plain ELM327 can't do that.
                if current.count + 3 > 7 { return (.adapterCannot, current, true) }
                return (.refused("no answer from the module"), current, false)
            }
        }
        guard let r else { return (.refused("not connected"), []) }
        if r.2 { codingAbility[codingKey(m)] = r.0 }      // only remember definitive answers
        return (r.0, r.1)
    }

    // MARK: Fault test

    func startFaultTest(_ m: VAGModule, clearFirst: Bool) {
        guard faultTest?.running != true else { return }
        faultTest = FaultTestRun(module: m, steps: SystemKind.of(m).testSteps)
        let discovered = family.discovered
        Task {
            let running = pollTask
            pollTask = nil
            running?.cancel()
            await running?.value
            guard let svc = service else { faultTest?.phase = .error("Not connected"); return }
            pollTask = Task { [weak self] in
                if clearFirst {
                    self?.faultTest?.phase = .clearing
                    do {
                        if discovered { try await svc.hyundaiClear(m) } else { try await svc.vagClear(m) }
                        self?.recordClear(module: m)
                    } catch {
                        self?.faultTest?.note = "Couldn't clear first (\(error.localizedDescription)) — watching anyway."
                    }
                }
                await svc.vagOpen(m)
                let first = discovered ? await svc.discoveredFaultsOpen(m) : await svc.vagFaultsOpen(m)
                guard let first else {
                    await svc.vagClose()
                    self?.faultTest?.phase = .error("\(m.name) is not answering.")
                    self?.finishFaultTest(svc, m, last: nil)
                    return
                }
                self?.faultTest?.before = first
                self?.faultTest?.phase = .watching
                var known = Dictionary(first.map { ($0.id, $0.active) }, uniquingKeysWith: { a, _ in a })
                var last = first
                while !Task.isCancelled, let me = self, me.faultTest?.phase == .watching {
                    let now = discovered ? await svc.discoveredFaultsOpen(m) : await svc.vagFaultsOpen(m)
                    guard let now else {
                        me.faultTest?.missedReads += 1
                        await svc.vagOpen(m)                         // re-arm the channel after a hiccup
                        try? await Task.sleep(nanoseconds: 300_000_000)
                        continue
                    }
                    last = now
                    me.faultTest?.reads += 1
                    let stepNow = me.faultTest?.step ?? 0
                    for f in now {
                        let wasActive = known[f.id]
                        // New fault, or a stored one that just became active again.
                        if wasActive == nil || (wasActive == false && f.active),
                           me.faultTest?.hits.contains(where: { $0.id == f.id }) == false {
                            me.faultTest?.hits.append(.init(fault: f, step: stepNow, at: Date()))
                        }
                        known[f.id] = f.active
                    }
                    try? await Task.sleep(nanoseconds: 700_000_000)
                }
                await svc.vagClose()
                self?.finishFaultTest(svc, m, last: last)
            }
        }
    }

    func stopFaultTest() {
        guard faultTest?.running == true else { return }
        if faultTest?.phase == .watching { faultTest?.phase = .finished }
        else { pollTask?.cancel() }
    }

    private func finishFaultTest(_ svc: OBDService, _ m: VAGModule, last: [VAGFault]?) {
        var failed = false
        if case .error? = faultTest?.phase { failed = true }
        if !failed { faultTest?.phase = .finished }
        if let last {
            recordFaults(module: m, faults: last)
            if let i = vagReports.firstIndex(where: { $0.module == m }) { vagReports[i].faults = last }
        }
        pollTask = nil
        if state == .connected { startPolling() }
    }
}
