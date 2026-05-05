import Foundation
import SwiftUI

/// One-shot prompt that asks the user whether to install
/// /usr/local/bin/accountpilot. Stores acceptance/decline in
/// UserDefaults so the prompt only fires once.
@MainActor
final class CLILinkPrompt: ObservableObject {
    @Published var shouldShow: Bool = false
    @Published private(set) var lastError: String?

    private let promptedKey = "cliLinkPrompted"

    func checkOnLaunch() {
        if UserDefaults.standard.bool(forKey: promptedKey) {
            return
        }
        // Only prompt if the symlink doesn't already exist.
        let target = URL(fileURLWithPath: "/usr/local/bin/accountpilot")
        if FileManager.default.fileExists(atPath: target.path) {
            UserDefaults.standard.set(true, forKey: promptedKey)
            return
        }
        shouldShow = true
    }

    /// User clicked Install. Run `accountpilot self link --json`.
    func install() async {
        defer {
            shouldShow = false
            UserDefaults.standard.set(true, forKey: promptedKey)
        }
        do {
            let stdout = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "self", "link", "--json"]
            )
            struct Env: Decodable {
                struct InnerData: Decodable { let created: Bool }
                let ok: Bool
                let data: InnerData?
                struct Err: Decodable { let code: String; let message: String }
                let error: Err?
            }
            let env = try JSONDecoder().decode(Env.self, from: Data(stdout.utf8))
            if !env.ok {
                lastError = env.error?.message ?? "unknown error"
            }
        } catch {
            lastError = "\(error)"
        }
    }

    /// User clicked Skip. Mark prompted so we don't ask again.
    func decline() {
        UserDefaults.standard.set(true, forKey: promptedKey)
        shouldShow = false
    }
}
