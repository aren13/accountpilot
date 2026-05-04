import SwiftUI

struct MessageListView: View {
    @StateObject private var store = MessagesStore()
    @StateObject private var search = SearchStore()
    @Binding var selection: Int?
    var filter: MessageFilter

    var body: some View {
        Group {
            if !search.query.isEmpty {
                searchResultsList
            } else if store.isLoading && store.messages.isEmpty {
                ProgressView("Loading messages…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let err = store.loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 28))
                        .foregroundStyle(.orange)
                    Text("Couldn't load messages").font(.headline)
                    Text(err)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    Button("Retry") { store.reload() }
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if store.messages.isEmpty {
                Text("No messages")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                messagesList
            }
        }
        .searchable(text: Binding(
            get: { search.query },
            set: { search.update(query: $0) }
        ), prompt: "Search all messages")
        .onChange(of: filter) { newValue in
            store.filter = newValue
            store.reload()
        }
        .task {
            store.filter = filter
            store.reload()
        }
    }

    @ViewBuilder
    private var messagesList: some View {
        List(selection: $selection) {
            ForEach(store.messages) { msg in
                MessageRow(message: msg)
                    .tag(msg.id)
                    .onAppear {
                        if msg.id == store.messages.last?.id {
                            store.loadMore()
                        }
                    }
            }
            if store.isLoading && !store.messages.isEmpty {
                HStack {
                    Spacer()
                    ProgressView().controlSize(.small)
                    Spacer()
                }
                .listRowSeparator(.hidden)
            }
        }
    }

    @ViewBuilder
    private var searchResultsList: some View {
        if search.results.isEmpty && !search.isLoading {
            Text("No results for \"\(search.query)\"")
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(selection: $selection) {
                ForEach(search.results) { r in
                    SearchResultRow(result: r)
                        .tag(r.id)
                }
            }
        }
    }
}

private struct MessageRow: View {
    let message: Message
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: iconForSource(message.source))
                .frame(width: 22)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(message.fromName ?? message.fromIdentifier ?? "Unknown")
                        .font(.body.weight(.medium))
                    Spacer()
                    if message.hasAttachments {
                        Image(systemName: "paperclip")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Text(message.sentAt, style: .relative)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                if !message.subject.isEmpty {
                    Text(message.subject).font(.callout).lineLimit(1)
                }
                Text(message.snippet)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 2)
    }

    private func iconForSource(_ s: String) -> String {
        switch s {
        case "gmail", "outlook", "imap-generic": return "envelope"
        case "imessage": return "message"
        default: return "tray"
        }
    }
}

private struct SearchResultRow: View {
    let result: SearchResult
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(result.subject.isEmpty ? "(no subject)" : result.subject)
                    .font(.body.weight(.medium))
                    .lineLimit(1)
                Spacer()
                Text(result.sentAt, style: .relative)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Text(result.snippet)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
    }
}
