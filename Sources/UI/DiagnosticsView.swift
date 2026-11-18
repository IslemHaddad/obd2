import SwiftUI

struct DiagnosticsView: View {
    @Environment(VehicleSession.self) private var s
    @State private var busy = false
    enum ClearTarget: Identifiable {
        case one(ECU), faulty
        var id: String { if case .one(let e) = self { e.id } else { "faulty" } }
    }
    @State private var pendingClear: ClearTarget?
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let r = s.readiness {
                    Section("Status") {
                        Label(r.milOn ? "Check Engine light ON" : "Check Engine light OFF",
                              systemImage: "engine.combustion.fill")
                            .foregroundStyle(r.milOn ? .orange : .green)
                        LabeledContent("Confirmed DTC count", value: "\(r.dtcCount)")
                    }
                }
                if s.modules.isEmpty {
                    Section("Trouble Codes") {
                        Text(s.readiness == nil ? "Tap Scan" : "No codes").foregroundStyle(.secondary)
                    }
                }
                ForEach(s.faultyModules) { m in
                    Section {
                        ForEach(m.dtcs) { d in dtcRow(d) }
                    } header: {
                        HStack {
                            Text(m.ecu == .broadcast ? "All Modules" : m.ecu.name)
                            Spacer()
                            Button("Clear", role: .destructive) { pendingClear = .one(m.ecu) }
                                .font(.caption.bold()).disabled(busy)
                        }
                    }
                }
                let healthy = s.modules.filter { !$0.faulty }
                if !healthy.isEmpty {
                    Section("No Faults — skipped") {
                        ForEach(healthy) { m in
                            Label(m.ecu == .broadcast ? "All Modules" : m.ecu.name, systemImage: "checkmark.seal.fill")
                                .foregroundStyle(.green)
                        }
                    }
                }
                if !s.freeze.isEmpty {
                    Section("Freeze Frame") {
                        ForEach(s.freeze.keys.sorted(), id: \.self) { k in
                            if let p = PIDs.byID[k], let v = s.freeze[k] {
                                LabeledContent(p.name, value: String(format: "%.1f %@", v, p.unit))
                            }
                        }
                    }
                }
                if let r = s.readiness {
                    Section("Readiness Monitors") {
                        ForEach(r.monitors.filter(\.supported)) { m in
                            Label(m.name, systemImage: m.complete ? "checkmark.circle.fill" : "clock.fill")
                                .foregroundStyle(m.complete ? .green : .yellow)
                        }
                    }
                }
            }
            .navigationTitle("Diagnostics")
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if busy { ProgressView() }
                    Button("Clear Faulty", role: .destructive) { pendingClear = .faulty }
                        .disabled(busy || s.state != .connected || s.faultyModules.isEmpty)
                    Button("Scan") { run { await s.scanDTCs() } }.disabled(busy || s.state != .connected)
                }
            }
            .confirmationDialog(clearTitle, isPresented: Binding(get: { pendingClear != nil }, set: { if !$0 { pendingClear = nil } }), titleVisibility: .visible) {
                Button("Clear", role: .destructive) {
                    switch pendingClear {
                    case .one(let e): run { try await s.clear(e) }
                    case .faulty: run { try await s.clearFaulty() }
                    case nil: break
                    }
                }
                Button("Cancel", role: .cancel) { pendingClear = nil }
            } message: { Text("Engine OFF, ignition ON. Readiness monitors of the cleared module(s) reset.") }
            .alert("Error", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) { Button("OK") { error = nil } } message: { Text(error ?? "") }
        }
    }

    private func run(_ op: @escaping () async throws -> Void) {
        busy = true
        Task {
            do { try await op() } catch { self.error = error.localizedDescription }
            busy = false
        }
    }

    private var clearTitle: String {
        switch pendingClear {
        case .one(let e): "Clear codes in \(e == .broadcast ? "all modules" : e.name)?"
        case .faulty: "Clear \(s.faultyModules.count) faulty module(s) only?"
        case nil: ""
        }
    }

    private func dtcRow(_ d: DTC) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(d.code).font(.headline.monospaced())
                Spacer()
                Text(d.kind.rawValue).font(.caption2.bold())
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(color(d.kind).opacity(0.25), in: Capsule())
            }
            Text(d.description).font(.subheadline).foregroundStyle(.secondary)
        }
    }

    private func color(_ k: DTC.Kind) -> Color {
        switch k { case .stored: .red; case .pending: .yellow; case .permanent: .purple }
    }
}

struct InfoView: View {
    @Environment(VehicleSession.self) private var s
    var body: some View {
        NavigationStack {
            List {
                Section("Vehicle") {
                    LabeledContent("VIN", value: s.vin ?? "—").textSelection(.enabled)
                    LabeledContent("Calibration ID", value: s.calID ?? "—")
                    LabeledContent("ECU", value: s.ecuName ?? "—")
                }
                Section("Connection") {
                    LabeledContent("Adapter", value: s.adapterVersion.isEmpty ? "—" : s.adapterVersion)
                    LabeledContent("Protocol", value: s.protocolName.isEmpty ? "—" : s.protocolName)
                    LabeledContent("Battery", value: s.batteryVoltage.map { String(format: "%.2f V", $0) } ?? "—")
                }
            }
            .navigationTitle("Vehicle")
            .refreshable { await s.loadInfo() }
        }
    }
}

struct LogsView: View {
    @Environment(VehicleSession.self) private var s
    @State private var tick = 0
    var body: some View {
        NavigationStack {
            List {
                ForEach(s.logFiles, id: \.self) { url in
                    ShareLink(item: url) {
                        Label(url.lastPathComponent, systemImage: "tablecells")
                    }
                }
                .onDelete { idx in
                    let files = s.logFiles
                    idx.forEach { try? FileManager.default.removeItem(at: files[$0]) }
                    tick += 1
                }
            }
            .id(tick)
            .overlay { if s.logFiles.isEmpty { ContentUnavailableView("No logs", systemImage: "doc", description: Text("Tap ● on Live to record CSV")) } }
            .navigationTitle("Logs")
            .refreshable { tick += 1 }
        }
    }
}
