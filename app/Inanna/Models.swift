import Foundation

// 서버 스키마(server/companion/schema.py)와 1:1 — 필요한 필드만 디코드
struct Companion: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var relationship: Relationship
    var voice: Voice

    struct Relationship: Codable, Hashable {
        var template: String
        var callsMe: String?

        enum CodingKeys: String, CodingKey {
            case template
            case callsMe = "calls_me"
        }
    }

    struct Voice: Codable, Hashable {
        var engine: String?
    }
}

struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    var role: String       // user | assistant | error
    var content: String
}

struct Memory: Codable, Identifiable {
    var id: Int
    var content: String
    var layer: String
    var createdAt: Double

    enum CodingKeys: String, CodingKey {
        case id, content, layer
        case createdAt = "created_at"
    }
}

struct HistoryResponse: Codable {
    struct Row: Codable {
        var role: String
        var content: String
    }
    var messages: [Row]
}
