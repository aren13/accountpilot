import SwiftUI

struct StatusBarMenu: View {
    @ObservedObject var supervisor: SyncSupervisor
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        if supervisor.status.isEmpty {
            Text("No accounts").disabled(true)
        } else {
            ForEach(supervisor.status) { s in
                Section(s.identifier) {
                    Text(lastSyncLabel(s))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Sync Now") {
                        Task { _ = await supervisor.syncNow(accountID: s.id) }
                    }
                }
            }
            Divider()
        }
        Button("Open AccountPilot…") {
            openWindow(id: "main")
            NSApp.activate(ignoringOtherApps: true)
        }
        Divider()
        Button(supervisor.isRunning ? "Pause Sync" : "Resume Sync") {
            Task {
                if supervisor.isRunning { await supervisor.stop() }
                else { await supervisor.start() }
            }
        }
        Divider()
        Button("Quit AccountPilot") { NSApp.terminate(nil) }
            .keyboardShortcut("q")
    }

    private func lastSyncLabel(_ s: SyncStatus) -> String {
        guard let d = s.lastSyncAt else { return "Never synced" }
        let f = RelativeDateTimeFormatter()
        return "Last sync: \(f.localizedString(for: d, relativeTo: .now))"
    }
}
