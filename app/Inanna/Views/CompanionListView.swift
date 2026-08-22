import SwiftUI

struct CompanionListView: View {
    @EnvironmentObject var app: AppState
    @State private var showOnboard = false
    @State private var showPresets = false
    @State private var showDeleteAccount = false
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
                    .accessibilityIdentifier("presetsButton")
                Button { showOnboard = true } label: { Image(systemName: "plus") }
                    .accessibilityIdentifier("onboardButton")
                Menu {
                    if let url = URL(string: app.serverURLString + "/static/privacy.html") {
                        Link("개인정보처리방침", destination: url)
                    }
                    Button("로그아웃", role: .destructive) { app.signOut() }
                    // 앱 내 계정 삭제 — App Store 5.1.1(v) 필수 요건
                    Button("계정 삭제", role: .destructive) { showDeleteAccount = true }
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
            .confirmationDialog(
                "계정과 모든 데이터(컴패니언·대화·기억)가 완전히 삭제됩니다. 되돌릴 수 없어요.",
                isPresented: $showDeleteAccount, titleVisibility: .visible
            ) {
                Button("계정 삭제", role: .destructive) {
                    Task { _ = await app.deleteAccount() }
                }
                Button("취소", role: .cancel) {}
            }
        }
    }

    private func row(_ c: Companion) -> some View {
        HStack(spacing: 12) {
            // 플랫 오라 아바타 — 목록은 조용하게, 구체는 통화 화면의 언어 (웹과 동일)
            AuraAvatar(name: c.name, hue: Aura.hue(id: c.id, aura: c.aura))
            VStack(alignment: .leading) {
                Text(c.name).font(.headline)
                Text(relCaption(c))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func relCaption(_ c: Companion) -> String {
        let rel = REL_LABEL[c.relationship.template] ?? c.relationship.template
        let calls = c.relationship.callsMe
        return calls.isEmpty ? rel : "\(rel) · \(calls)"
    }
}
