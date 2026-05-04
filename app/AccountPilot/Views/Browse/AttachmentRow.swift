import SwiftUI

struct AttachmentRow: View {
    let attachment: MessageDetail.Attachment

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: iconForMime(attachment.mimeType))
                .font(.system(size: 26))
                .foregroundStyle(.tint)
                .frame(width: 38)
            VStack(alignment: .leading, spacing: 2) {
                Text(attachment.filename).font(.callout).lineLimit(1)
                Text(humanSize(attachment.sizeBytes))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Open") {
                Task {
                    try? await AttachmentService.openInQuickLook(
                        attachmentID: attachment.id
                    )
                }
            }
            .controlSize(.small)
        }
        .padding(8)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private func iconForMime(_ mime: String?) -> String {
        guard let m = mime else { return "doc" }
        if m.hasPrefix("image/") { return "photo" }
        if m.hasPrefix("video/") { return "play.rectangle" }
        if m.hasPrefix("audio/") { return "waveform" }
        if m == "application/pdf" { return "doc.richtext" }
        return "doc"
    }

    private func humanSize(_ bytes: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }
}
