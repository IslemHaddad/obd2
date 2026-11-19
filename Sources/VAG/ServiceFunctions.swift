import Foundation

/// Built-in VAG service-function catalog — the guided "special functions" a VCDS/ThinkDiag
/// subscription normally provides, run on the existing RoutineControl/adaptation engine.
///
/// Honesty: routine IDs differ by ECU/platform. The UI always previews the exact UDS bytes and
/// asks the user to confirm before anything is sent. `confidence == .template` means the ID is a
/// common default to verify against your car (label/ODX data) before it will actually execute.
struct ServiceFn: Identifiable, Hashable {
    enum Kind { case routine, adaptation, procedure }

    let id: String
    let name: String
    let group: String
    let modules: [String]
    let summary: String
    let kind: Kind
    var routine: UInt16 = 0
    var startData: [UInt8] = []
    var did: UInt16 = 0
    var timeout: Double = 30
    var doneOffset: Int? = 0
    var doneValue: UInt8 = 0x02
    let steps: [String]
    let preconditions: [String]
    var caution: String = ""
    var engine: String = "ignition"           // off | ignition | running | any
    var fuel: [String] = []                    // restrict to these fuels; empty = any
    var confidence: String = "template"        // verified | common | template

    var engineLabel: String {
        ["off": "engine off", "ignition": "ignition on, engine off",
         "running": "engine running", "any": "ignition on"][engine] ?? engine
    }

    /// Exact UDS request(s) this will send, for the confirm sheet.
    var preview: String {
        let rid = String(format: "%04X", routine)
        let data = startData.map { String(format: "%02X", $0) }.joined()
        switch kind {
        case .routine:
            return "Enter session 10 03\nStart   31 01 \(rid) \(data)\nPoll    31 03 \(rid)\nStop    31 02 \(rid)"
        case .adaptation:
            let d = String(format: "%04X", did)
            return "Enter session 10 03\nRead   22 \(d)\nWrite  2E \(d) <new value>\nVerify 22 \(d)"
        case .procedure:
            return "Guided steps only — no automatic command is sent."
        }
    }

    /// Bridge routine functions onto the existing BasicSetting runner.
    func asBasicSetting(moduleAddress: String) -> BasicSetting {
        BasicSetting(module: moduleAddress, name: name, routine: routine, startData: startData,
                     timeout: timeout, conditions: preconditions.joined(separator: " · "),
                     doneOffset: doneOffset, doneValue: doneValue)
    }

    static func functions(for address: String?, family: VAGBrand.Family, fuel: String) -> [ServiceFn] {
        catalog.filter { f in
            family == .vag
                && (address == nil || f.modules.contains(address!))
                && (f.fuel.isEmpty || fuel.isEmpty || f.fuel.contains(fuel))
        }
    }

    static let catalog: [ServiceFn] = [
        ServiceFn(id: "throttle_adapt", name: "Throttle Body Adaptation", group: "Engine", modules: ["01"],
            summary: "Re-learns the throttle valve's closed/open stops. Do after cleaning the throttle body or clearing throttle faults, or if idle is unstable.",
            kind: .routine, routine: 0x0402, timeout: 40,
            steps: ["Engine at idle, fully warmed up (coolant ≥ 80 °C).", "All electrical loads off (A/C, lights, fan).",
                    "Do not touch the accelerator.", "Start the routine — the throttle cycles and settles.", "When done, switch ignition off for 20 s."],
            preconditions: ["Engine running and warm", "Accelerator released", "Loads off"],
            caution: "The throttle will move on its own. Keep hands clear of the intake.", engine: "running"),
        ServiceFn(id: "service_reset", name: "Service / Oil Interval Reset", group: "Service", modules: ["17"],
            summary: "Resets the service reminder (oil / inspection) in the instrument cluster after a service.",
            kind: .routine, routine: 0x0351, timeout: 20,
            steps: ["Ignition ON, engine off.", "Confirm the service you actually performed.",
                    "Run the reset; the SERVICE message clears.", "Cycle the ignition and check the cluster."],
            preconditions: ["Ignition on, engine off", "Service actually completed"],
            caution: "Only reset after the work is genuinely done — it changes the maintenance record."),
        ServiceFn(id: "sas_calibration", name: "Steering Angle Sensor Calibration", group: "Steering", modules: ["03", "44"],
            summary: "Zeroes the steering angle sensor. Required after a wheel alignment, steering rack, or SAS replacement, and clears the ESC light when it's an angle fault.",
            kind: .routine, routine: 0x0404, timeout: 30,
            steps: ["On level ground, engine running.", "Wheels pointed perfectly straight ahead.",
                    "Do not move the steering wheel during calibration.", "Run it, then drive straight briefly to confirm the light is out."],
            preconditions: ["Engine running", "Wheels straight ahead", "Vehicle stationary"],
            caution: "Wrong wheel position calibrates a wrong zero — make sure the steering is truly centred.", engine: "running"),
        ServiceFn(id: "abs_bleed", name: "ABS Brake Bleeding", group: "Brakes", modules: ["03"],
            summary: "Cycles the ABS pump and valves so you can bleed air from the ABS unit — needed after opening the hydraulic circuit or replacing the ABS module.",
            kind: .routine, routine: 0x0301, timeout: 120,
            steps: ["Engine off, ignition ON. Reservoir topped up.", "Have a second person at the bleeder screws.",
                    "Run it and follow the per-wheel pumping prompts.", "Keep the reservoir full throughout.", "Finish, then do a normal pedal bleed."],
            preconditions: ["Ignition on", "Reservoir full", "Second person ready"],
            caution: "Never let the reservoir run dry — it pulls air into the ABS unit."),
        ServiceFn(id: "epb_service", name: "Parking Brake Service Mode", group: "Brakes", modules: ["53", "03"],
            summary: "Opens the electronic parking brake calipers to the service position for rear pad changes, then closes them. Only if the car has an electronic handbrake.",
            kind: .routine, routine: 0x0405, timeout: 30,
            steps: ["Ignition ON, engine off, level ground, wheels chocked.", "Run 'open' — the rear calipers retract.",
                    "Change the pads.", "Run 'close', then press the EPB switch a few times.", "Check the handbrake holds before driving."],
            preconditions: ["Ignition on", "Wheels chocked", "Car has electronic handbrake"],
            caution: "Confirm the brake holds before moving. If the car has a manual handbrake, this doesn't apply."),
        ServiceFn(id: "battery_reg", name: "Battery Registration", group: "Battery", modules: ["01", "09"],
            summary: "Registers a new battery's capacity and serial so the charging/energy management adapts. Only on cars with battery monitoring (usually start-stop / AGM).",
            kind: .adaptation, did: 0x1480,
            steps: ["Ignition ON, engine off.", "Enter the new battery's Ah capacity and serial from its label.",
                    "Write and verify.", "Cycle the ignition."],
            preconditions: ["Ignition on", "New battery fitted", "Car has battery monitoring"],
            caution: "Wrong capacity makes the charging strategy wrong. Skip if the car has no BMS."),
        ServiceFn(id: "injector_coding", name: "Injector Coding / Calibration", group: "Engine", modules: ["01"],
            summary: "Writes the injector correction (IMA/flow) codes after replacing injectors, so the ECU trims each cylinder correctly.",
            kind: .adaptation, did: 0x0391,
            steps: ["Ignition ON, engine off.", "Enter each injector's code per cylinder.", "Write and verify.", "Start the engine and check idle smoothness."],
            preconditions: ["Ignition on, engine off", "Injector codes to hand"],
            caution: "Wrong codes cause rough running. Match each code to the correct cylinder."),
        ServiceFn(id: "egr_adapt", name: "EGR Adaptation / Learn", group: "Engine", modules: ["01"],
            summary: "Re-learns the EGR valve range after cleaning or replacement. Mostly diesel.",
            kind: .routine, routine: 0x0408, timeout: 60,
            steps: ["Engine warm and idling, no loads.", "Do not touch the accelerator.", "Run it; the EGR valve cycles and relearns.", "Switch off for 20 s when done."],
            preconditions: ["Engine warm and idling", "Accelerator released"],
            caution: "The EGR valve moves on its own during the routine.", engine: "running"),
        ServiceFn(id: "gearbox_relearn", name: "Gearbox / DSG Adaptation", group: "Engine", modules: ["02"],
            summary: "Resets and re-learns transmission clutch/shift adaptations after service or clutch work. Follow with a defined drive cycle.",
            kind: .routine, routine: 0x0401, timeout: 60,
            steps: ["Engine warm, selector in P, brake held.", "Run the reset.", "Then drive the adaptation cycle (varied gentle shifts).", "Shift quality improves as it relearns."],
            preconditions: ["Engine warm", "Selector in P", "Brake held"],
            caution: "Shifts may feel firm until the drive-cycle relearn completes.", engine: "running"),
        ServiceFn(id: "immobilizer_reset", name: "Immobilizer / Key Learn", group: "Security", modules: ["09", "17"],
            summary: "Immobilizer adaptation (key matching / component protection). Security-protected — usually needs the vehicle's secret PIN/SKC and online access.",
            kind: .procedure,
            steps: ["This needs the vehicle's component-protection PIN/SKC.", "Without it the ECU stays security-locked (NRC 0x33).", "Use the dealer/ODIS online path or a known-good SKC source."],
            preconditions: ["Vehicle PIN/SKC available"],
            caution: "Immobilizer work can leave the car unable to start. Only with the correct secret."),
        ServiceFn(id: "tpms_reset", name: "Tyre Pressure (TPMS) Reset", group: "Comfort", modules: ["17"],
            summary: "Resets the tyre-pressure monitor to the current pressures as the new reference, after inflation or a tyre change.",
            kind: .routine, routine: 0x0409, timeout: 20,
            steps: ["Set all tyres to the correct cold pressures.", "Ignition ON.", "Run the reset (or use the car's menu / SET button).", "Drive a few minutes to confirm the warning stays off."],
            preconditions: ["Tyres at correct pressure", "Ignition on"],
            caution: "On indirect TPMS this just relearns; it can't detect a real slow leak immediately."),
        ServiceFn(id: "sunroof_init", name: "Sunroof Initialisation", group: "Comfort", modules: ["09"],
            summary: "Re-initialises the sunroof's end stops and one-touch after a battery disconnect or if it won't auto-close.",
            kind: .procedure,
            steps: ["Ignition ON.", "Hold the switch to fully close, keep holding 10–20 s.", "Release, then tilt/close once more to confirm one-touch.", "(Some cars expose this as a basic-setting routine instead.)"],
            preconditions: ["Ignition on"],
            caution: "Keep fingers clear of the glass during initialisation."),
        ServiceFn(id: "headlight_afs", name: "Adaptive Front Lighting Calibration", group: "Comfort", modules: ["09"],
            summary: "Calibrates headlight range / adaptive front-lighting (AFS) aim after a headlight or level sensor replacement.",
            kind: .routine, routine: 0x040A, timeout: 30,
            steps: ["Car on level ground, correct ride height, engine running.", "Nobody in the car, normal load.", "Run it; the headlights sweep and centre.", "Check beam aim on a wall afterwards."],
            preconditions: ["Level ground", "Engine running", "Normal load"],
            caution: "Mis-aimed beams dazzle oncoming drivers. Verify aim after.", engine: "running"),
        ServiceFn(id: "air_suspension", name: "Air Suspension Ride-Height Calibration", group: "Comfort", modules: ["34"],
            summary: "Calibrates air-suspension ride heights after a level-sensor or strut replacement. Only on air-sprung cars.",
            kind: .routine, routine: 0x040B, timeout: 120,
            steps: ["Car on level ground, doors closed, normal load.", "Measure actual ride heights as the car asks.", "Enter them and run the calibration.", "Let the car settle and recheck."],
            preconditions: ["Level ground", "Air suspension fitted"],
            caution: "Wrong heights affect handling and headlight aim."),
        ServiceFn(id: "dpf_regen", name: "DPF Forced Regeneration", group: "Engine", modules: ["01"],
            summary: "Forces a diesel particulate filter burn-off when soot load is high. Diesel only.",
            kind: .routine, routine: 0x0407, timeout: 1800,
            steps: ["Diesel engine, warmed up, in a well-ventilated open area.", "Fuel ≥ 1/4 tank; nothing flammable near the exhaust.",
                    "Start the regen and let it run — exhaust gets very hot.", "Keep running until complete.", "Do not leave the vehicle unattended."],
            preconditions: ["Diesel engine", "Warm engine", "Open ventilated area", "≥1/4 tank"],
            caution: "Exhaust reaches extreme temperatures. Never run indoors or near anything flammable.",
            engine: "running", fuel: ["diesel"]),
    ]
}
