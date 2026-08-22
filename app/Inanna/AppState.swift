import Foundation
import SwiftUI

/// 앱 전역 상태 — 서버 연결 설정과 컴패니언 목록.
/// 토큰은 Keychain(이 기기·잠금해제 한정), 서버 주소만 UserDefaults.
@MainActor
final class AppState: ObservableObject {
    /// 기본 서비스 서버 — 앱 사용자는 주소를 몰라도 바로 로그인된다.
    /// 셀프호스팅 사용자는 첫 화면의 '직접 운영하는 서버'에서 바꾼다.
    static let defaultServerURL = "https://inanna.day"

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

    /// 계정+전체 데이터 완전 삭제 (App Store 5.1.1(v)) — 성공하면 로그아웃 상태가 된다.
    func deleteAccount() async -> Bool {
        guard let api else { return false }
        do {
            _ = try await api.send("api/auth/account", method: "DELETE")
            signOut()
            return true
        } catch {
            lastError = "계정 삭제에 실패했어요. 잠시 후 다시 시도해주세요."
            return false
        }
    }

    /// 부적절한 AI 응답 신고 (App Store 1.2 UGC) — 실패해도 조용히 넘어간다.
    func report(companionId: String, content: String) async {
        guard let api else { return }
        _ = try? await api.send("api/report", json: [
            "companion_id": companionId, "content": content, "reason": "in-app report"])
    }

    func signOut() {
        authToken = ""
        companions = []
    }
}
