import Foundation

/// One row of `accountpilot status --json`'s `data.accounts[]`.
struct SyncStatus: Codable, Identifiable, Hashable {
    let id: Int                    // == account id
    let source: String
    let identifier: String
    let lastSyncAt: Date?          // null if never synced
    let lastError: String?
    let syncedCount: Int

    enum CodingKeys: String, CodingKey {
        case id, source, identifier
        case lastSyncAt = "last_sync_at"
        case lastError = "last_error"
        case syncedCount = "synced_count"
    }
}

struct SyncStatusListData: Decodable {
    let accounts: [SyncStatus]
    let generatedAt: Date

    enum CodingKeys: String, CodingKey {
        case accounts
        case generatedAt = "generated_at"
    }
}

extension JSONDecoder {
    /// AccountPilot CLI emits ISO8601 with offset (e.g. "2026-05-05T10:23:00+00:00").
    /// Use this factory whenever decoding CLI output that includes timestamps.
    static var accountPilotCLI: JSONDecoder {
        let d = JSONDecoder()
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        d.dateDecodingStrategy = .custom { decoder in
            let str = try decoder.singleValueContainer().decode(String.self)
            if let date = formatter.date(from: str) { return date }
            throw DecodingError.dataCorruptedError(
                in: try decoder.singleValueContainer(),
                debugDescription: "expected ISO8601, got \(str)"
            )
        }
        return d
    }
}
