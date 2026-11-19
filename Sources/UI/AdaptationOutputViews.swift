import SwiftUI

// MARK: - Adaptations

struct AdaptationsView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var editing: Adaptation?

    private var items: [Adaptation] { s.adaptations.filter { $0.module == module.address } }

    var body: some View {
        List {
            if items.isEmpty {
                ContentUnavailableView {
                    Label("No adaptations", systemImage: "dial.low")
                } description: {
                    Text("Add a known adaptation channel for this module.")
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
                Button { editing = Adaptation(module: module.address, did: 0, name: "") } label: { Image(systemName: "plus") }
            }
        }
        .sheet(item: $editing) { AdaptationEditor(adaptation: $0) }
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
