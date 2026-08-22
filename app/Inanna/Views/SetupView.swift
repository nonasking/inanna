import SwiftUI

/// 첫 실행 — 계정 로그인. 서버는 기본 서비스에 연결되고,
/// 직접 운영하는 서버가 있는 사람만 '직접 운영하는 서버'를 펼쳐 바꾼다.
struct SetupView: View {
    @EnvironmentObject var app: AppState
    @State private var url = AppState.defaultServerURL
    @State private var mode: Mode = .account   // 테스터 대부분 계정 — 토큰은 오너용
    @State private var token = ""
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?
    @State private var showAdvanced = false

    enum Mode: String, CaseIterable {
        case account = "계정"
        case token = "접속 토큰"
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("이메일", text: $email)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("비밀번호", text: $password)
                } header: {
                    Text("로그인")
                } footer: {
                    if let error { Text(error).foregroundStyle(.red) }
                }

                // 셀프호스팅 — 자기 서버를 운영하는 사람만 펼친다 (기본은 공용 서비스)
                Section {
                    DisclosureGroup("직접 운영하는 서버 사용", isExpanded: $showAdvanced) {
                        TextField("https://…", text: $url)
                            .keyboardType(.URL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                        Picker("인증", selection: $mode) {
                            ForEach(Mode.allCases, id: \.self) { Text($0.rawValue) }
                        }
                        .pickerStyle(.segmented)
                        if mode == .token {
                            SecureField("INANNA_AUTH_TOKEN", text: $token)
                        }
                    }
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
