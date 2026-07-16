import SwiftUI

struct CompanionListView: View {
    @EnvironmentObject var app: AppState
    @State private var showOnboard = false
    @State private var showPresets = false
    @State private var navPath = NavigationPath()

    var body: some View {
        NavigationStack(path: $navPath) {
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
                Button { showPresets = true } label: { Image(systemName: "sparkles") }
                Button { showOnboard = true } label: { Image(systemName: "plus") }
                Menu {
                    Button("로그아웃", role: .destructive) { app.signOut() }
                } label: {
                    Image(systemName: "person.circle")
                }
            }
            .sheet(isPresented: $showOnboard) {
                OnboardView { created in
                    navPath.append(created)  // 첫 만남 직후 바로 대화로 (기획 #8)
                }
            }
            .sheet(isPresented: $showPresets) {
                PresetsView { adopted in navPath.append(adopted) }  // 데려온 뒤 바로 대화
            }
            .refreshable { await app.loadCompanions() }
            .task { await app.loadCompanions() }
        }
    }

    private func row(_ c: Companion) -> some View {
        HStack(spacing: 12) {
            ZStack {
                // 통화 오브와 같은 시각 언어 — 발광 구체 아바타
                Circle().fill(RadialGradient(
                    colors: [Color(red: 0.80, green: 0.69, blue: 1.0),
                             Color(red: 0.42, green: 0.30, blue: 0.68)],
                    center: .init(x: 0.38, y: 0.32), startRadius: 2, endRadius: 34))
                    .shadow(color: Color(red: 0.71, green: 0.55, blue: 0.95).opacity(0.35),
                            radius: 6)
                Text(String(c.name.prefix(1)))
                    .font(.headline)
                    .foregroundStyle(.white)
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
