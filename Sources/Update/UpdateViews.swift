import SwiftUI

/// Floating banner shown above the tab bar when a newer build exists.
struct UpdateBanner: View {
    @Environment(UpdateChecker.self) private var u
    @State private var showing = false

    var body: some View {
        if u.showBanner, let r = u.available {
            Button { showing = true } label: {
                HStack(spacing: 12) {
                    Image(systemName: "arrow.down.circle.fill").font(.title2).foregroundStyle(.white, .tint)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Update available").font(.subheadline.weight(.semibold))
                        Text("Build \(r.build) · tap to see what's new").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button { withAnimation { u.skippedBuild = r.build } } label: {
                        Image(systemName: "xmark").font(.caption.weight(.bold)).foregroundStyle(.secondary)
                            .padding(8).background(.quaternary, in: Circle())
                    }
                    .buttonStyle(.plain)
                }
                .padding(12)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                .shadow(color: .black.opacity(0.15), radius: 12, y: 4)
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.bottom, 56)
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .sheet(isPresented: $showing) { UpdateSheet(release: r).presentationDetents([.medium, .large]) }
        }
    }
}

struct UpdateSheet: View {
    @Environment(UpdateChecker.self) private var u
    @Environment(\.openURL) private var openURL
    @Environment(\.dismiss) private var dismiss
    let release: UpdateChecker.Release

    var body: some View {
        NavigationStack {
            List {
                Section {
                    LabeledContent("Installed", value: "\(u.currentVersion) (\(u.currentBuild))")
                    LabeledContent("Available", value: "\(release.version) (\(release.build))")
                    if let d = release.date { LabeledContent("Published", value: d.formatted(date: .abbreviated, time: .shortened)) }
                }
                if !release.notes.isEmpty {
                    Section("What's new") {
                        Text(LocalizedStringKey(release.notes)).font(.subheadline)
                    }
                }
                Section {
                    Button { openURL(UpdateChecker.altStoreInstall(release.ipa)) } label: {
                        Label("Install with AltStore", systemImage: "square.and.arrow.down.on.square")
                    }
                    Button { openURL(UpdateChecker.sideStoreInstall(release.ipa)) } label: {
                        Label("Install with SideStore", systemImage: "square.and.arrow.down.on.square")
                    }
                    Button { openURL(release.ipa) } label: {
                        Label("Download IPA (for Sideloadly)", systemImage: "arrow.down.doc")
                    }
                    Button { openURL(release.page) } label: {
                        Label("Open release on GitHub", systemImage: "safari")
                    }
                } footer: {
                    Text("Your saved layouts, measurements, codings and backups are kept when you update.")
                }
            }
            .navigationTitle("Update")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Close") { dismiss() } }
        }
    }
}

/// Section for settings screens: manual check, auto-check toggle, AltStore source.
struct UpdateSettingsSection: View {
    @Environment(UpdateChecker.self) private var u
    @Environment(\.openURL) private var openURL
    @State private var sheet: UpdateChecker.Release?

    var body: some View {
        @Bindable var u = u
        Section {
            LabeledContent("Version", value: "\(u.currentVersion) (\(u.currentBuild))")
            if u.isTestFlight {
                Label("Updates arrive through TestFlight", systemImage: "airplane")
                    .foregroundStyle(.secondary)
            } else {
            HStack {
                Button("Check for Updates") { Task { await u.check() } }
                    .disabled(u.state == .checking)
                Spacer()
                switch u.state {
                case .checking: ProgressView()
                case .upToDate: Label("Up to date", systemImage: "checkmark.circle.fill").font(.caption).foregroundStyle(.green)
                case .available(let r):
                    Button("Build \(r.build)") { sheet = r }.font(.caption.weight(.semibold)).buttonStyle(.borderedProminent)
                case .failed(let e): Text(e).font(.caption).foregroundStyle(.red).lineLimit(2)
                case .idle: EmptyView()
                }
            }
            Toggle("Check automatically", isOn: $u.autoCheck)
            Button { openURL(UpdateChecker.altStoreAddSource) } label: {
                Label("Add source to AltStore (auto-updates)", systemImage: "plus.app")
            }
            }
        } header: { Text("Updates") } footer: {
            if let l = u.lastChecked { Text("Last checked \(l.formatted(.relative(presentation: .named)))") }
        }
        .sheet(item: $sheet) { UpdateSheet(release: $0).presentationDetents([.medium, .large]) }
    }
}

extension UpdateChecker.Release: Identifiable { var id: Int { build } }
