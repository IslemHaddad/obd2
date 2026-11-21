import SwiftUI

// MARK: - One fault row (module sheet, fault test)

struct FaultRow: View {
    @Environment(VehicleSession.self) private var s
    let fault: VAGFault
    let module: VAGModule
    var caption: String? = nil

    var body: some View {
        let e = fault.explain(in: module, family: s.family)
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(fault.code).font(.headline.monospaced())
                Spacer()
                Text(fault.state)
                    .font(.caption2.bold()).padding(.horizontal, 7).padding(.vertical, 2)
                    .background((fault.active ? module.category.color : .gray).opacity(0.25), in: Capsule())
            }
            Text(headline(e)).font(.subheadline.weight(.medium))
            Text(caption ?? e.codeLine).font(.caption).foregroundStyle(.secondary)
        }
    }

    /// In the module's own sheet the module name is redundant; show the failure itself.
    private func headline(_ e: FaultExplanation) -> String {
        if fault.powertrain, DTCDatabase.lookup(fault.dtc) != nil { return e.title }
        return fault.failureType == 0 ? "General fault" : FaultKnowledge.ftbText(fault.failureType)
    }
}

// MARK: - Full explanation of one fault

struct FaultDetailView: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.openURL) private var openURL
    let fault: VAGFault
    let module: VAGModule
    var showTestLink = true

    var body: some View {
        let e = fault.explain(in: module, family: s.family)
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text(e.title).font(.title3.weight(.semibold))
                    Text(e.codeLine).font(.subheadline.monospaced()).foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
                ForEach(e.flags, id: \.self) { f in
                    Label(f, systemImage: f.hasPrefix("Failing") ? "exclamationmark.circle.fill"
                          : f.hasPrefix("Requests") ? "lightbulb.max.fill" : "circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(f.hasPrefix("Failing") || f.hasPrefix("Requests") ? module.category.color : .secondary)
                }
            }
            Section("What it means") {
                Text(e.meaning)
                LabeledContent("Failure type", value: FaultKnowledge.ftbText(fault.failureType))
                LabeledContent("Group", value: FaultKnowledge.category(fault.failureType).name)
            }
            Section("What to check") {
                ForEach(Array(e.checks.enumerated()), id: \.offset) { i, c in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text("\(i + 1)").font(.caption.bold()).frame(width: 18, height: 18)
                            .background(.tint.opacity(0.2), in: Circle())
                        Text(c)
                    }
                }
            }
            Section {
                if showTestLink {
                    NavigationLink { FaultTestView(module: module) } label: {
                        Label("Run a Fault Test on \(module.name)", systemImage: "stethoscope")
                    }
                }
                Button {
                    var c = URLComponents(string: "https://www.google.com/search")!
                    c.queryItems = [URLQueryItem(name: "q", value: e.lookupQuery)]
                    if let u = c.url { openURL(u) }
                } label: {
                    Label("Look up the exact part for \(fault.powertrain ? fault.dtc : fault.vwNumber)", systemImage: "magnifyingglass")
                }
            } footer: {
                Text("The number is the same one VCDS, OBDeleven and dealers show, so searching it finds the exact component name.")
            }
        }
        .navigationTitle(fault.code)
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Fault Test

struct FaultTestView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var clearFirst = true
    @State private var shown: VAGFault?

    private var run: FaultTestRun? { s.faultTest?.module == module ? s.faultTest : nil }
    private var steps: [TestStep] { SystemKind.of(module).testSteps }

    var body: some View {
        List {
            if let run { runningContent(run) } else { intro }
        }
        .navigationTitle("Fault Test")
        .navigationBarTitleDisplayMode(.inline)
        .animation(.snappy, value: run?.hits.count)
        .animation(.snappy, value: run?.step)
        .sensoryFeedback(.warning, trigger: run?.hits.count ?? 0)
        .sheet(item: $shown) { f in
            NavigationStack {
                FaultDetailView(fault: f, module: module, showTestLink: false)
                    .toolbar { Button("Done") { shown = nil } }
            }
        }
        .onDisappear { s.stopFaultTest() }
    }

    @ViewBuilder private var intro: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                Label(module.name, systemImage: module.icon).font(.headline)
                Text("Many faults only show up while the part is working — like an A/C fault that appears once the A/C runs. The app watches \(module.name) live while you go through the steps, and any fault pops up the moment the module detects it, with the step that caused it.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
            Toggle(isOn: $clearFirst) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Clear stored faults first")
                    Text("Then anything that shows up is real and current.").font(.caption).foregroundStyle(.secondary)
                }
            }
            Button {
                s.startFaultTest(module, clearFirst: clearFirst)
            } label: {
                Label("Start Test", systemImage: "play.fill").frame(maxWidth: .infinity).fontWeight(.semibold)
            }
            .buttonStyle(.borderedProminent)
            .disabled(s.state != .connected)
        }
        Section("You'll be asked to") {
            ForEach(Array(steps.enumerated()), id: \.offset) { i, st in
                Label { Text(st.title) } icon: { Text("\(i + 1)").font(.caption.bold()) }
            }
        }
    }

    @ViewBuilder private func runningContent(_ r: FaultTestRun) -> some View {
        Section {
            switch r.phase {
            case .preparing:
                Label("Connecting to \(module.name)…", systemImage: "antenna.radiowaves.left.and.right")
            case .clearing:
                Label("Clearing stored faults…", systemImage: "trash")
            case .error(let e):
                Label(e, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                Button("Back") { s.faultTest = nil }
            case .watching:
                stepCard(r)
            case .finished:
                summary(r)
            }
            if let n = r.note { Text(n).font(.caption).foregroundStyle(.orange) }
        }

        if !r.hits.isEmpty {
            Section("Appeared during the test") {
                ForEach(r.hits) { h in
                    Button { shown = h.fault } label: {
                        FaultRow(fault: h.fault, module: module,
                                 caption: "At step \(h.step + 1): \(r.steps[min(h.step, r.steps.count - 1)].title) · \(h.at.formatted(date: .omitted, time: .standard))")
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        let old = r.before.filter { b in !r.hits.contains { $0.id == b.id } }
        if !old.isEmpty {
            Section("Already stored before the test") {
                ForEach(old) { f in
                    Button { shown = f } label: { FaultRow(fault: f, module: module) }.buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder private func stepCard(_ r: FaultTestRun) -> some View {
        let st = r.steps[min(r.step, r.steps.count - 1)]
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Step \(r.step + 1) of \(r.steps.count)").font(.caption.bold()).foregroundStyle(.secondary)
                Spacer()
                HStack(spacing: 5) {
                    Circle().fill(.green).frame(width: 7, height: 7)
                        .phaseAnimator([0.3, 1.0]) { c, o in c.opacity(o) } animation: { _ in .easeInOut(duration: 0.6) }
                    Text("Watching live · \(r.reads)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
            Text(st.title).font(.title2.weight(.semibold))
            if !st.detail.isEmpty { Text(st.detail).foregroundStyle(.secondary) }
            ProgressView(value: Double(r.step + 1), total: Double(r.steps.count))
            HStack {
                Button("Back") { s.faultTest?.step = max(0, r.step - 1) }
                    .buttonStyle(.bordered).disabled(r.step == 0)
                Spacer()
                if r.step + 1 < r.steps.count {
                    Button("Done — next") { s.faultTest?.step = r.step + 1 }.buttonStyle(.borderedProminent)
                } else {
                    Button("Finish") { s.stopFaultTest() }.buttonStyle(.borderedProminent)
                }
            }
        }
        .padding(.vertical, 6)
    }

    @ViewBuilder private func summary(_ r: FaultTestRun) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if r.hits.isEmpty {
                Label("No faults appeared", systemImage: "checkmark.seal.fill").font(.title3.weight(.semibold)).foregroundStyle(.green)
                Text("\(module.name) worked through every step without detecting a fault (\(r.reads) live checks).")
                    .foregroundStyle(.secondary)
            } else {
                Label("\(r.hits.count) fault\(r.hits.count == 1 ? "" : "s") appeared", systemImage: "exclamationmark.triangle.fill")
                    .font(.title3.weight(.semibold)).foregroundStyle(module.category.color)
                Text("Tap each one to see what it means and what to check.").foregroundStyle(.secondary)
            }
            Button("Test again") { s.faultTest = nil }.buttonStyle(.bordered)
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Coding: only offered when the adapter can actually do it

struct CodingGateView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var checking = false
    @State private var result: CodingAbility?

    private var known: CodingAbility? { result ?? s.codingAbility[s.codingKey(module)] }

    var body: some View {
        Group {
            if known == .yes {
                ModuleCodingView(module: module)
            } else {
                List {
                    if checking {
                        Section {
                            HStack(spacing: 12) { ProgressView(); Text("Checking if your adapter can code \(module.name)…") }
                            Text("The app reads the current coding and writes the exact same value back — nothing changes on the car.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    } else if let k = known {
                        Section {
                            Label(k.label, systemImage: "lock.fill").font(.headline).foregroundStyle(.orange)
                            Text(k.explanation)
                            if let a = s.adapterProfile { LabeledContent("Adapter", value: a.chip).font(.caption) }
                        }
                        Section { Button("Check again") { check() } }
                    }
                }
                .navigationTitle("Coding · \(module.address)")
                .task { if known == nil { check() } }
            }
        }
    }

    private func check() {
        checking = true
        Task {
            result = await s.probeCoding(module).0
            checking = false
        }
    }
}
