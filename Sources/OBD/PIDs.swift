import Foundation

/// SAE J1979 Mode 01 PID definition.
struct PID: Identifiable, Hashable {
    let id: UInt8
    let name: String
    let unit: String
    let bytes: Int
    let min: Double
    let max: Double
    let decode: @Sendable ([UInt8]) -> Double

    static func == (a: PID, b: PID) -> Bool { a.id == b.id }
    func hash(into h: inout Hasher) { h.combine(id) }
    var hex: String { String(format: "%02X", id) }
}

private func A(_ d: [UInt8]) -> Double { Double(d[0]) }
private func AB(_ d: [UInt8]) -> Double { Double(Int(d[0]) << 8 | Int(d[1])) }

enum PIDs {
    static let all: [PID] = [
        PID(id: 0x04, name: "Engine Load", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x05, name: "Coolant Temp", unit: "°C", bytes: 1, min: -40, max: 215) { A($0) - 40 },
        PID(id: 0x06, name: "Short Fuel Trim B1", unit: "%", bytes: 1, min: -100, max: 99.2) { A($0) / 1.28 - 100 },
        PID(id: 0x07, name: "Long Fuel Trim B1", unit: "%", bytes: 1, min: -100, max: 99.2) { A($0) / 1.28 - 100 },
        PID(id: 0x08, name: "Short Fuel Trim B2", unit: "%", bytes: 1, min: -100, max: 99.2) { A($0) / 1.28 - 100 },
        PID(id: 0x09, name: "Long Fuel Trim B2", unit: "%", bytes: 1, min: -100, max: 99.2) { A($0) / 1.28 - 100 },
        PID(id: 0x0A, name: "Fuel Pressure", unit: "kPa", bytes: 1, min: 0, max: 765) { A($0) * 3 },
        PID(id: 0x0B, name: "Intake MAP", unit: "kPa", bytes: 1, min: 0, max: 255) { A($0) },
        PID(id: 0x0C, name: "RPM", unit: "rpm", bytes: 2, min: 0, max: 8000) { AB($0) / 4 },
        PID(id: 0x0D, name: "Speed", unit: "km/h", bytes: 1, min: 0, max: 255) { A($0) },
        PID(id: 0x0E, name: "Timing Advance", unit: "°", bytes: 1, min: -64, max: 63.5) { A($0) / 2 - 64 },
        PID(id: 0x0F, name: "Intake Air Temp", unit: "°C", bytes: 1, min: -40, max: 215) { A($0) - 40 },
        PID(id: 0x10, name: "MAF Rate", unit: "g/s", bytes: 2, min: 0, max: 655.35) { AB($0) / 100 },
        PID(id: 0x11, name: "Throttle Position", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x1F, name: "Run Time", unit: "s", bytes: 2, min: 0, max: 65535) { AB($0) },
        PID(id: 0x21, name: "Distance w/ MIL", unit: "km", bytes: 2, min: 0, max: 65535) { AB($0) },
        PID(id: 0x22, name: "Fuel Rail Pressure", unit: "kPa", bytes: 2, min: 0, max: 5177) { AB($0) * 0.079 },
        PID(id: 0x23, name: "Fuel Rail Gauge Pressure", unit: "kPa", bytes: 2, min: 0, max: 655350) { AB($0) * 10 },
        PID(id: 0x2C, name: "Commanded EGR", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x2F, name: "Fuel Level", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x31, name: "Distance Since Clear", unit: "km", bytes: 2, min: 0, max: 65535) { AB($0) },
        PID(id: 0x33, name: "Barometric Pressure", unit: "kPa", bytes: 1, min: 0, max: 255) { A($0) },
        PID(id: 0x3C, name: "Catalyst Temp B1S1", unit: "°C", bytes: 2, min: -40, max: 6513) { AB($0) / 10 - 40 },
        PID(id: 0x42, name: "Module Voltage", unit: "V", bytes: 2, min: 0, max: 65.535) { AB($0) / 1000 },
        PID(id: 0x43, name: "Absolute Load", unit: "%", bytes: 2, min: 0, max: 25700) { AB($0) * 100 / 255 },
        PID(id: 0x44, name: "Commanded AFR λ", unit: "λ", bytes: 2, min: 0, max: 2) { AB($0) * 2 / 65536 },
        PID(id: 0x45, name: "Relative Throttle", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x46, name: "Ambient Air Temp", unit: "°C", bytes: 1, min: -40, max: 215) { A($0) - 40 },
        PID(id: 0x47, name: "Throttle Pos B", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x49, name: "Accel Pedal D", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x4A, name: "Accel Pedal E", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x4C, name: "Commanded Throttle", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x4D, name: "Time w/ MIL", unit: "min", bytes: 2, min: 0, max: 65535) { AB($0) },
        PID(id: 0x4E, name: "Time Since Clear", unit: "min", bytes: 2, min: 0, max: 65535) { AB($0) },
        PID(id: 0x51, name: "Fuel Type", unit: "", bytes: 1, min: 0, max: 255) { A($0) },
        PID(id: 0x52, name: "Ethanol %", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x5A, name: "Rel. Accel Pedal", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x5B, name: "Hybrid Battery Life", unit: "%", bytes: 1, min: 0, max: 100) { A($0) * 100 / 255 },
        PID(id: 0x5C, name: "Oil Temp", unit: "°C", bytes: 1, min: -40, max: 210) { A($0) - 40 },
        PID(id: 0x5E, name: "Fuel Rate", unit: "L/h", bytes: 2, min: 0, max: 3212) { AB($0) / 20 },
        PID(id: 0x61, name: "Demanded Torque", unit: "%", bytes: 1, min: -125, max: 130) { A($0) - 125 },
        PID(id: 0x62, name: "Actual Torque", unit: "%", bytes: 1, min: -125, max: 130) { A($0) - 125 },
        PID(id: 0x63, name: "Reference Torque", unit: "Nm", bytes: 2, min: 0, max: 65535) { AB($0) },
    ]

    /// Synthetic PID for SEAT/VW engine oil temperature (read from module 01 DID 11BD, injected by the session).
    /// id 0xFF is not a real OBD PID, so the poller never requests it on the bus.
    static let oilTemp = PID(id: 0xFF, name: "Oil Temp", unit: "°C", bytes: 2, min: 40, max: 150) { _ in 0 }

    static let byID: [UInt8: PID] = Dictionary(uniqueKeysWithValues: (all + [oilTemp]).map { ($0.id, $0) })

    /// Response data length for any mode 01 PID (needed to split multi-PID responses).
    static func length(of pid: UInt8) -> Int? {
        if let p = byID[pid] { return p.bytes }
        switch pid {
        case 0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0, 0x01, 0x41: return 4
        case 0x03: return 2
        case 0x12, 0x13, 0x1C, 0x1D, 0x1E, 0x30: return 1
        case 0x14...0x1B: return 2
        case 0x24...0x2B, 0x34...0x3B: return 4
        case 0x3D...0x3F: return 2
        default: return nil
        }
    }
}
