import Foundation
import AppKit

enum AttachmentService {
    /// Resolves an attachment id via the CLI, then opens the file in
    /// the user's default app for that mime type. macOS Quick Look
    /// (cmd+space-after-Finder-select) requires the file to be in a
    /// Finder window — for direct preview, NSWorkspace.open() works
    /// for image/video/PDF/text via the registered handlers.
    static func openInQuickLook(attachmentID: Int) async throws {
        let stdout = try await PythonRuntime.shared.run(
            ["-m", "accountpilot.cli", "attachments", "path",
             "\(attachmentID)", "--json"]
        )
        struct Env: Decodable {
            struct PathData: Decodable {
                let id: Int
                let absolutePath: String
                let exists: Bool
                let sizeBytes: Int
                enum CodingKeys: String, CodingKey {
                    case id, exists
                    case absolutePath = "absolute_path"
                    case sizeBytes = "size_bytes"
                }
            }
            let ok: Bool
            let data: PathData?
            struct Err: Decodable { let code: String; let message: String }
            let error: Err?
        }
        let env = try JSONDecoder().decode(Env.self, from: Data(stdout.utf8))
        guard env.ok, let data = env.data else {
            throw NSError(
                domain: "AttachmentService", code: 1,
                userInfo: [NSLocalizedDescriptionKey:
                    env.error?.message ?? "attachment lookup failed"]
            )
        }
        guard data.exists else {
            throw NSError(
                domain: "AttachmentService", code: 2,
                userInfo: [NSLocalizedDescriptionKey:
                    "attachment file missing on disk: \(data.absolutePath)"]
            )
        }
        let url = URL(fileURLWithPath: data.absolutePath)
        await MainActor.run {
            NSWorkspace.shared.open(url)
        }
    }
}
