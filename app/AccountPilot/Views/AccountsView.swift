import SwiftUI

struct AccountsView: View {
    @StateObject private var store = AccountStore()
    @State private var showAddSheet = false
    @State private var pendingError: AccountStoreError?

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Accounts")
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        Button {
                            showAddSheet = true
                        } label: {
                            Label("Add account", systemImage: "plus")
                        }
                    }
                }
                .sheet(isPresented: $showAddSheet) {
                    AddAccountSheet(store: store)
                }
                .alert(
                    "Could not remove account",
                    isPresented: .constant(pendingError != nil),
                    presenting: pendingError
                ) { _ in
                    Button("OK") { pendingError = nil }
                } message: { err in
                    Text(err.localizedDescription)
                }
                .task { await store.refresh() }
        }
    }

    @ViewBuilder
    private var content: some View {
        if store.isLoading && store.accounts.isEmpty {
            ProgressView("Loading accounts…")
        } else if let err = store.loadError {
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 36))
                    .foregroundStyle(.orange)
                Text("Could not load accounts").font(.headline)
                Text(err)
                    .font(.system(.body, design: .monospaced))
                    .multilineTextAlignment(.center)
                    .textSelection(.enabled)
                Button("Retry") { Task { await store.refresh() } }
            }
            .padding()
        } else if store.accounts.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "tray")
                    .font(.system(size: 40))
                    .foregroundStyle(.secondary)
                Text("No accounts yet").font(.headline)
                Text("Click + to add Gmail, Outlook, or iMessage.")
                    .foregroundStyle(.secondary)
            }
            .padding()
        } else {
            List {
                ForEach(store.accounts) { account in
                    AccountRow(account: account) {
                        await removeAccount(account)
                    }
                }
            }
        }
    }

    private func removeAccount(_ account: Account) async {
        do {
            try await store.remove(id: account.id)
        } catch let err as AccountStoreError {
            pendingError = err
        } catch {
            pendingError = AccountStoreError(code: "UNKNOWN", message: "\(error)")
        }
    }
}

private struct AccountRow: View {
    let account: Account
    let onRemove: () async -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: iconForSource(account.source))
                .font(.system(size: 22))
                .foregroundStyle(account.enabled ? Color.accentColor : .secondary)
                .frame(width: 32)
            VStack(alignment: .leading, spacing: 2) {
                Text(account.identifier).font(.body)
                Text("\(account.source) · \(account.ownerName)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button(role: .destructive) {
                Task { await onRemove() }
            } label: {
                Image(systemName: "minus.circle.fill")
                    .foregroundStyle(.red)
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, 4)
    }

    private func iconForSource(_ source: String) -> String {
        switch source {
        case "gmail", "outlook", "imap-generic": return "envelope"
        case "imessage": return "message"
        default: return "person.crop.circle"
        }
    }
}
