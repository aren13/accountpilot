import SwiftUI

/// Tag identifying which sidebar row is selected.
enum BrowseSelection: Hashable {
    case allMessages
    case account(id: Int)
    case contact(id: Int)
    case manageAccounts
}

struct BrowseSidebar: View {
    @ObservedObject var accountStore: AccountStore
    @State private var people: [Person] = []
    @State private var loadError: String?

    @Binding var selection: BrowseSelection?

    var body: some View {
        List(selection: $selection) {
            Section("Library") {
                Label("All Messages", systemImage: "tray.full")
                    .tag(BrowseSelection.allMessages)
                ForEach(accountStore.accounts) { acct in
                    Label {
                        VStack(alignment: .leading) {
                            Text(acct.identifier)
                            Text(acct.source)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: iconForSource(acct.source))
                    }
                    .tag(BrowseSelection.account(id: acct.id))
                }
            }
            Section("People") {
                ForEach(people.prefix(20)) { p in
                    Label {
                        HStack {
                            Text(p.displayName)
                            Spacer()
                            Text("\(p.messageCount)")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "person.crop.circle")
                    }
                    .tag(BrowseSelection.contact(id: p.id))
                }
            }
            Section {
                Label("Manage Accounts…", systemImage: "gearshape")
                    .tag(BrowseSelection.manageAccounts)
            }
        }
        .listStyle(.sidebar)
        .task {
            await accountStore.refresh()
            await loadPeople()
        }
    }

    private func loadPeople() async {
        do {
            let stdout = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "people", "list", "--json"]
            )
            struct Env: Decodable { let ok: Bool; let data: PeopleListData? }
            let env = try JSONDecoder().decode(Env.self, from: Data(stdout.utf8))
            // Filter out owners — sidebar shows other people only
            people = (env.data?.people ?? []).filter { !$0.isOwner }
        } catch {
            loadError = "\(error)"
        }
    }

    private func iconForSource(_ s: String) -> String {
        switch s {
        case "gmail", "outlook", "imap-generic": return "envelope"
        case "imessage": return "message"
        default: return "person.crop.circle"
        }
    }
}
