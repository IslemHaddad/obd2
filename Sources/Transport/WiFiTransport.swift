import Foundation
import Network

final class WiFiTransport: OBDTransport {
    var onReceive: ((Data) -> Void)?
    var onDisconnect: ((Error?) -> Void)?

    private let connection: NWConnection
    private let queue = DispatchQueue(label: "obd.wifi", qos: .userInitiated)

    init(host: String, port: UInt16) {
        let tcp = NWProtocolTCP.Options()
        tcp.noDelay = true
        tcp.connectionTimeout = 5
        connection = NWConnection(host: NWEndpoint.Host(host),
                                  port: NWEndpoint.Port(rawValue: port)!,
                                  using: NWParameters(tls: nil, tcp: tcp))
    }

    func connect() async throws {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            var resumed = false
            connection.stateUpdateHandler = { [weak self] state in
                switch state {
                case .ready:
                    if !resumed { resumed = true; cont.resume() }
                    self?.receive()
                case .failed(let e):
                    if !resumed { resumed = true; cont.resume(throwing: e) }
                    else { self?.onDisconnect?(e) }
                case .cancelled:
                    if !resumed { resumed = true; cont.resume(throwing: TransportError.notConnected) }
                    else { self?.onDisconnect?(nil) }
                default: break
                }
            }
            connection.start(queue: queue)
        }
    }

    private func receive() {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, done, err in
            guard let self else { return }
            if let data, !data.isEmpty { onReceive?(data) }
            if done || err != nil { onDisconnect?(err); return }
            receive()
        }
    }

    func send(_ data: Data) {
        connection.send(content: data, completion: .idempotent)
    }

    func disconnect() { connection.cancel() }
}
