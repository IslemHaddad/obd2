import SwiftUI

// MARK: - Live data

struct ModuleLiveView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var editing: Measurement?

    private var defs: [Measurement] { s.measurements.filter { $0.module == module.address } }

    var body: some View {
        List {
            if defs.isEmpty {
                ContentUnavailableView {
                    Label("No live values yet", systemImage: "waveform.path.ecg")
                } description: {
                    Text("No live values are known for this module yet.")
                }
            }
            ForEach(defs) { d in
                Button { editing = d } label: {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(d.name).font(.subheadline.weight(.semibold))
                            Text("DID \(d.didHex)").font(.caption2.monospaced()).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if let h = s.vagLiveNumeric[d.id], h.count > 1 {
                            AreaSparkline(values: h, lo: h.min()!, hi: max(h.max()!, h.min()! + 1), colors: [.cyan.opacity(0.6), .cyan])
                                .frame(width: 70, height: 26)
                        }
                        Text(s.vagLive[d.id] ?? "…")
                            .font(.system(.body, design: .rounded).weight(.semibold)).monospacedDigit()
                            .contentTransition(.numericText())
                            .frame(minWidth: 80, alignment: .trailing)
                    }
                }
                .buttonStyle(.plain)
            }
            .onDelete { idx in
                let ids = idx.map { defs[$0].id }
                s.measurements.removeAll { ids.contains($0.id) }
            }
        }
        .animation(.smooth, value: s.vagLive)
        .navigationTitle("Live · \(module.address)")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { editing = Measurement(module: module.address, did: 0, name: "") } label: { Image(systemName: "plus") }
            }
        }
        .sheet(item: $editing) { MeasurementEditor(measurement: $0) }
        .onAppear { s.startVAGLive(module) }
        .onDisappear { s.stopVAGLive() }
    }
}

struct MeasurementEditor: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    @State var measurement: Measurement
    @State private var didText = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Identifier") {
                    TextField("Name", text: $measurement.name)
                    TextField("DID (hex)", text: $didText).font(.body.monospaced())
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                    Picker("Type", selection: $measurement.kind) {
                        ForEach(Measurement.Kind.allCases, id: \.self) { Text($0.rawValue.capitalized).tag($0) }
                    }.pickerStyle(.segmented)
                }
                if measurement.kind == .number {
                    Section("Decoding: value = raw × scale + offset") {
                        Stepper("Byte offset: \(measurement.offset)", value: $measurement.offset, in: 0...64)
                        Picker("Length", selection: $measurement.length) {
                            Text("1 byte").tag(1); Text("2 bytes").tag(2); Text("4 bytes").tag(4)
                        }
                        Toggle("Signed", isOn: $measurement.signed)
                        LabeledContent("Scale") { TextField("1", value: $measurement.scale, format: .number).multilineTextAlignment(.trailing).keyboardType(.decimalPad) }
                        LabeledContent("Offset") { TextField("0", value: $measurement.add, format: .number).multilineTextAlignment(.trailing).keyboardType(.numbersAndPunctuation) }
                        TextField("Unit", text: $measurement.unit)
                    }
                }
            }
            .navigationTitle(measurement.name.isEmpty ? "New Measurement" : measurement.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        guard let did = UInt16(didText, radix: 16) else { return }
                        measurement.did = did
                        if measurement.name.isEmpty { measurement.name = "DID \(measurement.didHex)" }
                        if let i = s.measurements.firstIndex(where: { $0.id == measurement.id }) { s.measurements[i] = measurement }
                        else { s.measurements.append(measurement) }
                        dismiss()
                    }
                    .disabled(UInt16(didText, radix: 16) == nil)
                }
            }
            .onAppear { didText = measurement.did == 0 ? "" : measurement.didHex }
        }
    }
}

// MARK: - Identification

struct ModuleIdentView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var rows: [(String, String)] = []
    @State private var loading = true

    var body: some View {
        List {
            if loading { ProgressView() }
            ForEach(rows, id: \.0) { k, v in
                LabeledContent(k) { Text(v).monospaced().textSelection(.enabled).multilineTextAlignment(.trailing) }
            }
        }
        .navigationTitle("Identification")
        .task { rows = await s.readIdentification(module); loading = false }
    }
}

// MARK: - Coding

struct ModuleCodingView: View {
    @Environment(VehicleSession.self) private var s
    let module: VAGModule
    @State private var original: [UInt8] = []
    @State private var coding: [UInt8] = []
    @State private var selectedByte: Int?
    @State private var hexText = ""
    @State private var busy = false
    @State private var error: String?
    @State private var confirmWrite = false
    @State private var success = false
    @State private var newRecipe = false

    private var changed: Bool { coding != original }
    private var moduleBackups: [CodingBackup] { s.backups.filter { $0.module == module.address && ($0.vin == (s.vin ?? "") || s.vin == nil) } }
    private var moduleRecipes: [CodingRecipe] { s.recipes.filter { $0.module == module.address } }

    var body: some View {
        List {
            Section {
                if coding.isEmpty {
                    if busy { ProgressView() } else { Button("Read Coding") { read() } }
                } else {
                    byteGrid
                    TextField("Hex", text: $hexText, axis: .vertical)
                        .font(.caption.monospaced()).textInputAutocapitalization(.characters).autocorrectionDisabled()
                        .onSubmit { applyHex() }
                        .onChange(of: hexText) { _, _ in applyHex() }
                }
            } header: {
                HStack { Text("Long Coding (\(coding.count) bytes)"); Spacer(); if changed { Text("Modified").foregroundStyle(.orange) } }
            }

            if let b = selectedByte, b < coding.count {
                Section("Byte \(b) — \(String(format: "%02X", coding[b]))") {
                    ForEach((0..<8).reversed(), id: \.self) { bit in
                        Toggle(isOn: Binding(
                            get: { coding[b] & (1 << bit) != 0 },
                            set: { on in coding[b] = on ? coding[b] | (1 << bit) : coding[b] & ~(1 << bit); syncHex() })) {
                            HStack {
                                Text("Bit \(bit)").monospaced()
                                if original.indices.contains(b), (original[b] ^ coding[b]) & (1 << bit) != 0 {
                                    Image(systemName: "circle.fill").font(.system(size: 6)).foregroundStyle(.orange)
                                }
                            }
                        }
                    }
                    Button("Save change as One-Tap…") { newRecipe = true }.disabled(!changed)
                }
            }

            if !moduleRecipes.isEmpty, !coding.isEmpty {
                Section("One-Tap") {
                    ForEach(moduleRecipes) { r in
                        Button {
                            if let c = r.apply(to: coding) { coding = c; syncHex() }
                        } label: {
                            HStack {
                                Text(r.name)
                                Spacer()
                                if r.isApplied(coding) { Image(systemName: "checkmark.circle.fill").foregroundStyle(.green) }
                                Text(String(format: "B%d &%02X=%02X", r.byte, r.mask, r.value)).font(.caption2.monospaced()).foregroundStyle(.secondary)
                            }
                        }
                    }
                    .onDelete { idx in let ids = idx.map { moduleRecipes[$0].id }; s.recipes.removeAll { ids.contains($0.id) } }
                }
            }

            if !moduleBackups.isEmpty {
                Section("Backups — tap to load") {
                    ForEach(moduleBackups) { b in
                        Button {
                            coding = b.coding; syncHex()
                        } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(b.date.formatted(date: .abbreviated, time: .shortened)).font(.subheadline)
                                Text(b.hex).font(.caption2.monospaced()).foregroundStyle(.secondary).lineLimit(2)
                                if !b.note.isEmpty { Text(b.note).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .navigationTitle("Coding · \(module.address)")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if changed { Button("Revert") { coding = original; syncHex() } }
                Button("Write") { confirmWrite = true }
                    .fontWeight(.semibold)
                    .disabled(!changed || busy || s.state != .connected)
            }
        }
        .confirmationDialog("Write new coding to \(module.name)?", isPresented: $confirmWrite, titleVisibility: .visible) {
            Button("Write Coding", role: .destructive) { write() }
        } message: {
            Text("Current coding is backed up first. Ignition ON, battery charged.")
        }
        .alert("Error", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
            Button("OK") { error = nil }
        } message: { Text(error ?? "") }
        .sensoryFeedback(.success, trigger: success)
        .sheet(isPresented: $newRecipe) { RecipeSheet(module: module, original: original, coding: coding) }
        .task { if coding.isEmpty { read() } }
    }

    private var byteGrid: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 6), spacing: 6) {
            ForEach(coding.indices, id: \.self) { i in
                let diff = original.indices.contains(i) && original[i] != coding[i]
                Button { withAnimation(.snappy) { selectedByte = i } } label: {
                    VStack(spacing: 1) {
                        Text(String(format: "%02X", coding[i])).font(.system(.body, design: .monospaced).weight(.semibold))
                        Text("\(i)").font(.system(size: 9)).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 42)
                    .background((selectedByte == i ? Color.accentColor : diff ? .orange : .gray).opacity(selectedByte == i ? 0.3 : 0.15),
                                in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 4)
    }

    private func syncHex() { hexText = coding.map { String(format: "%02X", $0) }.joined() }

    private func applyHex() {
        let b = ELM327.hexBytes(hexText)
        if b.count == original.count, b != coding { coding = b }
    }

    private func read() {
        busy = true
        Task {
            do { original = try await s.readCoding(module); coding = original; syncHex() }
            catch { self.error = error.localizedDescription }
            busy = false
        }
    }

    private func write() {
        busy = true
        let old = original, new = coding
        Task {
            do {
                let verified = try await s.writeCoding(module, from: old, to: new, note: "Before change")
                original = verified; coding = verified; syncHex(); success.toggle()
            } catch { self.error = error.localizedDescription }
            busy = false
        }
    }
}

struct RecipeSheet: View {
    @Environment(VehicleSession.self) private var s
    @Environment(\.dismiss) private var dismiss
    let module: VAGModule
    let original: [UInt8]
    let coding: [UInt8]
    @State private var name = ""

    /// Every changed byte becomes its own recipe entry (mask = changed bits).
    private var changes: [(Int, UInt8, UInt8)] {
        coding.indices.compactMap { i in
            guard i < original.count, original[i] != coding[i] else { return nil }
            return (i, original[i] ^ coding[i], coding[i])
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                TextField("Name (e.g. Needle sweep)", text: $name)
                Section("Changes") {
                    ForEach(changes, id: \.0) { b, m, v in
                        Text(String(format: "Byte %d  mask %02X  → %02X", b, m, v & m)).monospaced()
                    }
                }
            }
            .navigationTitle("Save One-Tap")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        for (b, m, v) in changes {
                            s.recipes.append(CodingRecipe(module: module.address,
                                                          name: changes.count > 1 ? "\(name) (B\(b))" : name,
                                                          byte: b, mask: m, value: v))
                        }
                        dismiss()
                    }
                    .disabled(name.isEmpty || changes.isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
