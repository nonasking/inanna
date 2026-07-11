import Foundation
import SwiftUI

/// 앱 전역 상태 — 서버 연결 설정과 컴패니언 목록.
/// 토큰은 v1에서 UserDefaults (제품 출시 전 Keychain으로 이동할 것).
@MainActor
final class AppState: ObservableObject {
    @AppStorage("serverURL") var serverURLString = ""
    @AppStorage("authToken") var authToken = ""

    @Published var companions: [Companion] = []
    @Published var lastError: String?

    var isConfigured: Bool { !serverURLString.isEmpty && !authToken.isEmpty }

    var api: APIClient? {
        guard let url = URL(string: serverURLString) else { return nil }
        return APIClient(baseURL: url, token: authToken)
    }

    func loadCompanions() async {
        guard let api else { return }
        do {
            companions = try await api.get("api/companions", as: [Companion].self)
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// 연결 검증 — 설정 화면에서 저장 전에 호출
    func verify(url: String, token: String) async -> String? {
        guard let base = URL(string: url) else { return "주소 형식이 올바르지 않아요" }
        let api = APIClient(baseURL: base, token: token)
        do {
            _ = try await api.get("api/companions", as: [Companion].self)
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    func login(url: String, email: String, password: String) async -> String? {
        guard let base = URL(string: url) else { return "주소 형식이 올바르지 않아요" }
        let api = APIClient(baseURL: base, token: "")
        do {
            let data = try await api.send("api/auth/login",
                                          json: ["email": email, "password": password])
            let obj = try JSONDecoder().decode([String: String].self, from: data)
            guard let token = obj["token"] else { return "로그인 응답이 올바르지 않아요" }
            serverURLString = url
            authToken = token
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    func signOut() {
        authToken = ""
        companions = []
    }
}
