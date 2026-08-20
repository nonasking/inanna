import SwiftUI

/// 오라 — 컴패니언 고유의 빛깔 (웹 app.js의 오라 시스템과 동일 규약).
/// 밤의 가족 대역(인디고 250° → 웜 로즈 20°) 안에서 hue 하나로 정체성을 만든다.
/// hue의 홀짝이 밝기 단(짝수=깊은 68%, 홀수=밝은 80%)을 정한다.
/// aura 필드가 없으면 id의 FNV-1a 해시로 대역 안에서 유도 — 웹과 같은 색이 나온다.
enum Aura {
    static func hue(id: String, aura: Int?) -> Int {
        if let aura { return ((aura % 360) + 360) % 360 }
        var h: UInt32 = 0x811c9dc5
        for u in id.utf16 {                       // JS charCodeAt와 동일 (UTF-16)
            h ^= UInt32(u)
            h = h &* 0x01000193
        }
        h ^= h >> 16
        h = h &* 0x85ebca6b
        h ^= h >> 13
        return (250 + Int(h % 130)) % 360
    }

    static func core(_ hue: Int) -> Color {
        let l = hue % 2 == 1 ? 0.80 : 0.68
        return oklch(l, 0.11, Double(hue))
    }

    static func deep(_ hue: Int) -> Color {
        let l = hue % 2 == 1 ? 0.50 : 0.38
        return oklch(l, 0.13, Double((hue + 40) % 360))
    }

    static func text(_ hue: Int) -> Color { oklch(0.82, 0.09, Double(hue)) }

    /// 통화 오브의 유대감 색 혼합용 RGB 튜플 (0~1)
    static func coreRGB(_ hue: Int) -> (Double, Double, Double) {
        oklchRGB(hue % 2 == 1 ? 0.80 : 0.68, 0.11, Double(hue))
    }

    static func deepRGB(_ hue: Int) -> (Double, Double, Double) {
        oklchRGB(hue % 2 == 1 ? 0.50 : 0.38, 0.13, Double((hue + 40) % 360))
    }

    private static func oklch(_ l: Double, _ c: Double, _ hDeg: Double) -> Color {
        let (r, g, b) = oklchRGB(l, c, hDeg)
        return Color(red: r, green: g, blue: b)
    }

    /// OKLCH → sRGB (웹 CSS oklch()와 같은 좌표계) — SwiftUI엔 없어서 직접 변환.
    private static func oklchRGB(_ l: Double, _ c: Double, _ hDeg: Double) -> (Double, Double, Double) {
        let h = hDeg * .pi / 180
        let a = c * cos(h), b = c * sin(h)
        let l_ = pow(l + 0.3963377774 * a + 0.2158037573 * b, 3)
        let m_ = pow(l - 0.1055613458 * a - 0.0638541728 * b, 3)
        let s_ = pow(l - 0.0894841775 * a - 1.2914855480 * b, 3)
        let r = +4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
        let g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
        let bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
        func gamma(_ x: Double) -> Double {
            let v = max(0, min(1, x))
            return v <= 0.0031308 ? 12.92 * v : 1.055 * pow(v, 1 / 2.4) - 0.055
        }
        return (gamma(r), gamma(g), gamma(bl))
    }
}

/// 관계 템플릿의 한국어 표시명 (웹 REL_LABEL과 동일)
let REL_LABEL: [String: String] = [
    "lover": "연인", "friend": "친구", "younger-sibling": "동생",
    "older-sibling": "누나/형", "mother": "어머니", "father": "아버지",
    "child": "자식", "assistant": "비서",
]

/// 플랫 오라 아바타 — 목록은 조용한 틴트+이니셜 (웹과 동일한 시각 언어)
struct AuraAvatar: View {
    let name: String
    let hue: Int
    var size: CGFloat = 44

    var body: some View {
        ZStack {
            Circle().fill(Aura.core(hue).opacity(0.16))
            Text(String(name.prefix(1)))
                .font(.system(size: size * 0.43, weight: .bold))
                .foregroundStyle(Aura.text(hue))
        }
        .frame(width: size, height: size)
    }
}
