import SwiftUI

struct BrowseView: View {
    @StateObject private var accountStore = AccountStore()
    @State private var sidebarSelection: BrowseSelection? = .allMessages
    @State private var messageSelection: Int?

    var body: some View {
        NavigationSplitView {
            BrowseSidebar(accountStore: accountStore, selection: $sidebarSelection)
                .frame(minWidth: 220)
        } content: {
            switch sidebarSelection {
            case .manageAccounts:
                AccountsView()
            case nil:
                Text("Select a source from the sidebar")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            default:
                MessageListView(
                    selection: $messageSelection,
                    filter: filterFor(sidebarSelection)
                )
                .frame(minWidth: 320)
            }
        } detail: {
            if let id = messageSelection {
                MessageDetailView(messageID: id)
            } else {
                Text("Select a message")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle("AccountPilot")
        .onChange(of: sidebarSelection) { _ in
            // clear detail pane on navigation
            messageSelection = nil
        }
    }

    private func filterFor(_ sel: BrowseSelection?) -> MessageFilter {
        switch sel {
        case .allMessages, nil, .manageAccounts:
            return MessageFilter()
        case .account(let id):
            return MessageFilter(accountID: id)
        case .contact(let id):
            return MessageFilter(contactID: id)
        }
    }
}
