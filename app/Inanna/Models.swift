import Foundation

// 서버 스키마(server/companion/schema.py)와 1:1 — 편집 화면이 전체를 왕복하므로
// 모든 필드를 보존해야 저장 시 데이터가 유실되지 않는다.
struct Companion: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var relationship: Relationship
    var persona: Persona = Persona()
    var voice: Voice = Voice()
    var model: ModelOverride = ModelOverride()

    struct Relationship: Codable, Hashable {
        var template: String
        var callsMe: String = ""
        var iCall: String = ""
        var speechLevel: String = "banmal"
        var intimacy: Double = 0.7
        var backstory: String = ""

        enum CodingKeys: String, CodingKey {
            case template, intimacy, backstory
            case callsMe = "calls_me"
            case iCall = "i_call"
            case speechLevel = "speech_level"
        }
    }

    struct Persona: Codable, Hashable {
        var traits: [String: Double] = [:]
        var speechQuirks: [String] = []
        var description: String = ""
        var exampleDialogue: String = ""
        var firstMessage: String = ""
        var lorebook: [LorebookEntry] = []

        enum CodingKeys: String, CodingKey {
            case traits, description, lorebook
            case speechQuirks = "speech_quirks"
            case exampleDialogue = "example_dialogue"
            case firstMessage = "first_message"
        }
    }

    struct LorebookEntry: Codable, Hashable {
        var keys: [String]
        var content: String
    }

    struct Voice: Codable, Hashable {
        var engine: String? = ""
        var voiceId: String = ""
        var model: String = ""
        var referenceAudio: String = ""
        var refText: String = ""
        var speed: Double = 1.0

        enum CodingKeys: String, CodingKey {
            case engine, model, speed
            case voiceId = "voice_id"
            case referenceAudio = "reference_audio"
            case refText = "ref_text"
        }
    }

    struct ModelOverride: Codable, Hashable {
        var provider: String = ""
        var name: String = ""
    }
}

struct RelTemplate: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var description: String?
}

// 온보딩 — /api/onboard/{chat,extract,complete} 요청·응답
struct OnboardPayload: Codable {
    var companion: Companion
    var messages: [Turn]
    var firstMemory: String = ""

    struct Turn: Codable {
        var role: String
        var content: String
    }

    enum CodingKeys: String, CodingKey {
        case companion, messages
        case firstMemory = "first_memory"
    }
}

struct OnboardExtract: Codable {
    var traits: [String: Double]
    var speechQuirks: [String]
    var description: String
    var callsMe: String
    var speechLevel: String
    var confirm: String
    var firstMemory: String

    enum CodingKeys: String, CodingKey {
        case traits, description, confirm
        case speechQuirks = "speech_quirks"
        case callsMe = "calls_me"
        case speechLevel = "speech_level"
        case firstMemory = "first_memory"
    }
}

struct VoiceOption: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var gender: String?
    var lang: String?
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
