import SwiftUI

// MARK: - Adaptations

struct AdaptationsView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var editing: Adaptation?
    @State private var scanning = false

    private var items: [Adaptation] { s.adaptations.filter { $0.module == module.address } }

    var body: some View {
        List {
            if items.isEmpty {
                ContentUnavailableView {
                    Label("No adaptations", systemImage: "dial.low")
                } description: {
                    Text("Scan the module for identifiers or add a known channel.")
                } actions: {
                    Button("Scan Module") { scanning = true }.buttonStyle(.borderedProminent)
                }
            }
            ForEach(items) { a in
                NavigationLink { AdaptationDetail(adaptationID: a.id, module: module) } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(a.name).font(.subheadline.weight(.semibold))
                        Text("DID \(a.didHex) · \(a.kind.rawValue)").font(.caption2.monospaced()).foregroundStyle(.secondary)
                    }
                }
                .swipeActions(edge: .leading) { Button("Edit") { editing = a }.tint(.blue) }
            }
            .onDelete { idx in let ids = idx.map { items[$0].id }; s.adaptations.removeAll { ids.contains($0.id) } }
        }
        .navigationTitle("Adaptations · \(module.address)")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { scanning = true } label: { Image(systemName: "magnifyingglass") }
                Button { editing = Adaptation(module: module.address, did: 0, name: "") } label: { Image(systemName: "plus") }
            }
        }
        .sheet(item: $editing) { AdaptationEditor(adaptation: $0) }
        .sheet(isPresented: $scanning) {
            DIDScanner(module: module) { did, p in
                editing = Adaptation(module: module.address, did: did, name: "",
                                     kind: p.count == 1 ? .number : p.allSatisfy({ (0x20...0x7E).contains($0) }) ? .ascii : .hex,
                                     length: min(p.count, 4))
            }
        }
    }
}

struct AdaptationEditor: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    @State var adaptation: Adaptation
    @State private var didText = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Channel") {
                    TextField("Name", text: $adaptation.name)
                    TextField("DID (hex)", text: $didText).font(.body.monospaced())
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                    Picker("Type", selection: $adaptation.kind) {
                        ForEach(Adaptation.Kind.allCases, id: \.self) { Text($0.rawValue.capitalized).tag($0) }
                    }.pickerStyle(.segmented)
                    Stepper("Byte offset: \(adaptation.offset)", value: $adaptation.offset, in: 0...64)
                }
                if adaptation.kind == .number {
                    Section("value = raw × scale + offset") {
                        Picker("Length", selection: $adaptation.length) {
                            Text("1 byte").tag(1); Text("2 bytes").tag(2); Text("4 bytes").tag(4)
                        }
                        LabeledContent("Scale") { TextField("1", value: $adaptation.scale, format: .number).multilineTextAlignment(.trailing).keyboardType(.decimalPad) }
                        LabeledContent("Offset") { TextField("0", value: $adaptation.add, format: .number).multilineTextAlignment(.trailing).keyboardType(.numbersAndPunctuation) }
                        TextField("Unit", text: $adaptation.unit)
                    }
                }
            }
            .navigationTitle(adaptation.name.isEmpty ? "New Adaptation" : adaptation.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        guard let did = UInt16(didText, radix: 16) else { return }
                        adaptation.did = did
                        if adaptation.kind == .toggle { adaptation.length = 1 }
                        if adaptation.name.isEmpty { adaptation.name = "Channel \(adaptation.didHex)" }
                        if let i = s.adaptations.firstIndex(where: { $0.id == adaptation.id }) { s.adaptations[i] = adaptation }
                        else { s.adaptations.append(adaptation) }
                        dismiss()
                    }
                    .disabled(UInt16(didText, radix: 16) == nil)
                }
            }
            .onAppear { didText = adaptation.did == 0 ? "" : adaptation.didHex }
        }
    }
}

struct AdaptationDetail: View {
    @Environment(VehicleSession.self) private var s
    let adaptationID: UUID
    let module: VAGModule
    @State private var original: [UInt8] = []
    @State private var payload: [UInt8] = []
    @State private var numberText = ""
    @State private var asciiText = ""
    @State private var hexText = ""
    @State private var busy = false
    @State private var error: String?
    @State private var confirm = false
    @State private var success = false

    private var a: Adaptation? { s.adaptations.first { $0.id == adaptationID } }
    private var history: [CodingBackup] { a.map { k in s.backups.filter { $0.module == k.backupKey } } ?? [] }

    var body: some View {
        List {
            if let a {
                Section("Current") {
                    if busy && original.isEmpty { ProgressView() }
                    if !original.isEmpty {
                        LabeledContent("Raw", value: hex(original)).font(.caption.monospaced())
                        if a.kind == .number, let v = a.number(original) {
                            LabeledContent("Value", value: format(v) + " " + a.unit)
                        }
                    }
                }
                if !original.isEmpty {
                    Section("New Value") {
                        switch a.kind {
                        case .number:
                            HStack {
                                TextField("Value", text: $numberText).keyboardType(.numbersAndPunctuation)
                                    .font(.title3.monospacedDigit())
                                Text(a.unit).foregroundStyle(.secondary)
                            }
                            .onChange(of: numberText) { _, t in
                                if let v = Double(t.replacingOccurrences(of: ",", with: ".")), let p = a.patch(original, value: v) { payload = p }
                            }
                        case .toggle:
                            Toggle(a.name, isOn: Binding(
                                get: { payload.indices.contains(a.offset) && payload[a.offset] != 0 },
                                set: { on in if payload.indices.contains(a.offset) { payload[a.offset] = on ? 1 : 0 } }))
                        case .ascii:
                            TextField("Text", text: $asciiText)
                                .onChange(of: asciiText) { _, t in payload = a.patch(original, ascii: t) }
                        case .hex:
                            TextField("Hex", text: $hexText, axis: .vertical)
                                .font(.caption.monospaced()).textInputAutocapitalization(.characters).autocorrectionDisabled()
                                .onChange(of: hexText) { _, t in
                                    let b = ELM327.hexBytes(t); if b.count == original.count { payload = b }
                                }
                        }
                        if payload != original {
                            LabeledContent("Will write", value: hex(payload)).font(.caption.monospaced()).foregroundStyle(.orange)
                        }
                    }
                }
                if !history.isEmpty {
                    Section("History — tap to restore") {
                        ForEach(history) { b in
                            Button { payload = b.coding; syncFields() } label: {
                                VStack(alignment: .leading) {
                                    Text(b.date.formatted(date: .abbreviated, time: .shortened)).font(.subheadline)
                                    Text(b.hex).font(.caption2.monospaced()).foregroundStyle(.secondary)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .navigationTitle(a?.name ?? "Adaptation")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { read() } label: { Image(systemName: "arrow.clockwise") }.disabled(busy)
                Button("Write") { confirm = true }.fontWeight(.semibold)
                    .disabled(busy || payload == original || payload.isEmpty || s.state != .connected)
            }
        }
        .confirmationDialog("Write adaptation?", isPresented: $confirm, titleVisibility: .visible) {
            Button("Write", role: .destructive) { write() }
        } message: { Text("\(hex(original)) → \(hex(payload))\nPrevious value is saved to history.") }
        .alert("Error", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
            Button("OK") { error = nil }
        } message: { Text(error ?? "") }
        .sensoryFeedback(.success, trigger: success)
        .task { read() }
    }

    private func hex(_ b: [UInt8]) -> String { b.map { String(format: "%02X", $0) }.joined(separator: " ") }
    private func format(_ v: Double) -> String { v == v.rounded() ? String(format: "%.0f", v) : String(format: "%.3g", v) }

    private func syncFields() {
        guard let a else { return }
        if a.kind == .number, let v = a.number(payload) { numberText = format(v) }
        if a.kind == .ascii { asciiText = String(decoding: payload.dropFirst(a.offset).filter { (0x20...0x7E).contains($0) }, as: UTF8.self) }
        hexText = payload.map { String(format: "%02X", $0) }.joined()
    }

    private func read() {
        guard let a else { return }
        busy = true
        Task {
            do { original = try await s.readAdaptation(a, module); payload = original; syncFields() }
            catch { self.error = error.localizedDescription }
            busy = false
        }
    }

    private func write() {
        guard let a else { return }
        busy = true
        let old = original, new = payload
        Task {
            do {
                original = try await s.writeAdaptation(a, module, old: old, new: new)
                payload = original; syncFields(); success.toggle()
            } catch { self.error = error.localizedDescription }
            busy = false
        }
    }
}

// MARK: - Output tests

struct OutputTestsView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var editing: OutputTest?

    private var tests: [OutputTest] { s.outputTests.filter { $0.module == module.address } }

    var body: some View {
        List {
            if tests.isEmpty {
                ContentUnavailableView {
                    Label("No output tests", systemImage: "play.circle")
                } description: {
                    Text("Add an I/O control identifier or routine for this module.")
                } actions: {
                    Button("Add Test") { editing = OutputTest(module: module.address, name: "", identifier: 0) }
                        .buttonStyle(.borderedProminent)
                }
            }
            if let e = s.testError {
                Label(e, systemImage: "xmark.octagon.fill").foregroundStyle(.red).font(.subheadline)
            }
            ForEach(tests) { t in
                OutputTestRow(test: t, module: module)
                    .swipeActions(edge: .leading) { Button("Edit") { editing = t }.tint(.blue) }
            }
            .onDelete { idx in let ids = idx.map { tests[$0].id }; s.outputTests.removeAll { ids.contains($0.id) } }
        }
        .navigationTitle("Output Tests · \(module.address)")
        .toolbar {
            Button { editing = OutputTest(module: module.address, name: "", identifier: 0) } label: { Image(systemName: "plus") }
                .disabled(s.activeTest != nil)
        }
        .sheet(item: $editing) { OutputTestEditor(test: $0) }
        .onDisappear { s.stopOutputTest() }
    }
}

struct OutputTestRow: View {
    @Environment(VehicleSession.self) private var s
    let test: OutputTest
    let module: VAGModule

    private var mine: Bool { s.activeTest == test.id }

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                if mine, case .running = s.testState {
                    Circle().fill(Color.yellow.opacity(0.25)).frame(width: 44, height: 44)
                        .phaseAnimator([1.0, 1.3]) { v, k in v.scaleEffect(k) } animation: { _ in .easeInOut(duration: 0.6) }
                }
                Image(systemName: mine ? "bolt.fill" : "bolt")
                    .font(.title3).foregroundStyle(mine ? .yellow : .secondary)
            }
            .frame(width: 44, height: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(test.name).font(.subheadline.weight(.semibold))
                Text("\(test.method == .ioControl ? "2F" : "31") \(test.idHex) \(test.dataHex)")
                    .font(.caption2.monospaced()).foregroundStyle(.secondary)
                if mine { statusText.font(.caption).foregroundStyle(.yellow) }
            }
            Spacer()
            if mine {
                Button("Stop") { s.stopOutputTest() }
                    .buttonStyle(.borderedProminent).tint(.red)
                    .disabled(s.testState == .stopping)
            } else {
                Button("Start") { s.startOutputTest(test, module) }
                    .buttonStyle(.bordered)
                    .disabled(s.activeTest != nil || s.state != .connected)
            }
        }
        .sensoryFeedback(.impact(weight: .heavy), trigger: mine)
    }

    @ViewBuilder private var statusText: some View {
        switch s.testState {
        case .starting: Text("Starting…")
        case .running(let r, let resp): Text(String(format: "Running · %.0fs left · %@", max(r, 0), resp))
        case .stopping: Text("Stopping…")
        case nil: EmptyView()
        }
    }
}

struct OutputTestEditor: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    @State var test: OutputTest
    @State private var idText = ""
    @State private var dataText = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Test") {
                    TextField("Name (e.g. Radiator fan)", text: $test.name)
                    Picker("Method", selection: $test.method) {
                        ForEach(OutputTest.Method.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }
                    TextField(test.method == .ioControl ? "DID (hex)" : "Routine ID (hex)", text: $idText)
                        .font(.body.monospaced()).textInputAutocapitalization(.characters).autocorrectionDisabled()
                    TextField("Control data (hex, optional)", text: $dataText)
                        .font(.body.monospaced()).textInputAutocapitalization(.characters).autocorrectionDisabled()
                }
                Section("Auto-stop") {
                    Stepper(String(format: "%.0f seconds", test.duration), value: $test.duration, in: 1...120, step: 1)
                }
                Section("Commands") {
                    LabeledContent("Start", value: preview.startCommand).font(.caption.monospaced())
                    LabeledContent("Stop", value: preview.stopCommand).font(.caption.monospaced())
                }
            }
            .navigationTitle(test.name.isEmpty ? "New Output Test" : test.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let t = preview
                        if let i = s.outputTests.firstIndex(where: { $0.id == t.id }) { s.outputTests[i] = t }
                        else { s.outputTests.append(t) }
                        dismiss()
                    }
                    .disabled(UInt16(idText, radix: 16) == nil || test.name.isEmpty)
                }
            }
            .onAppear {
                idText = test.identifier == 0 ? "" : test.idHex
                dataText = test.dataHex
            }
        }
    }

    private var preview: OutputTest {
        var t = test
        t.identifier = UInt16(idText, radix: 16) ?? 0
        t.data = ELM327.hexBytes(dataText)
        return t
    }
}
