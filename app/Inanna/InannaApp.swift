import SwiftUI

@main
struct InannaApp: App {
    @StateObject private var app = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .preferredColorScheme(.dark)
                .tint(Color(red: 0.71, green: 0.55, blue: 0.95))  // 웹과 같은 보라
        }
    }
}

struct RootView: View {
    @EnvironmentObject var app: AppState
    // 외부 AI 전송 동의 (App Store 5.1.2(i)) — 동의 전에는 어떤 화면도 열지 않는다
    @AppStorage("aiTransferConsent") private var aiTransferConsent = false

    var body: some View {
        if !aiTransferConsent {
            ConsentView { aiTransferConsent = true }
        } else if app.isConfigured {
            CompanionListView()
        } else {
            SetupView()
        }
    }
}
