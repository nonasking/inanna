import SwiftUI

/// 첫 실행 동의 — 대화가 외부 AI 사업자에게 전송됨을 고지하고 명시적 동의를 받는다
/// (App Store 5.1.2(i)). 동의 전에는 어떤 대화도 전송되지 않는다(서버 설정 전 단계).
struct ConsentView: View {
    var onAgree: () -> Void

    private let privacyURL = URL(string: "https://macbookpro.tail9f8fdd.ts.net/static/privacy.html")

    var body: some View {
        VStack(spacing: 18) {
            Spacer()
            ZStack {
                Circle().fill(RadialGradient(
                    colors: [Color(red: 0.80, green: 0.69, blue: 1.0),
                             Color(red: 0.42, green: 0.30, blue: 0.68)],
                    center: .init(x: 0.38, y: 0.32), startRadius: 4, endRadius: 46))
            }
            .frame(width: 84, height: 84)
            Text("시작하기 전에")
                .font(.title2.bold())
            VStack(alignment: .leading, spacing: 12) {
                Label {
                    Text("컴패니언의 응답을 만들기 위해 대화 내용이 AI 제공자(미국 Anthropic)에게 암호화되어 전송돼요. 음성을 켜면 응답 텍스트가 음성 합성 제공자(ElevenLabs)에도 전송될 수 있어요.")
                } icon: { Image(systemName: "arrow.up.forward.circle") }
                Label {
                    Text("대화와 기억은 Inanna 서버에만 저장되고, 계정 삭제 시 전부 지워져요.")
                } icon: { Image(systemName: "lock.circle") }
                Label {
                    Text("만 14세 미만은 이용할 수 없어요.")
                } icon: { Image(systemName: "person.crop.circle.badge.exclamationmark") }
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .padding(.horizontal, 8)
            if let url = privacyURL {
                Link("개인정보처리방침 전문 보기", destination: url)
                    .font(.footnote)
            }
            Spacer()
            Button {
                onAgree()
            } label: {
                Text("동의하고 시작하기")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            Text("동의하지 않으면 서비스를 이용할 수 없어요.")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(24)
    }
}
