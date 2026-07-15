import SwiftUI

/// 컴패니언 편집 — 성격·관계·보이스·AI 모델. (생성과 참조 오디오 업로드는 웹 빌더)
struct CompanionEditView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss

    @State var companion: Companion
    var onSaved: (Companion) -> Void = { _ in }
    var onDeleted: () -> Void = {}

    @State private var voices: [VoiceOption] = []
    @State private var busy = false
    @State private var error: String?
    @State private var confirmFarewell = false

    private let speechLevels = [("banmal", "반말"), ("jondaemal", "존댓말"), ("mixed", "섞임")]
    private let engines = [("", "없음 (텍스트만)"), ("edge", "프리셋 보이스"),
                           ("sovits", "보이스 클로닝"), ("elevenlabs", "감정 표현 (ElevenLabs)")]
    private let elModels = [("", "기본 (v2 — 안정)"), ("eleven_v3", "v3 — 감정 최대"),
                            ("eleven_turbo_v2_5", "Turbo — 균형"),
                            ("eleven_flash_v2_5", "Flash — 저지연")]
    private let providers = [("", "기본 (서버 설정)"), ("anthropic", "Anthropic (Claude)"),
                             ("ollama", "Ollama (로컬)"), ("openai", "OpenAI 호환")]

    var body: some View {
        NavigationStack {
            Form {
                Section("관계") {
                    TextField("나를 부르는 호칭", text: $companion.relationship.callsMe)
                    Picker("말투", selection: $companion.relationship.speechLevel) {
                        ForEach(speechLevels, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    VStack(alignment: .leading) {
                        Text("거리감 \(Int(companion.relationship.intimacy * 100))")
                            .font(.caption).foregroundStyle(.secondary)
                        Slider(value: $companion.relationship.intimacy, in: 0...1)
                    }
                    TextField("관계 서사", text: $companion.relationship.backstory,
                              axis: .vertical)
                        .lineLimit(2...5)
                }

                Section("성격") {
                    ForEach(companion.persona.traits.keys.sorted(), id: \.self) { key in
                        VStack(alignment: .leading) {
                            Text("\(key) \(Int((companion.persona.traits[key] ?? 0.5) * 10))/10")
                                .font(.caption).foregroundStyle(.secondary)
                            Slider(value: Binding(
                                get: { companion.persona.traits[key] ?? 0.5 },
                                set: { companion.persona.traits[key] = $0 }), in: 0...1)
                        }
                    }
                    TextField("자유 설정 (성격·배경·좋아하는 것)",
                              text: $companion.persona.description, axis: .vertical)
                        .lineLimit(3...8)
                    TextField("말버릇 (쉼표로 구분)", text: Binding(
                        get: { companion.persona.speechQuirks.joined(separator: ", ") },
                        set: { companion.persona.speechQuirks = $0.split(separator: ",")
                                .map { $0.trimmingCharacters(in: .whitespaces) }
                                .filter { !$0.isEmpty } }), axis: .vertical)
                        .lineLimit(1...4)
                }

                Section("목소리") {
                    Picker("엔진", selection: Binding(
                        get: { companion.voice.engine ?? "" },
                        set: { companion.voice.engine = $0; Task { await loadVoices() } })) {
                        ForEach(engines, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    if companion.voice.engine == "edge" || companion.voice.engine == "elevenlabs" {
                        Picker("보이스", selection: $companion.voice.voiceId) {
                            if !voices.contains(where: { $0.id == companion.voice.voiceId }) {
                                Text("(현재 설정 유지)").tag(companion.voice.voiceId)
                            }
                            ForEach(voices) { Text($0.name).tag($0.id) }
                        }
                    }
                    if companion.voice.engine == "elevenlabs" {
                        Picker("보이스 모델", selection: $companion.voice.model) {
                            ForEach(elModels, id: \.0) { Text($0.1).tag($0.0) }
                        }
                    }
                    if companion.voice.engine == "sovits" {
                        LabeledContent("참조 오디오",
                                       value: companion.voice.referenceAudio.isEmpty
                                       ? "없음 (웹 빌더에서 업로드)" : "등록됨")
                    }
                    if companion.voice.engine?.isEmpty == false {
                        VStack(alignment: .leading) {
                            Text("말 속도 \(companion.voice.speed, format: .number.precision(.fractionLength(2)))")
                                .font(.caption).foregroundStyle(.secondary)
                            Slider(value: $companion.voice.speed, in: 0.7...1.3)
                        }
                    }
                }

                Section {
                    Picker("LLM", selection: $companion.model.provider) {
                        ForEach(providers, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    if !companion.model.provider.isEmpty {
                        TextField("모델 이름 (비우면 기본)", text: $companion.model.name)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                } header: {
                    Text("AI 모델")
                } footer: {
                    Text("어떤 모델을 골라도 기억과 관계는 동일하게 유지돼요."
                         + (error.map { "\n⚠ \($0)" } ?? ""))
                        .foregroundStyle(error == nil ? Color.secondary : .red)
                }

                Section {
                    Button("작별하기", role: .destructive) { confirmFarewell = true }
                        .frame(maxWidth: .infinity)
                } footer: {
                    Text("함께한 기억이 모두 사라지고, 되돌릴 수 없어요.")
                }
            }
            .navigationTitle("\(companion.name) 편집")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(busy ? "저장 중…" : "저장") { save() }.disabled(busy)
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("취소") { dismiss() }
                }
            }
            .task { await loadVoices() }
            .confirmationDialog("\(companion.name)와 작별할까요?",
                                isPresented: $confirmFarewell, titleVisibility: .visible) {
                Button("작별하기", role: .destructive) { farewell() }
                Button("취소", role: .cancel) {}
            } message: {
                Text("함께한 기억이 모두 사라지고, 되돌릴 수 없어요.")
            }
        }
    }

    private func farewell() {
        guard let api = app.api else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                _ = try await api.send("api/companions/\(companion.id)", method: "DELETE")
                await app.loadCompanions()
                onDeleted()
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func loadVoices() async {
        guard let api = app.api,
              let engine = companion.voice.engine,
              engine == "edge" || engine == "elevenlabs" else { return }
        voices = (try? await api.get("api/voices?engine=\(engine)",
                                     as: [VoiceOption].self)) ?? []
    }

    private func save() {
        guard let api = app.api else { return }
        busy = true
        error = nil
        Task {
            defer { busy = false }
            do {
                try await api.post("api/companions", body: companion)
                onSaved(companion)
                await app.loadCompanions()
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
