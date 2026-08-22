import SwiftUI

/// 추천 컴패니언(프리셋) — 체험 대화 후 '데려오기'. (웹과 같은 흐름)
struct PresetsView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    var onAdopted: (Companion) -> Void = { _ in }

    @State private var presets: [PresetSummary] = []
    @State private var listError: String?

    private func loadPresets() async {
        guard let api = app.api else { return }
        do {
            presets = try await api.get("api/presets", as: [PresetSummary].self)
            listError = presets.isEmpty ? "추천 컴패니언이 없어요." : nil
        } catch {
            listError = error.localizedDescription
        }
    }

    var body: some View {
        NavigationStack {
            List(presets) { p in
                NavigationLink {
                    PresetChatView(preset: p, onAdopted: { c in
                        onAdopted(c); dismiss()
                    })
                } label: {
                    HStack(spacing: 12) {
                        AuraAvatar(name: p.name, hue: Aura.hue(id: p.id, aura: p.aura),
                                   size: 42)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(p.name)  ·  \(REL_LABEL[p.template] ?? p.template)")
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
            .overlay {
                // 빈 화면에 이유 없이 갇히지 않게 (로드 실패·빈 목록 모두 안내)
                if presets.isEmpty {
                    ContentUnavailableView(
                        listError == nil ? "불러오는 중…" : "불러오지 못했어요",
                        systemImage: listError == nil ? "sparkles" : "exclamationmark.triangle",
                        description: Text(listError ?? ""))
                }
            }
            .task { await loadPresets() }
        }
    }
}

struct PresetSummary: Codable, Identifiable {
    var id: String
    var name: String
    var template: String
    var concept: String?
    var aura: Int?
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
    @State private var adoptError: String?
    @State private var adopting = false

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
                Button(adopting ? "데려오는 중…" : "데려오기") { adopt() }
                    .disabled(streaming || adopting)
            }
        }
        .alert("데려오지 못했어요", isPresented: .constant(adoptError != nil)) {
            Button("확인") { adoptError = nil }
        } message: {
            Text(adoptError ?? "")
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
        adopting = true
        Task {
            defer { adopting = false }
            do {
                let data = try await api.send("api/presets/\(preset.id)/adopt", method: "POST")
                // 응답은 {ok, id, name} — id·name만 읽는다 (ok는 Bool이라 [String:String] 디코딩 불가)
                let r = try JSONDecoder().decode(AdoptResult.self, from: data)
                await app.loadCompanions()
                if let c = app.companions.first(where: { $0.id == r.id }) {
                    onAdopted(c)
                } else {
                    // 데려오기는 성공했는데 목록 갱신이 늦은 경우 — 버튼이 먹통이 되지 않게
                    onAdopted(Companion(id: r.id, name: r.name,
                                        relationship: .init(template: preset.template)))
                }
            } catch {
                adoptError = error.localizedDescription   // 조용히 멈추지 않게 표시
            }
        }
    }

    struct AdoptResult: Codable { var id: String; var name: String }
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
