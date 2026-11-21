import Foundation

enum DTCDatabase {
    static let known: [String: String] = [
        "P0010": "Camshaft Position Actuator Circuit (Bank 1)",
        "P0011": "Camshaft Timing Over-Advanced (Bank 1)",
        "P0016": "Crankshaft/Camshaft Position Correlation (Bank 1 Sensor A)",
        "P0087": "Fuel Rail/System Pressure Too Low",
        "P0100": "Mass Air Flow Circuit Malfunction",
        "P0101": "Mass Air Flow Circuit Range/Performance",
        "P0102": "Mass Air Flow Circuit Low Input",
        "P0106": "MAP Sensor Circuit Range/Performance",
        "P0113": "Intake Air Temperature Circuit High Input",
        "P0117": "Engine Coolant Temperature Circuit Low",
        "P0118": "Engine Coolant Temperature Circuit High",
        "P0121": "Throttle Position Sensor A Range/Performance",
        "P0128": "Coolant Thermostat Below Regulating Temperature",
        "P0131": "O2 Sensor Circuit Low Voltage (B1S1)",
        "P0133": "O2 Sensor Circuit Slow Response (B1S1)",
        "P0135": "O2 Sensor Heater Circuit (B1S1)",
        "P0141": "O2 Sensor Heater Circuit (B1S2)",
        "P0171": "System Too Lean (Bank 1)",
        "P0172": "System Too Rich (Bank 1)",
        "P0174": "System Too Lean (Bank 2)",
        "P0175": "System Too Rich (Bank 2)",
        "P0217": "Engine Overheat Condition",
        "P0234": "Turbocharger Overboost Condition",
        "P0299": "Turbocharger Underboost",
        "P0300": "Random/Multiple Cylinder Misfire Detected",
        "P0301": "Cylinder 1 Misfire Detected", "P0302": "Cylinder 2 Misfire Detected",
        "P0303": "Cylinder 3 Misfire Detected", "P0304": "Cylinder 4 Misfire Detected",
        "P0305": "Cylinder 5 Misfire Detected", "P0306": "Cylinder 6 Misfire Detected",
        "P0325": "Knock Sensor 1 Circuit (Bank 1)",
        "P0335": "Crankshaft Position Sensor A Circuit",
        "P0340": "Camshaft Position Sensor Circuit (Bank 1)",
        "P0380": "Glow Plug/Heater Circuit A",
        "P0401": "EGR Flow Insufficient",
        "P0402": "EGR Flow Excessive",
        "P0420": "Catalyst Efficiency Below Threshold (Bank 1)",
        "P0430": "Catalyst Efficiency Below Threshold (Bank 2)",
        "P0440": "EVAP System Malfunction",
        "P0442": "EVAP System Small Leak Detected",
        "P0455": "EVAP System Large Leak Detected",
        "P0456": "EVAP System Very Small Leak Detected",
        "P0500": "Vehicle Speed Sensor Malfunction",
        "P0505": "Idle Air Control System",
        "P0507": "Idle RPM Higher Than Expected",
        "P0562": "System Voltage Low",
        "P0563": "System Voltage High",
        "P0600": "Serial Communication Link",
        "P0606": "ECM/PCM Processor Fault",
        "P0700": "Transmission Control System Malfunction",
        "P0715": "Input/Turbine Speed Sensor Circuit",
        "P0730": "Incorrect Gear Ratio",
        "P0741": "Torque Converter Clutch Circuit Performance",
        "P2002": "Diesel Particulate Filter Efficiency Below Threshold",
        "P2135": "Throttle/Pedal Position Sensor A/B Voltage Correlation",
        "P242F": "Diesel Particulate Filter Restriction - Ash Accumulation",
        "U0100": "Lost Communication With ECM/PCM",
        "U0101": "Lost Communication With TCM",
        "U0121": "Lost Communication With ABS Module",
        "U0140": "Lost Communication With Body Control Module",
    ]

    // MARK: Online fallback — a full code table fetched once from the project repo and cached on device.
    static let onlineURL = URL(string: "https://raw.githubusercontent.com/IslemHaddad/obd2/main/data/dtc.json")!
    private static let cacheKey = "dtc.online.v1"
    /// Loaded from the on-device cache at first use; refreshed by preloadOnline().
    static var online: [String: String] = {
        if let d = UserDefaults.standard.data(forKey: cacheKey),
           let m = try? JSONDecoder().decode([String: String].self, from: d) { return m }
        return [:]
    }()

    /// Curated set first, then the online table. nil only when a code is in neither.
    static func lookup(_ code: String) -> String? { known[code] ?? online[code] }

    /// Fetch the full code table once and cache it. Best-effort; silent offline.
    static func preloadOnline() async {
        if online.count > 100 { return }                         // already have it from a previous run
        guard let (data, _) = try? await URLSession.shared.data(from: onlineURL),
              let m = try? JSONDecoder().decode([String: String].self, from: data), !m.isEmpty else { return }
        online = m
        UserDefaults.standard.set(data, forKey: cacheKey)
    }

    static func describe(_ code: String) -> String {
        if let d = lookup(code) { return d }
        let chars = Array(code)
        guard chars.count == 5 else { return "Unknown" }
        let generic = chars[1] == "0" || chars[1] == "2" || (chars[0] == "P" && chars[1] == "3" && chars[2] >= "4")
        let scope = generic ? "Generic" : "Manufacturer-specific"
        let area: String
        switch chars[0] {
        case "P":
            switch chars[2] {
            case "0", "1", "2": area = "Fuel & Air Metering"
            case "3": area = "Ignition / Misfire"
            case "4": area = "Auxiliary Emission Controls"
            case "5": area = "Speed / Idle Control"
            case "6": area = "Computer Output Circuit"
            case "7", "8", "9": area = "Transmission"
            case "A", "B", "C": area = "Hybrid Propulsion"
            default: area = "Powertrain"
            }
        case "C": area = "Chassis"
        case "B": area = "Body"
        default: area = "Network Communication"
        }
        return "\(scope) – \(area)"
    }
}
