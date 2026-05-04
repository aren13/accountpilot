import Foundation

/// One row from `accountpilot messages list --json`'s data.messages[].
struct Message: Codable, Identifiable, Hashable {
    let id: Int
    let source: String
    let accountID: Int
    let sentAt: Date
    let threadID: String?
    let subject: String           // empty string for iMessage rows
    let snippet: String
    let fromName: String?
    let fromIdentifier: String?
    let hasAttachments: Bool

    enum CodingKeys: String, CodingKey {
        case id, source, subject, snippet
        case accountID = "account_id"
        case sentAt = "sent_at"
        case threadID = "thread_id"
        case fromName = "from_name"
        case fromIdentifier = "from_identifier"
        case hasAttachments = "has_attachments"
    }
}

struct MessagesListData: Decodable {
    let messages: [Message]
    let nextCursor: Int?

    enum CodingKeys: String, CodingKey {
        case messages
        case nextCursor = "next_cursor"
    }
}

/// One row from `accountpilot messages get --json`'s data.message.
struct MessageDetail: Codable, Identifiable, Hashable {
    let id: Int
    let source: String
    let accountID: Int
    let sentAt: Date
    let receivedAt: Date?
    let threadID: String?
    let bodyText: String
    let bodyHTML: String?
    let direction: String
    let subject: String?
    let email: EmailFields?
    let imessage: IMessageFields?
    let people: [PersonRef]
    let attachments: [Attachment]

    enum CodingKeys: String, CodingKey {
        case id, source, subject, email, imessage, people, attachments, direction
        case accountID = "account_id"
        case sentAt = "sent_at"
        case receivedAt = "received_at"
        case threadID = "thread_id"
        case bodyText = "body_text"
        case bodyHTML = "body_html"
    }

    struct EmailFields: Codable, Hashable {
        let imapUID: Int
        let mailbox: String
        let gmailThreadID: String?
        let inReplyTo: String?
        let labelsJSON: String?

        enum CodingKeys: String, CodingKey {
            case mailbox
            case imapUID = "imap_uid"
            case gmailThreadID = "gmail_thread_id"
            case inReplyTo = "in_reply_to"
            case labelsJSON = "labels_json"
        }
    }

    struct IMessageFields: Codable, Hashable {
        let chatGUID: String
        let service: String
        let isFromMe: Bool
        let isRead: Bool

        enum CodingKeys: String, CodingKey {
            case service
            case chatGUID = "chat_guid"
            case isFromMe = "is_from_me"
            case isRead = "is_read"
        }
    }

    struct PersonRef: Codable, Hashable {
        let role: String          // "from" / "to" / "cc" / "bcc"
        let id: Int
        let name: String
        let identifier: String?
    }

    struct Attachment: Codable, Identifiable, Hashable {
        let id: Int
        let filename: String
        let contentHash: String
        let mimeType: String?
        let sizeBytes: Int

        enum CodingKeys: String, CodingKey {
            case id, filename
            case contentHash = "content_hash"
            case mimeType = "mime_type"
            case sizeBytes = "size_bytes"
        }
    }
}

struct MessageGetData: Decodable {
    let message: MessageDetail
}
