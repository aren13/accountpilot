import Foundation
import SwiftUI

/// Filter for the message list query. Setting `filter` doesn't auto-reload —
/// the parent view calls `reload()` explicitly.
struct MessageFilter: Equatable, Hashable {
    var accountID: Int?
    var contactID: Int?
    var since: Date?
}

@MainActor
final class MessagesStore: ObservableObject {
    @Published private(set) var messages: [Message] = []
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var loadError: String?
    @Published var filter: MessageFilter = .init()

    private var nextCursor: Int?
    private var loadTask: Task<Void, Never>?

    /// Reset + load the first page for the current `filter`.
    func reload() {
        messages = []
        nextCursor = nil
        loadError = nil
        loadTask?.cancel()
        loadTask = Task { await self.loadPage(append: false) }
    }

    /// Load the next page if there is one. No-op if already at end or loading.
    func loadMore() {
        guard nextCursor != nil, !isLoading else { return }
        loadTask?.cancel()
        loadTask = Task { await self.loadPage(append: true) }
    }

    private func loadPage(append: Bool) async {
        isLoading = true
        defer { isLoading = false }

        var args = ["-m", "accountpilot.cli", "messages", "list", "--json", "--limit", "50"]
        if let id = filter.accountID {
            args.append("--account"); args.append("\(id)")
        }
        if let id = filter.contactID {
            args.append("--contact-id"); args.append("\(id)")
        }
        if let since = filter.since {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withFullDate]
            args.append("--since"); args.append(f.string(from: since))
        }
        if append, let cursor = nextCursor {
            args.append("--cursor"); args.append("\(cursor)")
        }

        do {
            let stdout = try await PythonRuntime.shared.run(args)
            struct Env: Decodable {
                let ok: Bool
                let data: MessagesListData?
                let error: CLIEnvelope<EmptyData>.CLIError?
            }
            let env = try JSONDecoder.accountPilotCLI.decode(
                Env.self, from: Data(stdout.utf8)
            )
            guard env.ok, let data = env.data else {
                loadError = env.error?.message ?? "unknown error"
                return
            }
            if append { messages.append(contentsOf: data.messages) }
            else { messages = data.messages }
            nextCursor = data.nextCursor
        } catch {
            loadError = "\(error)"
        }
    }
}
