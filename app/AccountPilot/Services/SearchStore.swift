import Foundation
import SwiftUI

@MainActor
final class SearchStore: ObservableObject {
    @Published var query: String = ""
    @Published private(set) var results: [SearchResult] = []
    @Published private(set) var isLoading: Bool = false

    private var debounceTask: Task<Void, Never>?

    /// Call when the search field text changes. Debounces 300ms then queries.
    func update(query newQuery: String) {
        query = newQuery
        debounceTask?.cancel()
        let trimmed = newQuery.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else {
            results = []
            return
        }
        debounceTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await self?.fire(trimmed)
        }
    }

    private func fire(_ query: String) async {
        isLoading = true
        defer { isLoading = false }
        do {
            let stdout = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "search", query, "--json", "--limit", "50"]
            )
            struct Env: Decodable {
                struct SearchData: Decodable { let query: String; let results: [SearchResult] }
                let ok: Bool; let data: SearchData?
            }
            let env = try JSONDecoder.accountPilotCLI.decode(
                Env.self, from: Data(stdout.utf8)
            )
            results = env.data?.results ?? []
        } catch {
            results = []
        }
    }
}

struct SearchResult: Codable, Identifiable, Hashable {
    let id: Int
    let source: String
    let accountID: Int
    let sentAt: Date
    let subject: String
    let snippet: String
    let score: Double

    enum CodingKeys: String, CodingKey {
        case id, source, subject, snippet, score
        case accountID = "account_id"
        case sentAt = "sent_at"
    }
}
