import SwiftUI

struct RootView: View {
    @Environment(VehicleSession.self) private var s
    @AppStorage("accent") private var accent: Accent = .cyan
    @AppStorage("appearance") private var appearance: Appearance = .system
    @Environment(UpdateChecker.self) private var updates

    var body: some View {
        TabView {
            ConnectView().tabItem { Label("Connect", systemImage: "antenna.radiowaves.left.and.right") }
            DashboardView().tabItem { Label("Live", systemImage: "gauge.with.dots.needle.67percent") }
            VehicleView().tabItem { Label("Vehicle", systemImage: "car") }
            PowerView().tabItem { Label("Power", systemImage: "bolt.horizontal.circle") }
            ReportView().tabItem { Label("Report", systemImage: "doc.text.magnifyingglass") }
            DiagnosticsView().tabItem { Label("Diagnose", systemImage: "exclamationmark.triangle") }
            FaultHistoryView().tabItem { Label("History", systemImage: "clock.arrow.circlepath") }
            LogsView().tabItem { Label("Logs", systemImage: "doc.text") }
        }
        .overlay(alignment: .top) {
            if let a = s.alert {
                Label(a, systemImage: "exclamationmark.triangle.fill")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(.white)
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .background(Color.red.gradient, in: Capsule())
                    .shadow(radius: 10)
                    .padding(.top, 6)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .onTapGesture { s.alert = nil }
            }
        }
        .animation(.spring, value: s.alert)
        .sensoryFeedback(.warning, trigger: s.alert)
        .onChange(of: s.scanner.poweredOn) { _, on in
            if on, s.state == .idle, UserDefaults.standard.bool(forKey: "autoConnect"), LastAdapter.load() != nil { s.connectLast() }
        }
        .overlay(alignment: .bottom) { UpdateBanner() }
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: updates.showBanner)
        .tint(accent.color)
        .preferredColorScheme(appearance.scheme)
    }
}

struct ConnectView: View {
    @Environment(VehicleSession.self) private var s
    @AppStorage("wifiHost") private var host = "192.168.0.10"
    @AppStorage("wifiPort") private var port = 35000
    @AppStorage("autoConnect") private var autoConnect = false
    @AppStorage("autoReconnect") private var autoReconnect = true

    var body: some View {
        NavigationStack {
            List {
                Section("Status") {
                    statusRow
                    if let last = LastAdapter.load(), s.state != .connected {
                        Button { s.connectLast() } label: {
                            Label("Connect to \(last.label)", systemImage: "bolt.horizontal.fill")
                        }
                    }
                    Toggle("Connect automatically at launch", isOn: $autoConnect)
                    Toggle("Reconnect if the link drops", isOn: $autoReconnect)
                    if s.state == .connected {
                        LabeledContent("Adapter", value: s.adapterVersion)
                        LabeledContent("Protocol", value: s.protocolName)
                        LabeledContent("Supported PIDs", value: "\(s.supported.count)")
                        Button("Disconnect", role: .destructive) { s.disconnect() }
                    }
                }
                Section {
                    if !s.scanner.poweredOn { Text("Turn on Bluetooth").foregroundStyle(.secondary) }
                    ForEach(s.scanner.devices) { d in
                        Button { s.connectBLE(d) } label: {
                            HStack {
                                Text(d.name)
                                Spacer()
                                Text("\(d.rssi) dBm").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                            }
                        }
                    }
                } header: {
                    HStack {
                        Text("Bluetooth LE")
                        Spacer()
                        Button(s.scanner.isScanning ? "Stop" : "Scan") {
                            s.scanner.isScanning ? s.scanner.stop() : s.scanner.start()
                        }.font(.caption)
                    }
                }
                Section("Wi-Fi") {
                    TextField("Host", text: $host).keyboardType(.numbersAndPunctuation).autocorrectionDisabled()
                    TextField("Port", value: $port, format: .number.grouping(.never)).keyboardType(.numberPad)
                    Button("Connect Wi-Fi") { s.connectWiFi(host: host, port: UInt16(clamping: port)) }
                }
                UpdateSettingsSection()
            }
            .navigationTitle("OBD Pro")
        }
    }

    @ViewBuilder private var statusRow: some View {
        switch s.state {
        case .idle: Label("Not connected", systemImage: "circle").foregroundStyle(.secondary)
        case .connecting(let n): HStack { ProgressView(); Text("Connecting to \(n)…") }
        case .connected: Label("Connected", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
        case .reconnecting(let n): HStack { ProgressView(); Text("Link lost — reconnecting (attempt \(n))…") }
        case .failed(let e): Label(e, systemImage: "xmark.octagon.fill").foregroundStyle(.red)
        }
    }
}
