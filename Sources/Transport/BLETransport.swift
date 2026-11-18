import Foundation
import CoreBluetooth

/// Discovered BLE adapter.
struct BLEDevice: Identifiable, Hashable {
    let id: UUID
    let name: String
    let rssi: Int
}

/// Scans for BLE peripherals. Shared CBCentralManager is handed to the transport.
@Observable
final class BLEScanner: NSObject, CBCentralManagerDelegate {
    private(set) var devices: [BLEDevice] = []
    private(set) var isScanning = false
    private(set) var poweredOn = false

    let central: CBCentralManager
    fileprivate var peripherals: [UUID: CBPeripheral] = [:]
    fileprivate weak var activeTransport: BLETransport?

    override init() {
        central = CBCentralManager(delegate: nil, queue: DispatchQueue(label: "obd.ble", qos: .userInitiated))
        super.init()
        central.delegate = self
    }

    func start() {
        guard central.state == .poweredOn else { return }
        devices = []
        isScanning = true
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    func stop() { central.stopScan(); isScanning = false }

    func transport(for device: BLEDevice) -> BLETransport? {
        guard let p = peripherals[device.id] else { return nil }
        let t = BLETransport(scanner: self, peripheral: p)
        activeTransport = t
        return t
    }

    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        let on = c.state == .poweredOn
        DispatchQueue.main.async { self.poweredOn = on; if on { self.start() } }
    }

    func centralManager(_ c: CBCentralManager, didDiscover p: CBPeripheral,
                        advertisementData ad: [String: Any], rssi: NSNumber) {
        let name = p.name ?? (ad[CBAdvertisementDataLocalNameKey] as? String) ?? ""
        guard !name.isEmpty else { return }
        let d = BLEDevice(id: p.identifier, name: name, rssi: rssi.intValue)
        DispatchQueue.main.async {
            self.peripherals[p.identifier] = p
            if let i = self.devices.firstIndex(where: { $0.id == d.id }) { self.devices[i] = d }
            else { self.devices.append(d) }
            self.devices.sort { Self.rank($0) > Self.rank($1) }
        }
    }

    private static func rank(_ d: BLEDevice) -> Int {
        let n = d.name.uppercased()
        let likely = ["OBD", "ELM", "KONNWEI", "KW", "VLINK", "V-LINK", "IOS-VLINK", "OBDII"].contains { n.contains($0) }
        return (likely ? 1000 : 0) + d.rssi
    }

    func centralManager(_ c: CBCentralManager, didConnect p: CBPeripheral) { activeTransport?.didConnect() }
    func centralManager(_ c: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) { activeTransport?.fail(error) }
    func centralManager(_ c: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) { activeTransport?.didDisconnect(error) }
}

final class BLETransport: NSObject, OBDTransport, CBPeripheralDelegate {
    var onReceive: ((Data) -> Void)?
    var onDisconnect: ((Error?) -> Void)?

    private let scanner: BLEScanner
    private let peripheral: CBPeripheral
    private var writeChar: CBCharacteristic?
    private var notifyChar: CBCharacteristic?
    private var connectCont: CheckedContinuation<Void, Error>?
    private var pendingServices = 0

    init(scanner: BLEScanner, peripheral: CBPeripheral) {
        self.scanner = scanner
        self.peripheral = peripheral
        super.init()
        peripheral.delegate = self
    }

    func connect() async throws {
        scanner.stop()
        try await withCheckedThrowingContinuation { cont in
            connectCont = cont
            scanner.central.connect(peripheral)
        }
    }

    func didConnect() { peripheral.discoverServices(nil) }

    func fail(_ e: Error?) {
        connectCont?.resume(throwing: e ?? TransportError.notConnected); connectCont = nil
    }

    func didDisconnect(_ e: Error?) {
        if connectCont != nil { fail(e) } else { onDisconnect?(e) }
    }

    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        let services = p.services ?? []
        guard error == nil, !services.isEmpty else { return fail(error ?? TransportError.noCharacteristics) }
        pendingServices = services.count
        services.forEach { p.discoverCharacteristics(nil, for: $0) }
    }

    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor s: CBService, error: Error?) {
        // Prefer a service that has both notify + write (common: FFF0, FFE0, 18F0, E7810A71).
        let chars = s.characteristics ?? []
        let n = chars.first { $0.properties.contains(.notify) || $0.properties.contains(.indicate) }
        let w = chars.first { $0.properties.contains(.writeWithoutResponse) || $0.properties.contains(.write) }
        let havePair = notifyChar != nil && writeChar != nil && notifyChar?.service == writeChar?.service
        if !havePair {
            if let n, let w { notifyChar = n; writeChar = w }
            else { notifyChar = notifyChar ?? n; writeChar = writeChar ?? w }
        }
        pendingServices -= 1
        if pendingServices == 0 {
            guard let notifyChar else { return fail(TransportError.noCharacteristics) }
            p.setNotifyValue(true, for: notifyChar)
        }
    }

    func peripheral(_ p: CBPeripheral, didUpdateNotificationStateFor c: CBCharacteristic, error: Error?) {
        guard writeChar != nil, error == nil else { return fail(error ?? TransportError.noCharacteristics) }
        connectCont?.resume(); connectCont = nil
    }

    func peripheral(_ p: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error: Error?) {
        if let v = c.value, !v.isEmpty { onReceive?(v) }
    }

    func send(_ data: Data) {
        guard let w = writeChar else { return }
        let type: CBCharacteristicWriteType = w.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse
        let mtu = max(20, peripheral.maximumWriteValueLength(for: type))
        var i = data.startIndex
        while i < data.endIndex {
            let end = data.index(i, offsetBy: mtu, limitedBy: data.endIndex) ?? data.endIndex
            peripheral.writeValue(data[i..<end], for: w, type: type)
            i = end
        }
    }

    func disconnect() { scanner.central.cancelPeripheralConnection(peripheral) }
}
