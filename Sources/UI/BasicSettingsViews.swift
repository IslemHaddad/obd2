import SwiftUI

struct BasicSettingsView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var editing: BasicSetting?
    @State private var running: BasicSetting?

    private var items: [BasicSetting] { s.basicSettings.filter { $0.module == module.address } }

    var body: some View {
        List {
            if items.isEmpty {
                ContentUnavailableView {
                    Label("No basic settings", systemImage: "gearshape.arrow.triangle.2.circlepath")
                } description: {
                    Text("Add a routine (31 xx xx) for this module, e.g. throttle body adaptation.")
                } actions: {
                    Button("Add Basic Setting") { editing = BasicSetting(module: module.address, name: "", routine: 0) }
                        .buttonStyle(.borderedProminent)
                }
            }
            ForEach(items) { b in
                Button { running = b } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "gearshape.2.fill").foregroundStyle(.tint)
                            .frame(width: 36, height: 36)
                            .background(Color.accentColor.opacity(0.15), in: RoundedRectangle(cornerRadius: 9))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(b.name).font(.subheadline.weight(.semibold))
                            Text("Routine \(b.ridHex)\(b.startHex.isEmpty ? "" : " · \(b.startHex)")")
                                .font(.caption2.monospaced()).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "play.fill").foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.plain)
                .swipeActions(edge: .leading) { Button("Edit") { editing = b }.tint(.blue) }
            }
            .onDelete { idx in let ids = idx.map { items[$0].id }; s.basicSettings.removeAll { ids.contains($0.id) } }
        }
        .navigationTitle("Basic Settings · \(module.address)")
        .toolbar {
            Button { editing = BasicSetting(module: module.address, name: "", routine: 0) } label: { Image(systemName: "plus") }
        }
        .sheet(item: $editing) { BasicSettingEditor(setting: $0) }
        .fullScreenCover(item: $running) { BasicSettingRunner(settingID: $0.id, module: module) }
    }
}

// MARK: - Runner

struct BasicSettingRunner: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    let settingID: UUID
    let module: VAGModule

    private var b: BasicSetting? { s.basicSettings.first { $0.id == settingID } }
    private var run: VehicleSession.BasicRun? { s.basicRun?.setting == settingID ? s.basicRun : nil }
    private var active: Bool { run.map { !$0.finished } ?? false }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    statusRing.frame(width: 220, height: 220).padding(.top, 20)
                    phaseLabel
                    if let b, !b.conditions.isEmpty, !active {
                        Label(b.conditions, systemImage: "checklist")
                            .font(.subheadline)
                            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                            .background(.yellow.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    if let r = run, !r.result.isEmpty {
                        card("Routine Result") { Text(r.result).font(.callout.monospaced()).textSelection(.enabled) }
                    }
                    if let b, !b.watch.isEmpty {
                        card("Live Values") {
                            ForEach(s.measurements.filter { b.watch.contains($0.id) }) { m in
                                HStack {
                                    Text(m.name).foregroundStyle(.secondary)
                                    Spacer()
                                    Text(run?.watch[m.id] ?? "—").monospacedDigit().fontWeight(.semibold)
                                        .contentTransition(.numericText())
                                }
                                .font(.subheadline)
                            }
                        }
                    }
                }
                .padding(.horizontal, 20)
                .animation(.smooth, value: run)
            }
            .safeAreaInset(edge: .bottom) { controls.padding(20).background(.bar) }
            .navigationTitle(b?.name ?? "Basic Setting")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }.disabled(active)
                }
            }
            .interactiveDismissDisabled(active)
            .sensoryFeedback(trigger: run?.phase) { _, new in
                switch new {
                case .done: .success
                case .failed, .error, .timedOut: .error
                case .running: .impact(weight: .medium)
                default: nil
                }
            }
        }
    }

    private var progress: Double {
        guard let r = run, let b else { return 0 }
        if r.phase == .done { return 1 }
        return min(r.elapsed / max(b.timeout, 1), 1)
    }

    private var tint: Color {
        switch run?.phase {
        case .done: .green
        case .failed, .error, .timedOut: .red
        case .stopped: .gray
        default: .accentColor
        }
    }

    private var statusRing: some View {
        ZStack {
            Circle().stroke(tint.opacity(0.15), lineWidth: 16)
            Circle().trim(from: 0, to: progress)
                .stroke(AngularGradient(colors: [tint.opacity(0.5), tint], center: .center),
                        style: StrokeStyle(lineWidth: 16, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .shadow(color: tint.opacity(0.6), radius: 10)
            if active, run?.phase == .running {
                Circle().stroke(tint.opacity(0.4), lineWidth: 2)
                    .phaseAnimator([false, true]) { v, on in v.scaleEffect(on ? 1.12 : 0.95).opacity(on ? 0 : 1) }
                        animation: { _ in .easeOut(duration: 1.4) }
            }
            VStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 40, weight: .semibold)).foregroundStyle(tint)
                    .symbolEffect(.pulse, isActive: run?.phase == .running)
                if let r = run, r.elapsed > 0 {
                    Text(String(format: "%.0fs", r.elapsed)).font(.title3.monospacedDigit().weight(.semibold))
                        .contentTransition(.numericText())
                }
            }
        }
    }

    private var icon: String {
        switch run?.phase {
        case .done: "checkmark"
        case .failed, .error: "xmark"
        case .timedOut: "clock.badge.exclamationmark"
        case .stopped: "stop.fill"
        case .running, .starting, .stopping: "gearshape.2.fill"
        case nil: "play.fill"
        }
    }

    @ViewBuilder private var phaseLabel: some View {
        let text: String = switch run?.phase {
        case nil: "Ready"
        case .starting: "Starting routine…"
        case .running: "Running — keep conditions stable"
        case .stopping: "Stopping…"
        case .done: "Completed successfully"
        case .failed: "Routine reported failure"
        case .stopped: "Stopped"
        case .timedOut: "Timed out"
        case .error(let e): e
        }
        Text(text).font(.headline).foregroundStyle(tint).multilineTextAlignment(.center)
    }

    private var controls: some View {
        Group {
            if active {
                Button(role: .destructive) { s.stopBasicSetting() } label: {
                    Label("Stop", systemImage: "stop.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).tint(.red)
                .disabled(run?.phase == .stopping)
            } else {
                Button { if let b { s.startBasicSetting(b, module) } } label: {
                    Label(run == nil ? "Start" : "Run Again", systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(s.state != .connected || s.activeTest != nil)
            }
        }
        .controlSize(.large)
    }

    private func card<C: View>(_ title: String, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary).textCase(.uppercase)
            c()
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

// MARK: - Editor

struct BasicSettingEditor: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    @State var setting: BasicSetting
    @State private var ridText = ""
    @State private var dataText = ""
    @State private var useDone = false
    @State private var useFail = false
    @State private var doneText = "00"
    @State private var failText = "FF"

    private var moduleMeasurements: [Measurement] { s.measurements.filter { $0.module == setting.module } }

    var body: some View {
        NavigationStack {
            Form {
                Section("Routine") {
                    TextField("Name (e.g. Throttle body adaptation)", text: $setting.name)
                    TextField("Routine ID (hex)", text: $ridText).font(.body.monospaced())
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                    TextField("Start data (hex, optional)", text: $dataText).font(.body.monospaced())
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                    Stepper(String(format: "Timeout: %.0f s", setting.timeout), value: $setting.timeout, in: 5...600, step: 5)
                }
                Section("Conditions shown before start") {
                    TextField("e.g. Engine off, ignition on, pedal released", text: $setting.conditions, axis: .vertical)
                }
                Section {
                    Toggle("Detect completion", isOn: $useDone)
                    if useDone {
                        Stepper("Result byte: \(setting.doneOffset ?? 0)", value: Binding(
                            get: { setting.doneOffset ?? 0 }, set: { setting.doneOffset = $0 }), in: 0...32)
                        LabeledContent("Done when =") { TextField("00", text: $doneText).font(.body.monospaced()).multilineTextAlignment(.trailing) }
                        Toggle("Failure value", isOn: $useFail)
                        if useFail {
                            LabeledContent("Failed when =") { TextField("FF", text: $failText).font(.body.monospaced()).multilineTextAlignment(.trailing) }
                        }
                    }
                } header: { Text("Result (31 03)") } footer: {
                    Text("Without completion detection the routine runs until you stop it or it times out.")
                }
                if !moduleMeasurements.isEmpty {
                    Section("Watch live values") {
                        ForEach(moduleMeasurements) { m in
                            Toggle(m.name, isOn: Binding(
                                get: { setting.watch.contains(m.id) },
                                set: { on in if on { setting.watch.append(m.id) } else { setting.watch.removeAll { $0 == m.id } } }))
                        }
                    }
                }
                Section("Commands") {
                    LabeledContent("Start", value: "3101\(ridPreview)\(dataText.uppercased())").font(.caption.monospaced())
                    LabeledContent("Results", value: "3103\(ridPreview)").font(.caption.monospaced())
                    LabeledContent("Stop", value: "3102\(ridPreview)").font(.caption.monospaced())
                }
            }
            .navigationTitle(setting.name.isEmpty ? "New Basic Setting" : setting.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }.disabled(UInt16(ridText, radix: 16) == nil || setting.name.isEmpty)
                }
            }
            .onAppear {
                ridText = setting.routine == 0 ? "" : setting.ridHex
                dataText = setting.startHex
                useDone = setting.doneOffset != nil
                doneText = String(format: "%02X", setting.doneValue)
                useFail = setting.failValue != nil
                if let f = setting.failValue { failText = String(format: "%02X", f) }
            }
        }
    }

    private var ridPreview: String { UInt16(ridText, radix: 16).map { String(format: "%04X", $0) } ?? "????" }

    private func save() {
        guard let rid = UInt16(ridText, radix: 16) else { return }
        setting.routine = rid
        setting.startData = ELM327.hexBytes(dataText)
        if useDone {
            setting.doneOffset = setting.doneOffset ?? 0
            setting.doneValue = UInt8(doneText, radix: 16) ?? 0
            setting.failValue = useFail ? UInt8(failText, radix: 16) : nil
        } else {
            setting.doneOffset = nil
            setting.failValue = nil
        }
        if let i = s.basicSettings.firstIndex(where: { $0.id == setting.id }) { s.basicSettings[i] = setting }
        else { s.basicSettings.append(setting) }
        dismiss()
    }
}
