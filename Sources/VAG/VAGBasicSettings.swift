import Foundation

/// UDS RoutineControl-based basic setting: 31 01 start → 31 03 poll results → (31 02 stop).
struct BasicSetting: Identifiable, Codable, Hashable {
    var id = UUID()
    var module: String
    var name: String
    var routine: UInt16
    var startData: [UInt8] = []
    var timeout: Double = 60                 // seconds
    var conditions: String = ""              // user notes shown before start (e.g. "Engine off, ignition on")
    var watch: [UUID] = []                   // Measurement ids read while running
    var doneOffset: Int?                     // completion: result[doneOffset] == doneValue
    var doneValue: UInt8 = 0
    var failValue: UInt8?                    // optional: result[doneOffset] == failValue → failed

    var ridHex: String { String(format: "%04X", routine) }
    var startHex: String { startData.map { String(format: "%02X", $0) }.joined() }
    var startCommand: String { "3101" + ridHex + startHex }
    var resultCommand: String { "3103" + ridHex }
    var stopCommand: String { "3102" + ridHex }

    enum Verdict { case running, done, failed }
    func verdict(_ result: [UInt8]) -> Verdict {
        guard let o = doneOffset, o < result.count else { return .running }
        if let f = failValue, result[o] == f { return .failed }
        return result[o] == doneValue ? .done : .running
    }

    private static let key = "vag.basicsettings.v1"
    static func load() -> [BasicSetting] {
        guard let d = UserDefaults.standard.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([BasicSetting].self, from: d)) ?? []
    }
    static func save(_ b: [BasicSetting]) {
        if let d = try? JSONEncoder().encode(b) { UserDefaults.standard.set(d, forKey: key) }
    }
}
