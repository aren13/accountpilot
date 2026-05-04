import SwiftUI

struct SettingsView: View {
    @ObservedObject var supervisor: SyncSupervisor
    @AppStorage("backgroundSyncEnabled") private var backgroundSyncEnabled = true

    var body: some View {
        Form {
            Section("Sync") {
                Toggle("Background sync enabled", isOn: $backgroundSyncEnabled)
                    .onChange(of: backgroundSyncEnabled) { newValue in
                        Task {
                            if newValue { await supervisor.start() }
                            else { await supervisor.stop() }
                        }
                    }
                if let err = supervisor.lastError {
                    LabeledContent("Last error") {
                        Text(err).font(.caption).foregroundStyle(.red)
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .padding(20)
        .frame(width: 460)
    }
}
