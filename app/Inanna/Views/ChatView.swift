import SwiftUI

struct ChatView: View {
    @EnvironmentObject var app: AppState
    @State var companion: Companion

    @State private var messages: [ChatMessage] = []
    @State private var input = ""
    @State private var streaming = false
    @State private var showCall = false
    @State private var showMemories = false
    @State private var showEdit = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(messages) { Bubble(message: $0) }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                }
                .onChange(of: messages) {
                    if let last = messages.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
            inputBar
        }
        .navigationTitle(companion.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if companion.voice.engine?.isEmpty == false {
                Button { showCall = true } label: { Image(systemName: "phone") }
            }
            Button { showMemories = true } label: { Image(systemName: "brain") }
            Button { showEdit = true } label: { Image(systemName: "slider.horizontal.3") }
        }
        .fullScreenCover(isPresented: $showCall, onDismiss: {
            Task { await loadHistory() }  // 통화 턴도 대화 기록 — 종료 후 동기화
        }) {
            CallView(companion: companion)
        }
        .sheet(isPresented: $showMemories) {
            MemoriesView(companion: companion)
        }
        .sheet(isPresented: $showEdit) {
            CompanionEditView(companion: companion) { companion = $0 }
        }
        .task { await loadHistory() }
    }

    private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("메시지", text: $input, axis: .vertical)
                .lineLimit(1...5)
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

    private func loadHistory() async {
        guard let api = app.api else { return }
        do {
            let h = try await api.get("api/chat/\(companion.id)/history", as: HistoryResponse.self)
            messages = h.messages.map { ChatMessage(role: $0.role, content: $0.content) }
        } catch {
            messages.append(ChatMessage(role: "error", content: error.localizedDescription))
        }
    }

    private func send() {
        guard let api = app.api else { return }
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        input = ""
        messages.append(ChatMessage(role: "user", content: text))
        var reply = ChatMessage(role: "assistant", content: "")
        messages.append(reply)
        streaming = true
        Task {
            defer { streaming = false }
            do {
                for try await delta in api.chatStream(companionId: companion.id, message: text) {
                    reply.content += delta
                    messages[messages.count - 1] = reply
                }
            } catch {
                messages.append(ChatMessage(role: "error", content: error.localizedDescription))
            }
        }
    }
}

private struct Bubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == "user" { Spacer(minLength: 48) }
            Text(message.content.isEmpty ? "…" : message.content)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .background(background, in: RoundedRectangle(cornerRadius: 14))
                .foregroundStyle(message.role == "error" ? .red : .primary)
            if message.role != "user" { Spacer(minLength: 48) }
        }
        .id(message.id)
    }

    private var background: Color {
        switch message.role {
        case "user": return Color(red: 0.23, green: 0.18, blue: 0.36)
        case "error": return Color(red: 0.29, green: 0.13, blue: 0.19)
        default: return Color(white: 0.13)
        }
    }
}
