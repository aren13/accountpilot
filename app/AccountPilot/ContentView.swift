import SwiftUI

struct ContentView: View {
    let migration: ConfigMigration.Result?

    @State private var pythonVersion: String = "loading…"
    @State private var accountpilotVersion: String = "loading…"

    var body: some View {
        VStack(spacing: 0) {
            AccountsView()
            Divider()
            footer
        }
        .task { await loadVersions() }
    }

    @ViewBuilder
    private var footer: some View {
        VStack(spacing: 4) {
            if case .imported(let count) = migration {
                Text("Imported \(count) account(s) from config.yaml")
                    .font(.caption)
                    .foregroundStyle(.green)
            } else if case .failed(let msg) = migration {
                Text("Migration failed: \(msg)")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .lineLimit(2)
            }
            HStack(spacing: 12) {
                Text("AccountPilot 0.2.0")
                Text("·")
                Text("Python \(pythonVersion)")
                    .font(.system(.caption, design: .monospaced))
                Text("·")
                Text("accountpilot \(accountpilotVersion)")
                    .font(.system(.caption, design: .monospaced))
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(.ultraThinMaterial)
    }

    private func loadVersions() async {
        if let pv = try? await PythonRuntime.shared.run(
            ["-c", "import platform; print(platform.python_version())"]
        ) {
            pythonVersion = pv.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if let av = try? await PythonRuntime.shared.run(
            ["-m", "accountpilot.cli", "--version"]
        ) {
            accountpilotVersion = av.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }
}
