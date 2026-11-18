import SwiftUI

@main
struct OBDProApp: App {
    @State private var session = VehicleSession()
    @State private var updates = UpdateChecker()
    @Environment(\.scenePhase) private var phase
    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(session)
                .environment(updates)
                .task { await updates.checkOnLaunch() }
                .onChange(of: phase) { _, p in if p == .active { Task { await updates.checkOnLaunch() } } }
        }
    }
}
