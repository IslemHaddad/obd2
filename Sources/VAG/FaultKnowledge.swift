import Foundation

// Fault explanations built from what the module actually reports:
//  • VW fault number = the 3-byte UDS DTC in decimal (the same number VCDS / OBDeleven / ODIS show)
//  • failure type byte (SAE J2012-DA) → exact failure ("Actuator stuck", "Open circuit", …)
//  • status byte (ISO 14229) → active now / this drive / confirmed / warning lamp
//  • which system the module is → what components sit behind it, and how to test it.
// VW's own per-number fault text lives in VW's licensed label database and is not on the car;
// the "Look up" link searches that number for the exact component name.

struct FaultExplanation {
    let title: String
    let codeLine: String
    let meaning: String
    let checks: [String]
    let flags: [String]
    let lookupQuery: String
}

enum FaultKnowledge {
    /// SAE J2012-DA failure type bytes.
    static let ftb: [UInt8: String] = [
        0x00: "No sub-type information", 0x01: "General electrical failure", 0x02: "General signal failure",
        0x03: "FM / PWM failure", 0x04: "System internal failure", 0x05: "System programming failure",
        0x06: "Algorithm-based failure", 0x07: "Mechanical failure", 0x08: "Bus signal / message failure",
        0x09: "Component failure",
        0x11: "Circuit short to ground", 0x12: "Circuit short to battery", 0x13: "Circuit open",
        0x14: "Circuit short to ground or open", 0x15: "Circuit short to battery or open",
        0x16: "Circuit voltage below threshold", 0x17: "Circuit voltage above threshold",
        0x18: "Circuit current below threshold", 0x19: "Circuit current above threshold",
        0x1A: "Circuit resistance below threshold", 0x1B: "Circuit resistance above threshold",
        0x1C: "Circuit voltage out of range", 0x1D: "Circuit current out of range",
        0x1E: "Circuit resistance out of range", 0x1F: "Circuit intermittent",
        0x21: "Signal amplitude below minimum", 0x22: "Signal amplitude above maximum",
        0x23: "Signal stuck low", 0x24: "Signal stuck high", 0x25: "Signal shape / waveform failure",
        0x26: "Signal rate of change below threshold", 0x27: "Signal rate of change above threshold",
        0x28: "Signal bias level out of range / zero adjustment failure", 0x29: "Signal invalid",
        0x2A: "Signal stuck in range", 0x2B: "Signal cross-coupled", 0x2F: "Signal erratic",
        0x31: "No signal", 0x32: "Signal low time below minimum", 0x33: "Signal low time above maximum",
        0x34: "Signal high time below minimum", 0x35: "Signal high time above maximum",
        0x36: "Signal frequency too low", 0x37: "Signal frequency too high", 0x38: "Signal frequency incorrect",
        0x39: "Too few pulses", 0x3A: "Too many pulses",
        0x41: "General checksum failure", 0x42: "General memory failure", 0x43: "Special memory failure",
        0x44: "Data memory failure", 0x45: "Program memory failure", 0x46: "Calibration / parameter memory failure",
        0x47: "Watchdog / safety processor failure", 0x48: "Supervision software failure",
        0x49: "Internal electronic failure", 0x4A: "Incorrect component installed", 0x4B: "Over temperature",
        0x51: "Not programmed", 0x52: "Not activated", 0x53: "Deactivated", 0x54: "Missing calibration",
        0x55: "Not configured (coding)", 0x56: "Invalid / incompatible configuration",
        0x57: "Invalid / incompatible software component",
        0x61: "Signal calculation failure", 0x62: "Signal compare failure", 0x63: "Circuit / component protection time-out",
        0x64: "Signal plausibility failure", 0x65: "Signal has too few transitions / events",
        0x66: "Signal has too many transitions / events", 0x67: "Signal incorrect after event", 0x68: "Event information",
        0x71: "Actuator stuck", 0x72: "Actuator stuck open", 0x73: "Actuator stuck closed", 0x74: "Actuator slipping",
        0x75: "Emergency position not reachable", 0x76: "Wrong mounting position", 0x77: "Commanded position not reachable",
        0x78: "Alignment or adjustment incorrect", 0x79: "Mechanical linkage failure", 0x7A: "Fluid leak or seal failure",
        0x7B: "Low fluid level",
        0x81: "Invalid serial data received", 0x82: "Alive / sequence counter incorrect",
        0x83: "Signal protection value incorrect", 0x84: "Signal below allowable range",
        0x85: "Signal above allowable range", 0x86: "Signal invalid", 0x87: "Missing message", 0x88: "Bus off",
        0x8F: "Erratic",
        0x91: "Parametric", 0x92: "Performance or incorrect operation", 0x93: "No operation",
        0x94: "Unexpected operation", 0x95: "Incorrect assembly", 0x96: "Component internal failure",
        0x97: "Component or system operation obstructed or blocked", 0x98: "Component or system over temperature",
    ]

    struct Category { let name: String; let meaning: String; let checks: [String] }

    static func category(_ t: UInt8) -> Category {
        // 0x01-0x09 are the "general" form of each group (0x04 = general internal failure → group 4).
        switch (0x01...0x09).contains(t) ? t : t >> 4 {
        case 0x1:
            return .init(name: "Electrical circuit",
                         meaning: "A wire, connector or part in this circuit is shorted, open, or has the wrong voltage, current or resistance.",
                         checks: ["Unplug and inspect the connector of the part (corrosion, bent or pushed-back pins)",
                                  "Look along the wiring for chafing, breaks or water ingress",
                                  "Measure the part's resistance / supply voltage against spec"])
        case 0x2:
            return .init(name: "Signal",
                         meaning: "The signal reaches the module but is wrong — stuck, out of range, erratic or invalid.",
                         checks: ["Check the sensor and its connector",
                                  "Compare the sensor's live value with reality (e.g. temperature vs. actual)",
                                  "Check grounds — a loose ground makes signals drift"])
        case 0x3:
            return .init(name: "Pulse / PWM signal",
                         meaning: "A pulsed (PWM or frequency) signal has the wrong timing or pulse count.",
                         checks: ["Check the part driven or read by PWM (blower, fan, valve, speed sensor)",
                                  "Inspect its wiring and connector"])
        case 0x4:
            return .init(name: "Inside the control unit",
                         meaning: "The control unit found a problem inside itself — memory, checksum, processor or internal electronics.",
                         checks: ["Clear it and re-test: one occurrence after low battery voltage or a jump-start is common",
                                  "Check battery voltage, and this module's fuse and ground",
                                  "If it returns immediately after clearing, the unit needs a software update or replacement"])
        case 0x5:
            return .init(name: "Programming / coding",
                         meaning: "The unit's coding, calibration or software doesn't match the car (not coded, not activated, wrong configuration).",
                         checks: ["Was this module replaced or recoded recently?",
                                  "Check the coding matches the car's equipment",
                                  "Clear and re-test — some appear once after a battery disconnect"])
        case 0x6:
            return .init(name: "Plausibility",
                         meaning: "The module compared signals and the result didn't make sense (two values disagree, or a value is impossible).",
                         checks: ["Check the sensors involved for drift or bad connections",
                                  "Scan the other modules — the bad signal may come from one of them"])
        case 0x7:
            return .init(name: "Mechanical / actuator",
                         meaning: "A moving part (motor, flap, valve, pump) is stuck, blocked, slipping or can't reach its position.",
                         checks: ["Operate the function and listen for the motor / flap",
                                  "Check for obstruction or a broken linkage",
                                  "If the part was replaced, it must be calibrated (basic setting)"])
        case 0x8:
            return .init(name: "Communication",
                         meaning: "A message from another module is missing or invalid, or the CAN bus dropped out.",
                         checks: ["Scan the other modules — the sender may have its own fault",
                                  "Very common after a flat battery, jump-start or battery change: clear and re-test",
                                  "If it returns: check CAN wiring and connectors of the sending module"])
        case 0x9:
            return .init(name: "Component performance",
                         meaning: "The part is electrically fine but doesn't perform correctly (no operation, wrong operation, overheating).",
                         checks: ["Test the part's function directly",
                                  "Check for overheating, blockage or wear"])
        default:
            return .init(name: "General",
                         meaning: "The module stored the fault without a more specific failure type.",
                         checks: ["Run the Fault Test to see when it appears",
                                  "Check this module's power, ground and connectors"])
        }
    }

    static func ftbText(_ t: UInt8) -> String {
        if let s = ftb[t] { return s }
        return "\(category(t).name) fault (type \(String(format: "%02X", t)))"
    }

    /// ISO 14229 DTC status bits, human readable.
    static func flags(_ s: UInt8) -> [String] {
        var out = [String]()
        if s & 0x01 != 0 { out.append("Failing right now") }
        if s & 0x02 != 0 { out.append("Failed during this ignition cycle") }
        if s & 0x08 != 0 { out.append("Confirmed and stored") }
        else if s & 0x04 != 0 { out.append("Pending — seen once, not yet confirmed") }
        if s & 0x01 == 0, s & 0x08 != 0 { out.append("Not present now (intermittent or already fixed)") }
        if s & 0x80 != 0 { out.append("Requests the warning light") }
        return out
    }
}

// MARK: - What kind of system a module is (VW Group, Hyundai/Kia and Renault names)

enum SystemKind {
    case engine, transmission, brakes, steering, column, climate, body, airbag, cluster, gateway,
         infotainment, door, tyres, parking, key, generic

    static func of(_ m: VAGModule) -> SystemKind {
        let n = m.name.lowercased()
        func has(_ k: String...) -> Bool { k.contains { n.contains($0) } }
        if has("engine", "uce") { return .engine }
        if has("transmission", "gearbox", "tcu", "bva") { return .transmission }
        if has("abs", "brake", "esc", "esp") { return .brakes }
        if has("steering column") { return .column }
        if has("steering", "mdps", "dae") { return .steering }
        if has("air cond", "climat") { return .climate }
        if has("airbag", "srs") { return .airbag }
        if has("instrument", "cluster", "tdb") { return .cluster }
        if has("gateway") { return .gateway }
        if has("infotainment", "audio", "radio", "multimedia", "head unit") { return .infotainment }
        if has("door") { return .door }
        if has("tyre", "tpms") { return .tyres }
        if has("parking") { return .parking }
        if has("smart key", "immobil", "keyless", "hands-free") { return .key }
        if has("central electrics", "body", "bcm", "uch", "ipm") { return .body }
        return .generic
    }

    /// Parts this module watches — where the fault most likely is.
    var components: String {
        switch self {
        case .engine: "Sensors (air mass/pressure, coolant temp, oxygen, cam/crank), ignition coils, injectors, throttle body, fuel pump."
        case .transmission: "Gear selector, input/output speed sensors, shift solenoids, fluid temperature sensor, clutch actuators."
        case .brakes: "4 wheel-speed sensors, ABS pump & valve block, brake light switch, brake pressure sensor, steering-angle and yaw signals."
        case .steering: "Steering torque sensor, steering angle sensor, power-steering motor."
        case .column: "Steering angle sensor, clock spring, steering-wheel buttons, indicator and wiper stalks, horn."
        case .climate: "Blower motor & its regulator, refrigerant pressure/temperature sensor, flap motors (temperature, air distribution, recirculation), compressor regulating valve, cabin/evaporator temperature sensors, sunlight sensor."
        case .body: "Exterior lights & bulbs, wipers, central locking, windows, horn, interior lights, heated screens."
        case .airbag: "Airbag igniters, seat-belt pretensioners, crash sensors, seat occupancy sensor, connectors under the front seats, clock spring."
        case .cluster: "Instrument cluster, fuel level sender, oil level/temperature sensor, washer fluid level, door/handbrake switches."
        case .gateway: "The link between all modules — it stores communication faults and collects faults from other modules (often after low battery)."
        case .infotainment: "Radio/navigation unit, antennas, USB/Bluetooth, speakers, display, microphone, reverse camera."
        case .door: "Window motor, door lock, mirror motor & heater, door switches and handle sensors."
        case .tyres: "Tyre pressure sensors in each wheel, receiver/antenna."
        case .parking: "Parking sensors in the bumpers, buzzer/display, reverse signal."
        case .key: "Key/card antennas, immobilizer coil, door handle sensors, start button."
        case .generic: "The sensors and actuators connected to this module."
        }
    }
}

extension VAGFault {
    /// VW fault number (3-byte DTC in decimal) for VW Group body/chassis modules, SAE code otherwise.
    var vwNumber: String { String(raw) }

    func explain(in m: VAGModule, family: VAGBrand.Family) -> FaultExplanation {
        let kind = SystemKind.of(m)
        let type = FaultKnowledge.ftbText(failureType)
        let cat = FaultKnowledge.category(failureType)
        let sae = failureType == 0 ? dtc : "\(dtc) \(String(format: "%02X", failureType))"
        let known = DTCDatabase.lookup(dtc)
        let title: String
        let codeLine: String
        if powertrain {
            title = known ?? "\(m.name): \(type)"
            codeLine = family == .vag ? "\(sae) · VW \(vwNumber)" : sae
        } else {
            title = "\(m.name): \(type)"
            codeLine = "VW \(vwNumber) · \(sae)"
        }
        var meaning = cat.meaning
        if let known, powertrain { meaning = "\(known). " + (failureType == 0 ? "" : "Failure type: \(type). ") + cat.meaning }
        var checks = cat.checks
        checks.append("Parts behind this module: \(kind.components)")
        let brandWord = family == .vag ? "VCDS" : family == .hyundai ? "Hyundai" : "Renault"
        let q = powertrain && family != .vag ? "\(dtc) \(m.name)" : "\(brandWord) \(powertrain ? sae : vwNumber) \(m.name)"
        return FaultExplanation(title: title, codeLine: codeLine, meaning: meaning, checks: checks,
                                flags: FaultKnowledge.flags(status), lookupQuery: q)
    }
}
