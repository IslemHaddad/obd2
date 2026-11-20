import SwiftUI

/// Online photo + description for the selected car, its engine and platform, plus a VIN spec sheet.
struct CarInfoView: View {
    @Environment(VehicleSession.self) private var s
    @State private var info: CarInfo?
    @State private var loading = true
    @State private var failed = false

    var body: some View {
        ScrollView {
            if loading {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Fetching online data…").font(.subheadline).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity).padding(.top, 80)
            } else if let info, info.ok {
                VStack(alignment: .leading, spacing: 20) {
                    mediaBlock(info.car, fallback: info.title)
                    if !info.specs.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Specifications (from VIN)").font(.title3.bold())
                            VStack(spacing: 0) {
                                ForEach(info.specs) { sp in
                                    LabeledContent(sp.label, value: sp.value)
                                        .padding(.vertical, 6)
                                    Divider()
                                }
                            }
                            .padding(.horizontal, 14)
                            .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
                        }
                    }
                    mediaBlock(info.engine, fallback: "Engine")
                    mediaBlock(info.platform, fallback: "Platform")
                    Text("Photos & descriptions: Wikipedia. Spec sheet: NHTSA vPIC. Fetched live.")
                        .font(.caption2).foregroundStyle(.tertiary)
                }
                .padding()
            } else {
                ContentUnavailableView(failed ? "Couldn’t reach the internet" : "No online data",
                    systemImage: failed ? "wifi.slash" : "magnifyingglass",
                    description: Text(failed ? "Connect to the internet and try again."
                                             : "No online info found for this car."))
                    .padding(.top, 60)
            }
        }
        .navigationTitle("Car Info")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    @ViewBuilder private func mediaBlock(_ m: WikiMedia, fallback: String) -> some View {
        if m.ok {
            VStack(alignment: .leading, spacing: 10) {
                Text(m.title.isEmpty ? fallback : m.title).font(.title3.bold())
                if let url = m.imageURL {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let img): img.resizable().scaledToFit()
                        case .failure: EmptyView()
                        default: ProgressView().frame(maxWidth: .infinity, minHeight: 120)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                }
                if !m.summary.isEmpty {
                    Text(m.summary).font(.subheadline).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func load() async {
        let brand = s.vehicle?.brand.rawValue ?? ""
        let model = s.vehicle?.model.name ?? ""
        let systemName = s.vagReports.first { $0.module.address == "01" }?.systemName ?? ""
        let result = await OnlineInfo.fetch(brand: brand, model: model, vin: s.vin ?? "",
                                            fuel: s.fuel, systemName: systemName, isVAG: s.family == .vag)
        info = result
        failed = !result.ok
        loading = false
    }
}
