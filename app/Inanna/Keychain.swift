import Foundation
import Security

/// 최소 Keychain 래퍼 — 세션 토큰 저장용 (보안 L8: UserDefaults 평문 대체).
/// 이 기기·잠금해제 시에만 접근 가능, 백업에 포함되지 않는다.
enum Keychain {
    private static func query(_ key: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "dev.nonasking.inanna",
         kSecAttrAccount as String: key]
    }

    static func set(_ value: String, for key: String) {
        var q = query(key)
        SecItemDelete(q as CFDictionary)
        guard !value.isEmpty else { return }
        q[kSecValueData as String] = Data(value.utf8)
        q[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        SecItemAdd(q as CFDictionary, nil)
    }

    static func get(_ key: String) -> String {
        var q = query(key)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }
}
