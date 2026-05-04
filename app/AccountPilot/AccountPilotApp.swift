import SwiftUI

@main
struct AccountPilotApp: App {
    @StateObject private var supervisor = SyncSupervisor()
    @State private var migration: ConfigMigration.Result?

    @AppStorage("backgroundSyncEnabled") private var backgroundSyncEnabled = true

    var body: some Scene {
        Window("AccountPilot", id: "main") {
            ContentView(migration: migration, supervisor: supervisor)
                .frame(minWidth: 720, minHeight: 480)
                .task {
                    if migration == nil {
                        migration = await ConfigMigration.runIfNeeded()
                    }
                    if backgroundSyncEnabled {
                        await supervisor.start()
                    }
                }
        }
        .windowResizability(.contentMinSize)

        MenuBarExtra("AccountPilot", systemImage: supervisor.isRunning ? "tray.full.fill" : "tray") {
            StatusBarMenu(supervisor: supervisor)
        }

        Settings {
            SettingsView(supervisor: supervisor)
        }
    }
}
