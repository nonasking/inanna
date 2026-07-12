import Foundation
import SwiftUI

/// 앱 전역 상태 — 서버 연결 설정과 컴패니언 목록.
/// 토큰은 Keychain(이 기기·잠금해제 한정), 서버 주소만 UserDefaults.
@MainActor
final class AppState: ObservableObject {
    @AppStorage("serverURL") var serverURLString = ""

    @Published var authToken: String = Keychain.get("authToken") {
        didSet { Keychain.set(authToken, for: "authToken") }
    }

    init() {
        // 구버전(UserDefaults 평문)에서 1회 이관 후 흔적 제거
        if authToken.isEmpty,
           let legacy = UserDefaults.standard.string(forKey: "authToken"),
           !legacy.isEmpty {
            authToken = legacy
        }
        UserDefaults.standard.removeObject(forKey: "authToken")
    }

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
