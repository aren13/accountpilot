import Foundation
import SwiftUI

/// ObservableObject backing `AccountsView`. All account state mutations
/// go through `accountpilot ... --json` invocations of the bundled CLI.
/// The CLI is the single source of truth; the store re-fetches after
/// every mutation rather than tracking state independently.
@MainActor
final class AccountStore: ObservableObject {
    @Published private(set) var accounts: [Account] = []
    @Published private(set) var loadError: String?
    @Published private(set) var isLoading: Bool = false

    /// Refresh the list from `accountpilot accounts list --json`.
    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let stdout = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "accounts", "list", "--json"]
            )
            let env = try JSONDecoder().decode(
                CLIEnvelope<AccountsListData>.self,
                from: Data(stdout.utf8)
            )
            if env.ok, let data = env.data {
                self.accounts = data.accounts
                self.loadError = nil
            } else {
                self.loadError = env.error?.message ?? "unknown error"
            }
        } catch {
            self.loadError = "\(error)"
        }
    }

    /// Add a new account. Returns the new account's id on success, or
    /// throws an `AccountStoreError` (carries the CLI's error.code) on
    /// failure. Caller is responsible for triggering OAuth afterward.
    func add(
        provider: String,
        identifier: String,
        ownerName: String,
        ownerSurname: String?
    ) async throws -> Int {
        var args = [
            "-m", "accountpilot.cli", "accounts", "add", "--json",
            "--provider", provider,
            "--identifier", identifier,
            "--owner-name", ownerName,
        ]
        if let s = ownerSurname, !s.isEmpty {
            args.append("--owner-surname")
            args.append(s)
        }
        let stdout = try await PythonRuntime.shared.run(args)

        struct AddData: Decodable { let account: Account }
        let env = try JSONDecoder().decode(
            CLIEnvelope<AddData>.self, from: Data(stdout.utf8)
        )
        guard env.ok, let data = env.data else {
            throw AccountStoreError(
                code: env.error?.code ?? "UNKNOWN",
                message: env.error?.message ?? "add failed"
            )
        }
        await refresh()
        return data.account.id
    }

    /// Remove account by id. Throws on failure.
    func remove(id: Int) async throws {
        let stdout = try await PythonRuntime.shared.run(
            ["-m", "accountpilot.cli", "accounts", "remove", "\(id)", "--json"]
        )
        struct RemoveData: Decodable { let removed_id: Int }
        let env = try JSONDecoder().decode(
            CLIEnvelope<RemoveData>.self, from: Data(stdout.utf8)
        )
        guard env.ok else {
            throw AccountStoreError(
                code: env.error?.code ?? "UNKNOWN",
                message: env.error?.message ?? "remove failed"
            )
        }
        await refresh()
    }

    /// Run an OAuth login for an existing account id; returns the secrets
    /// path on success. The CLI blocks until the user completes consent
    /// in the browser, so this can take 15–60 seconds — caller should
    /// show a spinner.
    func oauthLogin(provider: String, accountID: Int) async throws -> String {
        guard provider == "google" || provider == "microsoft" else {
            throw AccountStoreError(
                code: "UNSUPPORTED_PROVIDER",
                message: "no OAuth flow for provider=\(provider)"
            )
        }
        let stdout = try await PythonRuntime.shared.run([
            "-m", "accountpilot.cli", "oauth", "login", provider,
            "\(accountID)", "--json",
        ])
        struct LoginData: Decodable {
            let account_id: Int
            let provider: String
            let secret_path: String
        }
        let env = try JSONDecoder().decode(
            CLIEnvelope<LoginData>.self, from: Data(stdout.utf8)
        )
        guard env.ok, let data = env.data else {
            throw AccountStoreError(
                code: env.error?.code ?? "OAUTH_FAILED",
                message: env.error?.message ?? "oauth login failed"
            )
        }
        return data.secret_path
    }
}

struct AccountStoreError: Error, LocalizedError {
    let code: String
    let message: String
    var errorDescription: String? { "[\(code)] \(message)" }
}
