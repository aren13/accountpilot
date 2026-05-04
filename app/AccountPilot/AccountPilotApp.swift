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
            StatusBarMenu(supervisor: supervisor) {
                NSApp.activate(ignoringOtherApps: true)
                openMainWindow()
            }
        }

        Settings {
            SettingsView(supervisor: supervisor)
        }
    }

    @MainActor
    private func openMainWindow() {
        // SwiftUI's Window scene with id: "main" can be opened via the
        // legacy URL scheme — the more recent OpenWindowAction lives in
        // EnvironmentValues which isn't available at the App-body level
        // without ceremony. The URL form just works.
        if let url = URL(string: "accountpilot://main") {
            NSWorkspace.shared.open(url)
        }
    }
}
