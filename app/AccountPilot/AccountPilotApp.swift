import SwiftUI

@main
struct AccountPilotApp: App {
    @State private var migration: ConfigMigration.Result?

    var body: some Scene {
        WindowGroup("AccountPilot") {
            ContentView(migration: migration)
                .frame(minWidth: 720, minHeight: 480)
                .task {
                    if migration == nil {
                        migration = await ConfigMigration.runIfNeeded()
                    }
                }
        }
        .windowResizability(.contentMinSize)
    }
}
