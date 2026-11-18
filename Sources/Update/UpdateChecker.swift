import Foundation
import Observation

/// Checks GitHub Releases of this repo for a newer CI build.
@MainActor
@Observable
final class UpdateChecker {
    static let repo = "IslemHaddad/obd2"
    static let altStoreSource = URL(string: "https://github.com/\(repo)/releases/latest/download/altstore-source.json")!

    struct Release: Equatable {
        let build: Int
        let version: String
        let notes: String
        let ipa: URL
        let page: URL
        let date: Date?
    }

    enum State: Equatable { case idle, checking, upToDate, available(Release), failed(String) }

    var state: State = .idle
    var lastChecked: Date? = UserDefaults.standard.object(forKey: "update.lastChecked") as? Date
    var autoCheck: Bool = UserDefaults.standard.object(forKey: "update.auto") as? Bool ?? true {
        didSet { UserDefaults.standard.set(autoCheck, forKey: "update.auto") }
    }
    /// Build the user chose to skip (banner stays hidden for it).
    var skippedBuild: Int = UserDefaults.standard.integer(forKey: "update.skipped") {
        didSet { UserDefaults.standard.set(skippedBuild, forKey: "update.skipped") }
    }

    let currentBuild = Int(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "0") ?? 0
    let currentVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"

    /// Installed from TestFlight → TestFlight handles updates.
    let isTestFlight = Bundle.main.appStoreReceiptURL?.lastPathComponent == "sandboxReceipt"

    var available: Release? { if case .available(let r) = state { r } else { nil } }
    var showBanner: Bool { !isTestFlight && (available.map { $0.build != skippedBuild } ?? false) }

    func checkOnLaunch() async {
        guard autoCheck, !isTestFlight else { return }
        if let l = lastChecked, Date().timeIntervalSince(l) < 3600 { return }   // at most hourly
        await check()
    }

    func check() async {
        state = .checking
        do {
            var req = URLRequest(url: URL(string: "https://api.github.com/repos/\(Self.repo)/releases/latest")!)
            req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
            req.timeoutInterval = 15
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                state = .failed("GitHub returned \((resp as? HTTPURLResponse)?.statusCode ?? 0)")
                return
            }
            let r = try JSONDecoder().decode(GHRelease.self, from: data)
            lastChecked = Date()
            UserDefaults.standard.set(lastChecked, forKey: "update.lastChecked")
            guard let build = Int(r.tag_name.filter(\.isNumber)),
                  let ipa = r.assets.first(where: { $0.name.hasSuffix(".ipa") })?.browser_download_url else {
                state = .failed("Latest release has no IPA")
                return
            }
            let rel = Release(build: build, version: r.name ?? r.tag_name, notes: r.body ?? "",
                              ipa: ipa, page: r.html_url,
                              date: r.published_at.flatMap { ISO8601DateFormatter().date(from: $0) })
            state = build > currentBuild ? .available(rel) : .upToDate
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    // Install hand-off URLs
    static func altStoreInstall(_ ipa: URL) -> URL { URL(string: "altstore://install?url=\(encode(ipa))")! }
    static func sideStoreInstall(_ ipa: URL) -> URL { URL(string: "sidestore://install?url=\(encode(ipa))")! }
    static var altStoreAddSource: URL { URL(string: "altstore://source?url=\(encode(altStoreSource))")! }

    private static func encode(_ u: URL) -> String {
        u.absoluteString.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? u.absoluteString
    }

    private struct GHRelease: Decodable {
        let tag_name: String
        let name: String?
        let body: String?
        let html_url: URL
        let published_at: String?
        let assets: [Asset]
        struct Asset: Decodable { let name: String; let browser_download_url: URL }
    }
}
