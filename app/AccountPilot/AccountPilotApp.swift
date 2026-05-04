import SwiftUI

@main
struct AccountPilotApp: App {
    var body: some Scene {
        WindowGroup("AccountPilot") {
            ContentView()
                .frame(minWidth: 480, minHeight: 320)
        }
        .windowResizability(.contentMinSize)
    }
}
