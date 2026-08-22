import Foundation

/// Inanna 서버 REST/SSE 클라이언트.
/// 인증: 셀프호스팅 단일 토큰 또는 계정 세션 토큰 — 서버가 둘 다 받는다.
struct APIClient {
    var baseURL: URL
    var token: String

    private func url(for path: String) -> URL {
        // appendingPathComponent는 '?'를 %3F로 이스케이프한다 — 쿼리는 분리해 붙인다
        let parts = path.split(separator: "?", maxSplits: 1)
        var url = baseURL.appendingPathComponent(String(parts[0]))
        if parts.count == 2,
           var comps = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            comps.percentEncodedQuery = String(parts[1])
            url = comps.url ?? url
        }
        return url
    }

    private func request(_ path: String, method: String = "GET",
                         json: [String: Any]? = nil) -> URLRequest {
        var req = URLRequest(url: url(for: path))
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

    /// 서버 에러 본문에서 사람이 읽을 문구를 뽑는다.
    /// FastAPI는 detail을 문자열(HTTPException)로도, 배열(검증 실패)로도 준다 —
    /// 문자열만 기대하면 검증 실패 때 이유가 통째로 사라진다.
    private func errorMessage(_ data: Data, status: Int) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let s = obj["detail"] as? String, !s.isEmpty { return s }
            if let arr = obj["detail"] as? [[String: Any]],
               let first = arr.first, let msg = first["msg"] as? String { return msg }
        }
        switch status {
        case 401: return "로그인이 필요해요"
        case 402: return "사용량을 다 썼어요"
        case 403: return "권한이 없어요"
        case 404: return "찾을 수 없어요"
        case 413, 422: return "입력이 너무 길거나 형식이 올바르지 않아요"
        case 429: return "잠시 후 다시 시도해주세요"
        default: return "요청 실패"
        }
    }

    private func check(_ resp: URLResponse, _ data: Data) throws {
        guard let http = resp as? HTTPURLResponse else { throw APIError.network }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.server(status: http.statusCode,
                                  message: errorMessage(data, status: http.statusCode))
        }
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        let (data, resp) = try await URLSession.shared.data(for: request(path))
        try check(resp, data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    /// Codable 본문 POST — 컴패니언 저장·온보딩 등 전체 스키마 왕복용
    @discardableResult
    func post<Body: Encodable>(_ path: String, body: Body) async throws -> Data {
        var req = request(path, method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        try check(resp, data)
        return data
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
        sseStream(path: "api/chat/\(companionId)",
                  bodyData: try? JSONSerialization.data(withJSONObject: ["message": message]))
    }

    /// Codable 본문의 SSE 스트림 (온보딩 등)
    func sseStream<Body: Encodable>(path: String, body: Body) -> AsyncThrowingStream<String, Error> {
        sseStream(path: path, bodyData: try? JSONEncoder().encode(body))
    }

    private func sseStream(path: String, bodyData: Data?) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var req = request(path, method: "POST")
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.httpBody = bodyData
                    let (bytes, resp) = try await URLSession.shared.bytes(for: req)
                    // 실패 응답이면 본문을 마저 읽어 서버 문구를 살린다 — 빈 Data로 검사하면
                    // 쿼터·정지·레이트리밋 안내가 전부 "요청 실패"로 뭉개진다.
                    if let http = resp as? HTTPURLResponse,
                       !(200..<300).contains(http.statusCode) {
                        var body = Data()
                        for try await b in bytes { body.append(b) }
                        throw APIError.server(status: http.statusCode,
                                              message: errorMessage(body, status: http.statusCode))
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let payload = Data(line.dropFirst(6).utf8)
                        if let obj = try? JSONSerialization.jsonObject(with: payload) as? [String: Any] {
                            if let delta = obj["delta"] as? String {
                                continuation.yield(delta)
                            }
                            if obj["done"] != nil { break }
                            if let err = obj["error"] as? String {
                                let quota = (obj["kind"] as? String) == "quota"
                                throw APIError.server(status: quota ? 402 : 500,
                                                      message: err)
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
            // 서버가 사람이 읽을 문구를 주면 그것을 쓴다 — 로그인 실패(비밀번호 오류)에
            // "설정에서 다시 로그인" 같은 엉뚱한 안내가 뜨지 않게.
            if !message.isEmpty && message != "요청 실패" { return message }
            return status == 401 ? "인증이 필요해요 — 설정에서 다시 로그인해주세요" : message
        }
    }
}
