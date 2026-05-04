import Foundation

/// Decoded shape of `accountpilot config import --json`'s `data` field.
struct ConfigImportData: Decodable {
    let accountsImported: Int
    let renamedTo: String?
    let noop: Bool

    enum CodingKeys: String, CodingKey {
        case accountsImported = "accounts_imported"
        case renamedTo = "renamed_to"
        case noop
    }
}

/// First-launch migration: imports accounts from `config.yaml` (if it
/// exists) into the SQLite DB, then renames the YAML to mark the
/// migration as done. Subsequent launches see no YAML and noop.
///
/// Surface design note: returning the result rather than mutating
/// global state lets `AccountPilotApp` decide what to do with import
/// failures (today: log + continue; later: show a one-time banner).
enum ConfigMigration {

    enum Result: Equatable {
        case skipped                              // YAML missing; nothing to do
        case imported(count: Int)                 // success
        case failed(message: String)              // error
    }

    static func runIfNeeded() async -> Result {
        do {
            let stdout = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "config", "import", "--json"]
            )
            let env = try JSONDecoder().decode(
                CLIEnvelope<ConfigImportData>.self,
                from: Data(stdout.utf8)
            )
            guard env.ok, let data = env.data else {
                return .failed(message: env.error?.message ?? "unknown migration error")
            }
            if data.noop {
                return .skipped
            }
            return .imported(count: data.accountsImported)
        } catch {
            return .failed(message: "\(error)")
        }
    }
}
