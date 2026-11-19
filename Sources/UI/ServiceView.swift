import SwiftUI

/// Built-in guided VAG service functions for one module. Each shows the exact UDS preview and
/// requires confirmation before anything is sent; routine functions run on the BasicSetting engine.
struct ServiceView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var selected: ServiceFn?

    private var fns: [ServiceFn] { ServiceFn.functions(for: module.address, family: s.family, fuel: s.fuel) }
    private var groups: [String] {
        var seen = Set<String>(), order = [String]()
        for g in fns.map(\.group) where seen.insert(g).inserted { order.append(g) }
        return order
    }

    var body: some View {
        List {
            Section {
                Text("Guided service functions. Each previews the exact commands and asks you to confirm before anything is sent to the car.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(groups, id: \.self) { g in
                Section(g) {
                    ForEach(fns.filter { $0.group == g }) { f in
                        Button { selected = f } label: {
                            HStack(spacing: 12) {
                                Image(systemName: icon(f)).foregroundStyle(.tint)
                                    .frame(width: 34, height: 34)
                                    .background(Color.accentColor.opacity(0.15), in: RoundedRectangle(cornerRadius: 9))
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(f.name).font(.subheadline.weight(.semibold))
                                    Text(f.summary).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                                }
                                Spacer()
                                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .navigationTitle("Service · \(module.address)")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $selected) { ServiceDetail(fn: $0, module: module) }
    }

    private func icon(_ f: ServiceFn) -> String {
        switch f.group {
        case "Engine": "engine.combustion"
        case "Brakes": "car.side.rear.and.exclamationmark.and.car.side.front"
        case "Steering": "steeringwheel"
        case "Battery": "minus.plus.batteryblock"
        case "Security": "key.horizontal"
        case "Service": "wrench.and.screwdriver"
        default: "gearshape.2"
        }
    }
}

private struct ServiceDetail: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    let fn: ServiceFn
    let module: VAGModule
    @State private var runID: UUID?
    @State private var showConfirm = false

    private var run: VehicleSession.BasicRun? { s.basicRun?.setting == runID ? s.basicRun : nil }
    private var active: Bool { run.map { !$0.finished } ?? false }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(fn.summary).font(.callout)

                    card("Needs", "checklist") {
                        Text(fn.engineLabel.capitalized).font(.subheadline.weight(.semibold))
                        ForEach(fn.preconditions, id: \.self) { p in
                            Label(p, systemImage: "circle.fill").font(.subheadline)
                                .labelStyle(BulletStyle())
                        }
                    }
                    card("Steps", "list.number") {
                        ForEach(Array(fn.steps.enumerated()), id: \.offset) { i, st in
                            HStack(alignment: .top, spacing: 8) {
                                Text("\(i + 1).").font(.subheadline.monospacedDigit().weight(.semibold)).foregroundStyle(.tint)
                                Text(st).font(.subheadline)
                            }
                        }
                    }
                    if !fn.caution.isEmpty {
                        Label(fn.caution, systemImage: "exclamationmark.triangle.fill")
                            .font(.subheadline).foregroundStyle(.orange)
                            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                            .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
                    }
                    card("Will send", "terminal") {
                        Text(fn.preview).font(.caption.monospaced()).textSelection(.enabled)
                    }
                    if fn.confidence == "template" {
                        Label("The routine ID is a common default — verify it fits your exact car before running.",
                              systemImage: "info.circle")
                            .font(.caption).foregroundStyle(.secondary)
                    }

                    if let r = run {
                        card("Status", "waveform.path.ecg") {
                            Text(phaseText(r.phase)).font(.headline).foregroundStyle(tint(r.phase))
                            if !r.result.isEmpty {
                                Text("Result: \(r.result)").font(.caption.monospaced()).textSelection(.enabled)
                            }
                        }
                    }
                }
                .padding(20)
            }
            .safeAreaInset(edge: .bottom) { controls.padding(20).background(.bar) }
            .navigationTitle(fn.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(active) } }
            .interactiveDismissDisabled(active)
            .confirmationDialog("Run \(fn.name) on the car?", isPresented: $showConfirm, titleVisibility: .visible) {
                Button("Run on car", role: .destructive) { start() }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Conditions: \(fn.preconditions.joined(separator: " · ")).\n\nWill send:\n\(fn.preview)")
            }
        }
    }

    @ViewBuilder private var controls: some View {
        switch fn.kind {
        case .routine:
            if active {
                Button(role: .destructive) { s.stopBasicSetting() } label: {
                    Label("Stop", systemImage: "stop.fill").frame(maxWidth: .infinity)
                }.buttonStyle(.borderedProminent).tint(.red).controlSize(.large)
            } else {
                Button { showConfirm = true } label: {
                    Label(run == nil ? "Run on Car" : "Run Again", systemImage: "play.fill").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .disabled(s.state != .connected || s.activeTest != nil)
            }
        case .adaptation:
            Label("Open the Adaptations tab to enter and write the value.", systemImage: "dial.low")
                .font(.footnote).foregroundStyle(.secondary).frame(maxWidth: .infinity)
        case .procedure:
            Label("Follow the steps above — no automatic command is sent.", systemImage: "hand.point.up.left")
                .font(.footnote).foregroundStyle(.secondary).frame(maxWidth: .infinity)
        }
    }

    private func start() {
        let b = fn.asBasicSetting(moduleAddress: module.address)
        runID = b.id
        s.startBasicSetting(b, module)
    }

    private func tint(_ p: VehicleSession.BasicRun.Phase) -> Color {
        switch p { case .done: .green; case .failed, .error, .timedOut: .red; case .stopped: .gray; default: .accentColor }
    }
    private func phaseText(_ p: VehicleSession.BasicRun.Phase) -> String {
        switch p {
        case .starting: "Starting…"; case .running: "Running — keep conditions stable"; case .stopping: "Stopping…"
        case .done: "Completed successfully"; case .failed: "Reported failure"; case .stopped: "Stopped"
        case .timedOut: "Timed out"; case .error(let e): e
        }
    }

    private func card<C: View>(_ title: String, _ sym: String, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: sym).font(.caption.weight(.semibold)).foregroundStyle(.secondary).textCase(.uppercase)
            c()
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

private struct BulletStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "circle.fill").font(.system(size: 5)).foregroundStyle(.tint).padding(.top, 6)
            configuration.title
        }
    }
}
