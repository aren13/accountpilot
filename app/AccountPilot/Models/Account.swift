import Foundation

/// Mirrors one row of `accountpilot accounts list --json`'s `data.accounts[]`.
/// Identifiable via the integer DB primary key.
struct Account: Codable, Identifiable, Hashable {
    let id: Int
    let source: String        // "gmail", "outlook", "imap-generic", "imessage"
    let identifier: String    // user-visible (email, phone, …)
    let enabled: Bool
    let ownerID: Int
    let ownerName: String

    enum CodingKeys: String, CodingKey {
        case id, source, identifier, enabled
        case ownerID = "owner_id"
        case ownerName = "owner_name"
    }
}

/// Top-level envelope shared by every `--json` CLI command. `T` is the
/// command-specific shape of `data`. Use `EmptyData` if the command
/// returns no payload (Swift requires the type parameter even for `null`).
struct CLIEnvelope<T: Decodable>: Decodable {
    let ok: Bool
    let data: T?
    let error: CLIError?

    struct CLIError: Decodable {
        let code: String
        let message: String
    }
}

struct EmptyData: Decodable {}

/// Convenience for `accounts list --json` — decodes
/// `{"ok": true, "data": {"accounts": [...]}, "error": null}` directly.
struct AccountsListData: Decodable {
    let accounts: [Account]
}
