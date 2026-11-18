import SwiftUI

@main
struct OBDProApp: App {
    @State private var session = VehicleSession()
    var body: some Scene {
        WindowGroup {
            RootView().environment(session)
        }
    }
}
