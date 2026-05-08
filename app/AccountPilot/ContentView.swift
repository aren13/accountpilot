import SwiftUI

struct ContentView: View {
    let migration: ConfigMigration.Result?
    @ObservedObject var supervisor: SyncSupervisor

    @State private var didProbeFDA: Bool = false
    @State private var fdaGranted: Bool = false
    @StateObject private var cliPrompt = CLILinkPrompt()

    var body: some View {
        Group {
            if !didProbeFDA {
                ProgressView("Checking permissions…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !fdaGranted {
                FDAWizardView(onGranted: {
                    fdaGranted = true
                    cliPrompt.checkOnLaunch()
                })
            } else {
                VStack(spacing: 0) {
                    BrowseView()
                    Divider()
                    footer
                }
                .alert(
                    "Install command-line tools?",
                    isPresented: $cliPrompt.shouldShow
                ) {
                    Button("Install") {
                        Task { await cliPrompt.install() }
                    }
                    Button("Skip", role: .cancel) {
                        cliPrompt.decline()
                    }
                } message: {
                    Text(
                        "This creates a symlink at /usr/local/bin/accountpilot so you can run AccountPilot from any terminal. You can remove it later with `rm /usr/local/bin/accountpilot`."
                    )
                }
            }
        }
        .task {
            let result = await FDAProbe.probe()
            fdaGranted = result.granted
            didProbeFDA = true
            if fdaGranted {
                cliPrompt.checkOnLaunch()
            }
        }
    }

    private var footer: some View {
        VStack(spacing: 4) {
            if case .imported(let count) = migration {
                Text("Imported \(count) account(s) from config.yaml")
                    .font(.caption).foregroundStyle(.green)
            }
            Text("AccountPilot 0.2.1")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(.ultraThinMaterial)
    }
}
