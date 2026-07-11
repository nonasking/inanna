import SwiftUI

/// 기억 열람·정정 — "컴패니언이 나를 어떻게 기억하는지"는 사용자의 것
struct MemoriesView: View {
    @EnvironmentObject var app: AppState
    let companion: Companion

    @State private var memories: [Memory] = []
    @State private var editing: Memory?
    @State private var editText = ""
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let error { Text(error).foregroundStyle(.red) }
                ForEach(memories.reversed()) { memory in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(Date(timeIntervalSince1970: memory.createdAt),
                             format: .dateTime.year().month().day())
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(memory.content)
                    }
                    .swipeActions {
                        Button("삭제", role: .destructive) { remove(memory) }
                        Button("정정") {
                            editing = memory
                            editText = memory.content
                        }
                    }
                }
            }
            .navigationTitle("\(companion.name)의 기억")
            .navigationBarTitleDisplayMode(.inline)
            .overlay {
                if memories.isEmpty && error == nil {
                    ContentUnavailableView("아직 기억이 없어요", systemImage: "brain",
                                           description: Text("대화가 쌓이면 여기서 볼 수 있어요."))
                }
            }
            .task { await load() }
            .sheet(item: $editing) { memory in
                NavigationStack {
                    TextEditor(text: $editText)
                        .padding()
                        .navigationTitle("기억 정정")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .confirmationAction) {
                                Button("저장") { save(memory) }
                            }
                            ToolbarItem(placement: .cancellationAction) {
                                Button("취소") { editing = nil }
                            }
                        }
                }
            }
        }
    }

    private func load() async {
        guard let api = app.api else { return }
        do {
            memories = try await api.get("api/companions/\(companion.id)/memories",
                                         as: [Memory].self)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func save(_ memory: Memory) {
        guard let api = app.api else { return }
        Task {
            do {
                _ = try await api.send("api/memories/\(memory.id)", method: "PUT",
                                       json: ["content": editText])
                editing = nil
                await load()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func remove(_ memory: Memory) {
        guard let api = app.api else { return }
        Task {
            do {
                _ = try await api.send("api/memories/\(memory.id)", method: "DELETE")
                await load()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
