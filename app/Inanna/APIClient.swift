import Foundation

/// Inanna 서버 REST/SSE 클라이언트.
/// 인증: 셀프호스팅 단일 토큰 또는 계정 세션 토큰 — 서버가 둘 다 받는다.
struct APIClient {
    var baseURL: URL
    var token: String

    private func request(_ path: String, method: String = "GET",
                         json: [String: Any]? = nil) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = method
        if !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let json {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: json)
        }
        return req
    }

    private func check(_ resp: URLResponse, _ data: Data) throws {
        guard let http = resp as? HTTPURLResponse else { throw APIError.network }
        guard (200..<300).contains(http.statusCode) else {
            let detail = (try? JSONDecoder().decode([String: String].self, from: data))?["detail"]
            throw APIError.server(status: http.statusCode, message: detail ?? "요청 실패")
        }
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        let (data, resp) = try await URLSession.shared.data(for: request(path))
        try check(resp, data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    func send(_ path: String, method: String = "POST",
              json: [String: Any]? = nil) async throws -> Data {
        let (data, resp) = try await URLSession.shared.data(
            for: request(path, method: method, json: json))
        try check(resp, data)
        return data
    }

    /// SSE 채팅 스트림 — 델타 텍스트를 순서대로 방출
    func chatStream(companionId: String, message: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let req = request("api/chat/\(companionId)", method: "POST",
                                      json: ["message": message])
                    let (bytes, resp) = try await URLSession.shared.bytes(for: req)
                    try check(resp, Data())
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let payload = Data(line.dropFirst(6).utf8)
                        if let obj = try? JSONSerialization.jsonObject(with: payload) as? [String: Any] {
                            if let delta = obj["delta"] as? String {
                                continuation.yield(delta)
                            }
                            if obj["done"] != nil { break }
                            if let err = obj["error"] as? String {
                                throw APIError.server(status: 500, message: err)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// 통화 WebSocket URL (docs/voice-protocol.md)
    func voiceURL(companionId: String) -> URL {
        var comps = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        comps.scheme = comps.scheme == "https" ? "wss" : "ws"
        comps.path = "/api/ws/voice/\(companionId)"
        return comps.url!
    }
}

enum APIError: LocalizedError {
    case network
    case server(status: Int, message: String)

    var errorDescription: String? {
        switch self {
        case .network: return "서버에 연결할 수 없어요"
        case .server(let status, let message):
            return status == 401 ? "인증이 필요해요 — 설정에서 다시 로그인해주세요" : message
        }
    }
}
