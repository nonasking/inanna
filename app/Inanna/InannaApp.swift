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

    var body: some View {
        if app.isConfigured {
            CompanionListView()
        } else {
            SetupView()
        }
    }
}
