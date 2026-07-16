import SwiftUI

/// 추천 컴패니언(프리셋) — 체험 대화 후 '데려오기'. (웹과 같은 흐름)
struct PresetsView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    var onAdopted: (Companion) -> Void = { _ in }

    @State private var presets: [PresetSummary] = []

    private let relLabel = ["lover": "연인", "friend": "친구", "younger-sibling": "동생",
                            "older-sibling": "누나/형", "mother": "어머니", "father": "아버지",
                            "child": "자식", "assistant": "비서"]

    var body: some View {
        NavigationStack {
            List(presets) { p in
                NavigationLink {
                    PresetChatView(preset: p, onAdopted: { c in
                        onAdopted(c); dismiss()
                    })
                } label: {
                    HStack(spacing: 12) {
                        ZStack {
                            Circle().fill(RadialGradient(
                                colors: [Color(red: 0.80, green: 0.69, blue: 1.0),
                                         Color(red: 0.42, green: 0.30, blue: 0.68)],
                                center: .init(x: 0.38, y: 0.32), startRadius: 2, endRadius: 30))
                            Text(String(p.name.prefix(1))).font(.headline).foregroundStyle(.white)
                        }.frame(width: 42, height: 42)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(p.name)  ·  \(relLabel[p.template] ?? p.template)")
                                .font(.headline)
                            if let c = p.concept, !c.isEmpty {
                                Text(c).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                            }
                        }
                    }
                }
            }
            .listStyle(.plain)
            .navigationTitle("추천 컴패니언")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("닫기") { dismiss() } }
            }
            .task {
                guard let api = app.api else { return }
                presets = (try? await api.get("api/presets", as: [PresetSummary].self)) ?? []
            }
        }
    }
}

struct PresetSummary: Codable, Identifiable {
    var id: String
    var name: String
    var template: String
    var concept: String?
}

/// 프리셋 체험 대화 (무저장) + 데려오기
private struct PresetChatView: View {
    @EnvironmentObject var app: AppState
    let preset: PresetSummary
    var onAdopted: (Companion) -> Void

    @State private var messages: [ChatMessage] = []
    @State private var input = ""
    @State private var streaming = false
    @State private var started = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(messages) { PresetBubble(message: $0) }
                    }
                    .padding(.horizontal, 14).padding(.vertical, 8)
                }
                .onChange(of: messages) {
                    if let last = messages.last { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("편하게 말 걸어보세요 (저장되지 않아요)", text: $input, axis: .vertical)
                    .lineLimit(1...4).padding(10)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                Button { send() } label: {
                    Image(systemName: "arrow.up.circle.fill").font(.system(size: 30))
                }
                .disabled(streaming || input.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
        }
        .navigationTitle("\(preset.name) 체험")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("데려오기") { adopt() }.disabled(streaming)
            }
        }
        .task {
            guard !started else { return }
            started = true
            await turn()   // 첫 인사
        }
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        input = ""
        messages.append(ChatMessage(role: "user", content: text))
        Task { await turn() }
    }

    private func turn() async {
        guard let api = app.api else { return }
        streaming = true
        defer { streaming = false }
        let history = messages.map { OnboardPayload.Turn(role: $0.role, content: $0.content) }
        var reply = ChatMessage(role: "assistant", content: "")
        messages.append(reply)
        do {
            let body = PreviewBody(messages: history)
            for try await d in api.sseStream(path: "api/presets/\(preset.id)/preview", body: body) {
                reply.content += d
                messages[messages.count - 1] = reply
            }
        } catch {
            messages.removeLast()
            messages.append(ChatMessage(role: "error", content: error.localizedDescription))
        }
    }

    private func adopt() {
        guard let api = app.api else { return }
        Task {
            do {
                let data = try await api.send("api/presets/\(preset.id)/adopt", method: "POST")
                let r = try JSONDecoder().decode([String: String].self, from: data)
                await app.loadCompanions()
                if let id = r["id"], let c = app.companions.first(where: { $0.id == id }) {
                    onAdopted(c)
                }
            } catch { /* 표시는 생략 — 재시도 가능 */ }
        }
    }

    struct PreviewBody: Codable { var messages: [OnboardPayload.Turn] }
}

private struct PresetBubble: View {
    let message: ChatMessage
    var body: some View {
        HStack {
            if message.role == "user" { Spacer(minLength: 48) }
            Text(message.content.isEmpty ? "…" : message.content)
                .padding(.horizontal, 13).padding(.vertical, 9)
                .background(message.role == "user"
                            ? Color(red: 0.23, green: 0.18, blue: 0.36) : Color(white: 0.13),
                            in: RoundedRectangle(cornerRadius: 14))
                .foregroundStyle(message.role == "error" ? .red : .primary)
            if message.role != "user" { Spacer(minLength: 48) }
        }.id(message.id)
    }
}
