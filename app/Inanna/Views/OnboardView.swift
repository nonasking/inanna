import AVFoundation
import SwiftUI

/// 첫 만남 온보딩 — 폼 대신 대화로 컴패니언이 형성된다 (웹과 같은 3단계).
/// 관계·이름만 명시 선택하고, 성격은 첫 대화에서 추출되어 확인 후 저장된다.
struct OnboardView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    var onCreated: (Companion) -> Void = { _ in }

    enum Step { case relationship, meeting, confirm }
    @State private var step: Step = .relationship

    @State private var templates: [RelTemplate] = []
    @State private var selected: RelTemplate?
    @State private var name = ""
    @State private var callsMe = ""

    @State private var proto: Companion?
    @State private var messages: [ChatMessage] = []
    @State private var turns: [OnboardPayload.Turn] = []
    @State private var input = ""
    @State private var streaming = false
    @State private var userTurns = 0

    @State private var extracted: OnboardExtract?
    @State private var error: String?

    @State private var voices: [VoiceOption] = []
    @State private var selectedVoice: String = ""
    @State private var player: AVAudioPlayer?

    var body: some View {
        NavigationStack {
            Group {
                switch step {
                case .relationship: relationshipStep
                case .meeting: meetingStep
                case .confirm: confirmStep
                }
            }
            .navigationTitle(step == .relationship ? "새로운 만남"
                             : "\(name)\(step == .meeting ? "와의 첫 만남" : "")")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("닫기") { dismiss() }
                }
            }
            .task {
                guard let api = app.api else { return }
                templates = (try? await api.get("api/templates", as: [RelTemplate].self)) ?? []
            }
        }
    }

    // MARK: 1단계 — 관계·이름 (명시적 계약)

    private var relationshipStep: some View {
        Form {
            Section {
                ForEach(templates) { tpl in
                    Button {
                        selected = tpl
                    } label: {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(tpl.name).foregroundStyle(.primary)
                                if let d = tpl.description, !d.isEmpty {
                                    Text(d).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            if selected?.id == tpl.id {
                                Image(systemName: "checkmark").foregroundStyle(.tint)
                            }
                        }
                    }
                }
            } header: {
                Text("어떤 사이가 되고 싶나요?")
            } footer: {
                Text("나머지는 만나서 알아가면 돼요.")
            }
            Section {
                TextField("이름을 지어주세요", text: $name)
                TextField("나를 부르는 호칭 (비우면 대화에서 정해져요)", text: $callsMe)
            }
            Button("만나러 가기") { startMeeting() }
                .disabled(selected == nil || name.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    private func startMeeting() {
        guard let tpl = selected else { return }
        let cleanName = name.trimmingCharacters(in: .whitespaces)
        name = cleanName
        var c = Companion(id: slug(cleanName), name: cleanName,
                          relationship: .init(template: tpl.id))
        c.relationship.callsMe = callsMe.trimmingCharacters(in: .whitespaces)
        proto = c
        step = .meeting
        Task { await companionTurn() }   // 컴패니언이 먼저 인사
    }

    private func slug(_ s: String) -> String {
        let ascii = s.lowercased().unicodeScalars
            .map { CharacterSet.alphanumerics.contains($0) ? String($0) : "-" }
            .joined().trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return ascii.isEmpty ? "c-\(Int(Date().timeIntervalSince1970) % 1000000)" : ascii
    }

    // MARK: 2단계 — 첫 만남 대화

    private var meetingStep: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(messages) { OnboardBubble(message: $0) }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                }
                .onChange(of: messages) {
                    if let last = messages.last { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            if let error {
                Text(error).font(.caption).foregroundStyle(.red)
            }
            if userTurns >= 3 && !streaming {
                Button("이 정도면 서로 알 것 같아요") { finishMeeting() }
                    .buttonStyle(.borderedProminent)
                    .padding(.vertical, 6)
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("편하게 대답해보세요", text: $input, axis: .vertical)
                    .lineLimit(1...4)
                    .padding(10)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                Button {
                    send()
                } label: {
                    Image(systemName: "arrow.up.circle.fill").font(.system(size: 30))
                }
                .disabled(streaming || input.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        input = ""
        messages.append(ChatMessage(role: "user", content: text))
        turns.append(.init(role: "user", content: text))
        userTurns += 1
        Task { await companionTurn() }
    }

    private func companionTurn() async {
        guard let api = app.api, let proto else { return }
        streaming = true
        error = nil
        defer { streaming = false }
        var reply = ChatMessage(role: "assistant", content: "")
        messages.append(reply)
        do {
            let payload = OnboardPayload(companion: proto, messages: turns)
            for try await delta in api.sseStream(path: "api/onboard/chat", body: payload) {
                reply.content += delta
                messages[messages.count - 1] = reply
            }
            turns.append(.init(role: "assistant", content: reply.content))
        } catch {
            messages.removeLast()
            self.error = error.localizedDescription
        }
    }

    // MARK: 3단계 — 추출·확인

    private func finishMeeting() {
        guard let api = app.api, var c = proto else { return }
        streaming = true
        error = nil
        Task {
            defer { streaming = false }
            do {
                let data = try await api.post("api/onboard/extract",
                                              body: OnboardPayload(companion: c, messages: turns))
                let x = try JSONDecoder().decode(OnboardExtract.self, from: data)
                c.persona.traits = x.traits
                c.persona.speechQuirks = x.speechQuirks
                c.persona.description = x.description
                c.relationship.speechLevel = x.speechLevel
                if c.relationship.callsMe.isEmpty { c.relationship.callsMe = x.callsMe }
                proto = c
                extracted = x
                step = .confirm
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private var confirmStep: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Text(extracted?.confirm ?? "나 이런 느낌인 것 같아. 맞지?")
                        .font(.body)
                    let traits = (extracted?.traits ?? [:])
                        .filter { $0.value >= 0.6 }.keys.sorted().joined(separator: " · ")
                    if !traits.isEmpty {
                        Text("성격: \(traits)").font(.caption).foregroundStyle(.secondary)
                    }
                    if let d = extracted?.description, !d.isEmpty {
                        Text(d).font(.caption).foregroundStyle(.secondary)
                    }
                }
            } header: {
                Text("\(name)의 이야기")
            } footer: {
                if let error { Text(error).foregroundStyle(.red) }
            }
            Section {
                ForEach(voices) { v in
                    Button {
                        selectedVoice = v.id
                        Task { await preview(v.id) }
                    } label: {
                        HStack {
                            Image(systemName: "play.circle")
                            Text(v.name).foregroundStyle(.primary)
                            Spacer()
                            if selectedVoice == v.id {
                                Image(systemName: "checkmark").foregroundStyle(.tint)
                            }
                        }
                    }
                }
            } header: {
                Text("내 목소리도 골라줄래?")
            } footer: {
                Text("듣고 고르거나, 나중에 편집에서 바꿀 수 있어요.")
            }
            Button("응, 그런 것 같아 — 시작하기") { complete() }
                .disabled(streaming)
        }
        .task {
            guard let api = app.api, voices.isEmpty else { return }
            let all = (try? await api.get("api/voices?engine=edge",
                                          as: [VoiceOption].self)) ?? []
            voices = all.filter { $0.lang == "ko" }.prefix(3).map { $0 }
        }
    }

    private func preview(_ voiceId: String) async {
        guard let api = app.api else { return }
        struct Req: Codable {
            var voice: Companion.Voice
            var text: String
        }
        var v = Companion.Voice()
        v.engine = "edge"
        v.voiceId = voiceId
        let line = String((extracted?.confirm ?? "안녕, 내 목소리 어때?").prefix(80))
        if let data = try? await api.post("api/tts-preview",
                                          body: Req(voice: v, text: line)) {
            player = try? AVAudioPlayer(data: data)
            player?.play()
        }
    }

    private func complete() {
        guard let api = app.api, var proto else { return }
        if !selectedVoice.isEmpty {
            proto.voice.engine = "edge"
            proto.voice.voiceId = selectedVoice
            self.proto = proto
        }
        streaming = true
        Task {
            defer { streaming = false }
            do {
                var payload = OnboardPayload(companion: proto, messages: turns)
                payload.firstMemory = extracted?.firstMemory ?? ""
                try await api.post("api/onboard/complete", body: payload)
                await app.loadCompanions()
                onCreated(proto)
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

private struct OnboardBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == "user" { Spacer(minLength: 48) }
            Text(message.content.isEmpty ? "…" : message.content)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .background(message.role == "user"
                            ? Color(red: 0.23, green: 0.18, blue: 0.36)
                            : Color(white: 0.13),
                            in: RoundedRectangle(cornerRadius: 14))
            if message.role != "user" { Spacer(minLength: 48) }
        }
        .id(message.id)
    }
}
