import SwiftUI

struct CallView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    let companion: Companion

    @StateObject private var call = CallEngine()

    private var stateLabel: String {
        switch call.state {
        case "connecting": return "연결 중…"
        case "idle": return "듣고 있어요"
        case "listening": return "듣는 중…"
        case "thinking": return "생각 중…"
        case "speaking": return "말하는 중 — 탭하면 끼어들 수 있어요"
        default: return ""
        }
    }

    var body: some View {
        ZStack {
            RadialGradient(colors: [Color(red: 0.11, green: 0.09, blue: 0.19), .black],
                           center: .init(x: 0.5, y: 0.35), startRadius: 0, endRadius: 500)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                VStack(spacing: 4) {
                    Text(companion.name).font(.title2.bold())
                    Text(stateLabel).font(.caption).foregroundStyle(.secondary)
                    if let error = call.error {
                        Text(error).font(.caption).foregroundStyle(.red)
                    }
                }
                .padding(.top, 48)

                Orb(state: call.state)
                    .frame(width: 140, height: 140)
                    .padding(.vertical, 56)

                VStack(spacing: 10) {
                    Text(call.userCaption)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text(call.charCaption)
                        .font(.body)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: 480)
                .padding(.horizontal, 24)

                Spacer()

                Button {
                    call.stop()
                    dismiss()
                } label: {
                    Text("통화 종료")
                        .padding(.horizontal, 32)
                        .padding(.vertical, 12)
                        .background(Color(red: 0.29, green: 0.13, blue: 0.19),
                                    in: Capsule())
                }
                .padding(.bottom, 32)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture { call.interrupt() }
        .onAppear {
            if let api = app.api {
                call.start(api: api, companionId: companion.id)
            }
        }
        .onDisappear { call.stop() }
    }
}

/// 상태별로 다르게 숨쉬는 오브 — 웹 통화 화면과 같은 시각 언어
private struct Orb: View {
    let state: String
    @State private var phase = false

    var body: some View {
        Circle()
            .fill(RadialGradient(colors: [Color(red: 0.8, green: 0.69, blue: 1.0),
                                          Color(red: 0.49, green: 0.37, blue: 0.75)],
                                 center: .init(x: 0.38, y: 0.34),
                                 startRadius: 4, endRadius: 70))
            .shadow(color: Color(red: 0.71, green: 0.55, blue: 0.95).opacity(0.4),
                    radius: phase ? 44 : 24)
            .scaleEffect(scale)
            .animation(animation, value: phase)
            .onAppear { phase = true }
            .onChange(of: state) { phase.toggle() }
    }

    private var scale: CGFloat {
        switch state {
        case "listening": return phase ? 1.15 : 1.0
        case "thinking": return phase ? 0.92 : 1.0
        case "speaking": return phase ? 1.08 : 1.0
        default: return 1.0
        }
    }

    private var animation: Animation? {
        switch state {
        case "listening": return .easeInOut(duration: 0.6).repeatForever()
        case "thinking": return .easeInOut(duration: 0.8).repeatForever()
        case "speaking": return .easeInOut(duration: 0.28).repeatForever()
        default: return .easeInOut(duration: 0.3)
        }
    }
}
