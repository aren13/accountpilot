import SwiftUI

struct ContentView: View {
    @State private var pythonVersion: String = "loading…"
    @State private var accountpilotVersion: String = "loading…"
    @State private var loadError: String?

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "tray.full")
                .font(.system(size: 40))
                .foregroundStyle(.tint)
            Text("AccountPilot 0.2.0")
                .font(.title2.weight(.semibold))
            Text("Python: \(pythonVersion)")
                .font(.system(.body, design: .monospaced))
            Text("accountpilot: \(accountpilotVersion)")
                .font(.system(.body, design: .monospaced))
            if let err = loadError {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
            }
        }
        .padding(40)
        .task { await loadVersions() }
    }

    private func loadVersions() async {
        do {
            pythonVersion = try await PythonRuntime.shared.run(
                ["-c", "import platform; print(platform.python_version())"]
            ).trimmingCharacters(in: .whitespacesAndNewlines)
            accountpilotVersion = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "--version"]
            ).trimmingCharacters(in: .whitespacesAndNewlines)
        } catch {
            loadError = "\(error)"
        }
    }
}
