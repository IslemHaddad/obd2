import Foundation

/// Byte pipe to an ELM327-compatible adapter.
protocol OBDTransport: AnyObject {
    var onReceive: ((Data) -> Void)? { get set }
    var onDisconnect: ((Error?) -> Void)? { get set }
    func connect() async throws
    func send(_ data: Data)
    func disconnect()
}

enum TransportError: LocalizedError {
    case bluetoothUnavailable, noCharacteristics, timeout, notConnected
    var errorDescription: String? {
        switch self {
        case .bluetoothUnavailable: "Bluetooth is off or unauthorized"
        case .noCharacteristics: "Adapter has no usable read/write characteristics"
        case .timeout: "Adapter did not respond"
        case .notConnected: "Not connected"
        }
    }
}
