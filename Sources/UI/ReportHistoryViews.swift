import SwiftUI
import UIKit
import WebKit

// MARK: - Report

struct ReportView: View {
    @Environment(VehicleSession.self) private var s
    @State private var pdfURL: URL?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if let p = s.reportProgress {
                    VStack(spacing: 8) {
                        if let v = s.vehicle { ScanShowcase(vehicle: v, progress: p.0, status: p.1) }
                        else { ProgressView(value: p.0) { Text(p.1).font(.caption) }.padding() }
                    }
                    .padding(.vertical)
                }
                if let r = s.report {
                    HTMLView(html: ReportHTML.render(r))
                } else if s.reportProgress == nil {
                    ContentUnavailableView {
                        Label("Full Scan Report", systemImage: "doc.text.magnifyingglass")
                    } description: {
                        Text("Scans every module: identification, faults, readiness, mileage cross-check, airbag check and a live snapshot.")
                    } actions: {
                        Button("Run Full Scan") { Task { await s.buildReport() } }
                            .buttonStyle(.borderedProminent).disabled(s.state != .connected)
                    }
                }
            }
            .navigationTitle("Report")
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if let r = s.report {
                        ShareLink(item: pdfURL ?? ReportHTML.pdf(r)) { Image(systemName: "square.and.arrow.up") }
                    }
                    Button { Task { await s.buildReport(); if let r = s.report { pdfURL = ReportHTML.pdf(r) } } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(s.state != .connected || s.reportProgress != nil)
                }
            }
        }
    }
}

struct HTMLView: UIViewRepresentable {
    let html: String
    func makeUIView(context: Context) -> WKWebView {
        let w = WKWebView()
        w.isOpaque = false
        w.backgroundColor = .clear
        return w
    }
    func updateUIView(_ w: WKWebView, context: Context) { w.loadHTMLString(html, baseURL: nil) }
}

enum ReportHTML {
    static func esc(_ s: String) -> String {
        s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
    }

    static func render(_ r: VehicleReport, print: Bool = false) -> String {
        let bg = print ? "#fff" : "#0f1012", card = print ? "#f6f6f8" : "#1b1c20", text = print ? "#111" : "#f2f2f7"
        let muted = print ? "#666" : "#8e8e93", line = print ? "#ddd" : "#2a2b30"
        let present = r.modules.filter(\.present)
        let n = r.faultCount
        var rows = ""
        for m in r.modules {
            if !m.present {
                rows += "<tr class=na><td>\(esc(m.address))</td><td>\(esc(m.name))</td><td colspan=2>Not fitted / no response</td></tr>"
            } else {
                let st = m.faults.isEmpty ? "<span class=ok>OK</span>" : "<span class=bad>\(m.faults.count) fault(s)</span>"
                rows += "<tr><td><b>\(esc(m.address))</b></td><td>\(esc(m.name))<div class=sub>\(esc(m.system ?? ""))</div></td><td>\(st)</td><td class=mono>\(esc(m.part ?? ""))</td></tr>"
            }
        }
        var details = ""
        for m in present where !m.faults.isEmpty {
            details += "<div class=card><h3>\(esc(m.address)) · \(esc(m.name))</h3><table>"
            for f in m.faults {
                details += "<tr><td class=mono><b>\(esc(f.code))</b></td><td>\(esc(f.state))</td><td>\(esc(f.description))<div class=sub>\(esc(f.detail))</div></td></tr>"
            }
            details += "</table></div>"
        }
        let obd = r.obdCodes.map { name, codes in
            "<tr><td>\(esc(name))</td><td>" + (codes.isEmpty ? "<span class=ok>No codes</span>"
                : codes.map { "<b class=mono>\($0.code)</b> \($0.kind.rawValue) — \(esc($0.description))" }.joined(separator: "<br>")) + "</td></tr>"
        }.joined()
        let ready = r.readiness.map { "<span class='chip \($0.1 ? "ok" : "warn")'>\(esc($0.0)): \($0.1 ? "complete" : "incomplete")</span>" }.joined()
        let snap = r.snapshot.map { "<tr><td class=k>\(esc($0.0))</td><td>\(esc($0.1))</td></tr>" }.joined()
        let notes = r.notes.map { "<li><b>\(esc($0.0)):</b> \(esc($0.1))</li>" }.joined()
        let odo = r.mileage.first.map { "\($0.1.formatted()) km" } ?? "—"
        let date = r.date.formatted(date: .abbreviated, time: .shortened)
        return """
        <!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
        <style>
        body{background:\(bg);color:\(text);font:15px -apple-system,Helvetica,sans-serif;margin:0;padding:16px}
        h1{font-size:24px;margin:0} h2{font-size:17px;margin:22px 0 8px} h3{font-size:15px;margin:0 0 8px}
        .sub{color:\(muted);font-size:12px} .mono{font-family:Menlo,monospace}
        .card{background:\(card);border:1px solid \(line);border-radius:14px;padding:12px 14px;margin:10px 0}
        .stats{display:flex;flex-wrap:wrap;gap:8px} .stat{flex:1 1 140px;background:\(card);border:1px solid \(line);border-radius:14px;padding:10px 12px}
        .stat b{display:block;font-size:19px} .stat span{color:\(muted);font-size:11px;text-transform:uppercase}
        table{width:100%;border-collapse:collapse} td{padding:7px 6px;border-bottom:1px solid \(line);vertical-align:top}
        td.k{color:\(muted)} tr.na td{color:\(muted)} .ok{color:#30D158;font-weight:600} .bad{color:#FF9F0A;font-weight:600}
        .chip{display:inline-block;padding:3px 9px;border-radius:9px;margin:3px;font-size:12px;background:#203a27;color:#7ee29a}
        .chip.warn{background:#4a3a12;color:#ffd60a}
        </style></head><body>
        <h1>\(esc(r.brand ?? "Vehicle")) diagnostic report</h1>
        <div class=sub>\(date) · OBD Pro · \(esc(r.adapter)) · \(esc(r.proto))</div>
        <div class=card style="border-left:5px solid \(n == 0 ? "#30D158" : "#FF9F0A")"><b style="font-size:17px">\(n == 0 ? "No faults found" : "\(n) fault(s)")</b>
        <div class=sub>\(present.count) modules responded · Check Engine light \(r.mil == true ? "ON" : "OFF")</div></div>
        <div class=stats>
        <div class=stat><span>VIN</span><b class=mono style="font-size:13px">\(esc(r.vin ?? "—"))</b></div>
        <div class=stat><span>Odometer</span><b>\(odo)</b></div>
        <div class=stat><span>Battery</span><b>\(r.battery.map { String(format: "%.1f V", $0) } ?? "—")</b></div>
        <div class=stat><span>Faults</span><b class=\(n == 0 ? "ok" : "bad")>\(n)</b></div></div>
        <h2>Modules</h2><div class=card><table>\(rows)</table></div>
        \(notes.isEmpty ? "" : "<h2>Notes</h2><div class=card><ul>\(notes)</ul></div>")
        \(details.isEmpty ? "" : "<h2>Faults</h2>\(details)")
        <h2>Generic OBD-II</h2><div class=card><table>\(obd)</table><div>\(ready)</div></div>
        <h2>Live snapshot</h2><div class=card><table>\(snap)</table></div>
        </body></html>
        """
    }

    /// Renders a light, printable PDF into a temp file for sharing.
    static func pdf(_ r: VehicleReport) -> URL {
        let fmt = UIMarkupTextPrintFormatter(markupText: render(r, print: true))
        let renderer = UIPrintPageRenderer()
        renderer.addPrintFormatter(fmt, startingAtPageAt: 0)
        let page = CGRect(x: 0, y: 0, width: 595, height: 842)           // A4 @72dpi
        renderer.setValue(page, forKey: "paperRect")
        renderer.setValue(page.insetBy(dx: 28, dy: 32), forKey: "printableRect")
        let data = NSMutableData()
        UIGraphicsBeginPDFContextToData(data, page, nil)
        for i in 0..<max(renderer.numberOfPages, 1) {
            UIGraphicsBeginPDFPage()
            renderer.drawPage(at: i, in: UIGraphicsGetPDFContextBounds())
        }
        UIGraphicsEndPDFContext()
        let name = "Report_\(r.vin?.suffix(6) ?? "car")_\(Int(r.date.timeIntervalSince1970)).pdf"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        try? (data as Data).write(to: url)
        return url
    }
}

// MARK: - Fault history

struct FaultHistoryView: View {
    @Environment(VehicleSession.self) private var s

    var body: some View {
        NavigationStack {
            List {
                let rows = s.faultSummaries
                if rows.isEmpty {
                    ContentUnavailableView("No history yet", systemImage: "clock.arrow.circlepath",
                                           description: Text("Every scan is remembered here: first seen, last seen, how often, and whether a code came back after clearing."))
                }
                ForEach(rows) { e in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(e.code).font(.headline.monospaced())
                            Spacer()
                            Text(e.state).font(.caption2.bold()).padding(.horizontal, 7).padding(.vertical, 2)
                                .background((e.state == "Active" ? Color.red : e.state == "Stored" ? Color.yellow : Color.gray).opacity(0.25), in: Capsule())
                        }
                        Text("\(e.module) · \(e.moduleName)").font(.subheadline)
                        Text("First \(e.first.formatted(date: .abbreviated, time: .omitted)) · last \(e.last.formatted(date: .abbreviated, time: .shortened)) · seen \(e.seen)×")
                            .font(.caption).foregroundStyle(.secondary)
                        if e.cleared > 0 {
                            Text(e.cameBack ? "Cleared \(e.cleared)× — CAME BACK" : "Cleared \(e.cleared)×")
                                .font(.caption.bold()).foregroundStyle(e.cameBack ? .red : .green)
                        }
                    }
                }
            }
            .navigationTitle("Fault History")
        }
    }
}
