import SwiftUI

struct ContentView: View {
    let migration: ConfigMigration.Result?
    @ObservedObject var supervisor: SyncSupervisor

    @State private var didProbeFDA: Bool = false
    @State private var fdaGranted: Bool = false

    var body: some View {
        Group {
            if !didProbeFDA {
                ProgressView("Checking permissions…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !fdaGranted {
                FDAWizardView(onGranted: {
                    fdaGranted = true
                })
            } else {
                VStack(spacing: 0) {
                    BrowseView()
                    Divider()
                    footer
                }
            }
        }
        .task {
            let result = await FDAProbe.probe()
            fdaGranted = result.granted
            didProbeFDA = true
        }
    }

    private var footer: some View {
        VStack(spacing: 4) {
            if case .imported(let count) = migration {
                Text("Imported \(count) account(s) from config.yaml")
                    .font(.caption).foregroundStyle(.green)
            }
            Text("AccountPilot 0.2.0")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(.ultraThinMaterial)
    }
}
