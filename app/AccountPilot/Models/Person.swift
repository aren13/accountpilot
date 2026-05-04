import Foundation

struct Person: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let surname: String?
    let isOwner: Bool
    let identifiers: [PersonIdentifier]
    let messageCount: Int

    var displayName: String {
        if let s = surname, !s.isEmpty { return "\(name) \(s)" }
        return name
    }

    enum CodingKeys: String, CodingKey {
        case id, name, surname, identifiers
        case isOwner = "is_owner"
        case messageCount = "message_count"
    }
}

struct PersonIdentifier: Codable, Hashable {
    let kind: String
    let value: String
}

struct PeopleListData: Decodable {
    let people: [Person]
}
