import SwiftUI

/// 첫 실행 — 서버 주소 + (셀프호스팅 토큰 | 계정 로그인)
struct SetupView: View {
    @EnvironmentObject var app: AppState
    @State private var url = "https://macbookpro.tail9f8fdd.ts.net"
    @State private var mode: Mode = .account   // 테스터 대부분 계정 — 토큰은 오너용
    @State private var token = ""
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?

    enum Mode: String, CaseIterable {
        case account = "계정"
        case token = "접속 토큰"
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("서버") {
                    TextField("https://…", text: $url)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section {
                    Picker("인증", selection: $mode) {
                        ForEach(Mode.allCases, id: \.self) { Text($0.rawValue) }
                    }
                    .pickerStyle(.segmented)

                    if mode == .token {
                        SecureField("INANNA_AUTH_TOKEN", text: $token)
                    } else {
                        TextField("이메일", text: $email)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                        SecureField("비밀번호", text: $password)
                    }
                } footer: {
                    if let error { Text(error).foregroundStyle(.red) }
                }
                Button(busy ? "연결 중…" : "연결") { connect() }
                    .disabled(busy || url.isEmpty)
            }
            .navigationTitle("Inanna")
        }
    }

    private func connect() {
        busy = true
        error = nil
        Task {
            defer { busy = false }
            if mode == .token {
                if let e = await app.verify(url: url, token: token) {
                    error = e
                    return
                }
                app.serverURLString = url
                app.authToken = token
            } else {
                if let e = await app.login(url: url, email: email, password: password) {
                    error = e
                    return
                }
            }
            await app.loadCompanions()
        }
    }
}
