import Foundation

/// Best-effort online enrichment for any VAG (and generic) car.
///
/// When the phone has internet, fetch a photo + short description for the car, its engine family and
/// its platform from Wikipedia (keyless), plus a structured spec sheet from the public NHTSA VIN
/// decoder when the VIN is one it knows (mostly US-market cars; European VAG VINs usually aren't).
///
/// Privacy: only the make/model and the detected engine string go to Wikipedia. The VIN is sent ONLY
/// to the NHTSA government decoder. Every call has a short timeout and fails silently, so the app
/// works identically offline.
struct WikiMedia: Equatable {
    var title = ""
    var imageURL: URL?
    var summary = ""
    var ok: Bool { imageURL != nil || !summary.isEmpty }
}

struct CarInfo {
    struct Spec: Identifiable { let id = UUID(); let label: String; let value: String }
    var title = ""
    var specs: [Spec] = []
    var car = WikiMedia()
    var engine = WikiMedia()
    var platform = WikiMedia()
    var ok: Bool { car.ok || engine.ok || !specs.isEmpty }
}

enum OnlineInfo {
    private static let ua = "OBDPro/1.0 (OBD2 diagnostic app)"
    private static let timeout: TimeInterval = 8

    private static func getJSON(_ url: URL) async -> Any? {
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.setValue(ua, forHTTPHeaderField: "User-Agent")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            return try JSONSerialization.jsonObject(with: data)
        } catch { return nil }
    }

    // MARK: - Wikipedia (fuzzy article match → thumbnail + intro, keyless)
    static func wikiSearch(_ query: String) async -> WikiMedia? {
        var c = URLComponents(string: "https://en.wikipedia.org/w/api.php")!
        c.queryItems = [
            .init(name: "action", value: "query"), .init(name: "format", value: "json"),
            .init(name: "redirects", value: "1"),
            .init(name: "generator", value: "search"), .init(name: "gsrsearch", value: query),
            .init(name: "gsrlimit", value: "1"),
            .init(name: "prop", value: "pageimages|extracts"),
            .init(name: "piprop", value: "thumbnail"), .init(name: "pithumbsize", value: "640"),
            .init(name: "exintro", value: "1"), .init(name: "explaintext", value: "1"),
            .init(name: "exsentences", value: "3"),
        ]
        guard let url = c.url, let json = await getJSON(url) as? [String: Any],
              let q = json["query"] as? [String: Any],
              let pages = q["pages"] as? [String: Any],
              let first = pages.values.first as? [String: Any] else { return nil }
        var m = WikiMedia()
        m.title = first["title"] as? String ?? ""
        if let thumb = first["thumbnail"] as? [String: Any], let src = thumb["source"] as? String {
            m.imageURL = URL(string: src)
        }
        m.summary = (first["extract"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return m.ok ? m : nil
    }

    static func wikiFirst(_ queries: [String]) async -> WikiMedia {
        for q in queries where !q.trimmingCharacters(in: .whitespaces).isEmpty {
            if let m = await wikiSearch(q), m.ok { return m }
        }
        return WikiMedia()
    }

    // MARK: - NHTSA VIN decode (best effort; mainly US-market cars)
    private static let nhtsaFields: [(String, String)] = [
        ("Make", "Make"), ("Model", "Model"), ("ModelYear", "Year"), ("Trim", "Trim"), ("Series", "Series"),
        ("BodyClass", "Body"), ("DriveType", "Drive"), ("Doors", "Doors"),
        ("EngineModel", "Engine"), ("DisplacementL", "Displacement (L)"), ("EngineCylinders", "Cylinders"),
        ("EngineHP", "Power (hp)"), ("FuelTypePrimary", "Fuel"), ("TransmissionStyle", "Transmission"),
        ("PlantCountry", "Built in"), ("Manufacturer", "Manufacturer"),
    ]

    static func nhtsaSpecs(_ vin: String) async -> [CarInfo.Spec] {
        guard vin.count >= 11,
              let url = URL(string: "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/\(vin)?format=json"),
              let json = await getJSON(url) as? [String: Any],
              let results = json["Results"] as? [[String: Any]], let row = results.first else { return [] }
        var out: [CarInfo.Spec] = []
        for (key, label) in nhtsaFields {
            let v = (row[key] as? String ?? "").trimmingCharacters(in: .whitespaces)
            if !v.isEmpty, !["Not Applicable", "0", "None"].contains(v) {
                out.append(.init(label: label, value: v))
            }
        }
        return out
    }

    // MARK: - engine family guess (prefer a clean family article with a real engine photo)
    private static func displacement(_ s: String) -> Double {
        let lower = s.lowercased()
        guard let r = lower.range(of: #"\d\.\d"#, options: .regularExpression) else { return 0 }
        return Double(String(lower[r])) ?? 0
    }

    private static func engineQueries(brand: String, systemName: String, fuel: String) -> [String] {
        let up = systemName.uppercased()
        let disp = displacement(systemName)
        var q: [String]
        if up.contains("TDI") || fuel == "diesel" {
            q = ["List of Volkswagen Group diesel engines"]
        } else if disp >= 1.8 || ["1.8", "2.0", "TFSI"].contains(where: { up.contains($0) }) {
            q = ["Volkswagen EA888 engine", "Volkswagen EA211 engine", "List of Volkswagen Group petrol engines"]
        } else {
            q = ["Volkswagen EA211 engine", "Volkswagen EA888 engine", "List of Volkswagen Group petrol engines"]
        }
        if !systemName.isEmpty { q += ["\(brand) \(systemName) engine", "\(systemName) engine"] }
        return q
    }

    // MARK: - main entry
    static func fetch(brand: String, model: String, vin: String, fuel: String,
                      systemName: String, isVAG: Bool) async -> CarInfo {
        var info = CarInfo()
        info.title = "\(brand) \(model)".trimmingCharacters(in: .whitespaces)

        info.specs = await nhtsaSpecs(vin)

        if !brand.isEmpty || !model.isEmpty {
            info.car = await wikiFirst(["\(brand) \(model)", model, brand])
            if !info.car.title.isEmpty { info.title = info.car.title }
        }
        if isVAG {
            info.engine = await wikiFirst(engineQueries(brand: brand, systemName: systemName, fuel: fuel))
            info.platform = await wikiFirst(["Volkswagen Group MQB platform"])
        } else if !systemName.isEmpty {
            info.engine = await wikiFirst(["\(brand) \(systemName) engine", "\(systemName) engine"])
        }
        return info
    }
}
