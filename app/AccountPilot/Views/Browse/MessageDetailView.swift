import SwiftUI

struct MessageDetailView: View {
    let messageID: Int
    @State private var detail: MessageDetail?
    @State private var loadError: String?

    var body: some View {
        Group {
            if let d = detail {
                content(d)
            } else if let err = loadError {
                Text(err).foregroundStyle(.red).padding()
            } else {
                ProgressView()
            }
        }
        .task(id: messageID) { await load() }
    }

    @ViewBuilder
    private func content(_ d: MessageDetail) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let subject = d.subject, !subject.isEmpty {
                    Text(subject)
                        .font(.title2.bold())
                        .textSelection(.enabled)
                }
                HStack(spacing: 8) {
                    Text("From").foregroundStyle(.secondary)
                    Text(d.people.first(where: { $0.role == "from" })?.name ?? "—")
                        .fontWeight(.medium)
                }
                .font(.callout)
                Text(d.sentAt, format: .dateTime)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Divider()

                Text(d.bodyText)
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if !d.attachments.isEmpty {
                    Divider()
                    Text("Attachments").font(.headline)
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 220), spacing: 12)],
                        spacing: 12
                    ) {
                        ForEach(d.attachments) { att in
                            AttachmentRow(attachment: att)
                        }
                    }
                }
            }
            .padding(24)
        }
    }

    private func load() async {
        loadError = nil
        do {
            let stdout = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "messages", "get",
                 "\(messageID)", "--json"]
            )
            struct Env: Decodable { let ok: Bool; let data: MessageGetData? }
            let env = try JSONDecoder.accountPilotCLI.decode(
                Env.self, from: Data(stdout.utf8)
            )
            detail = env.data?.message
        } catch {
            loadError = "\(error)"
        }
    }
}
