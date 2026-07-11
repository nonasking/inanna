import SwiftUI

struct CompanionListView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        NavigationStack {
            Group {
                if app.companions.isEmpty {
                    ContentUnavailableView(
                        "아직 컴패니언이 없어요",
                        systemImage: "sparkles",
                        description: Text(app.lastError ?? "웹 빌더에서 첫 컴패니언을 만들어보세요."))
                } else {
                    List(app.companions) { companion in
                        NavigationLink(value: companion) {
                            row(companion)
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Inanna")
            .navigationDestination(for: Companion.self) { ChatView(companion: $0) }
            .toolbar {
                Menu {
                    Button("로그아웃", role: .destructive) { app.signOut() }
                } label: {
                    Image(systemName: "person.circle")
                }
            }
            .refreshable { await app.loadCompanions() }
            .task { await app.loadCompanions() }
        }
    }

    private func row(_ c: Companion) -> some View {
        HStack(spacing: 12) {
            ZStack {
                Circle().fill(.tint.opacity(0.35))
                Text(String(c.name.prefix(1))).font(.headline)
            }
            .frame(width: 44, height: 44)
            VStack(alignment: .leading) {
                Text(c.name).font(.headline)
                Text("\(c.relationship.template) · \(c.relationship.callsMe ?? "")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
