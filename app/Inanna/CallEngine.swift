import AVFoundation
import Foundation

/// 실시간 음성 통화 — docs/voice-protocol.md 클라이언트 구현.
/// 반이중: idle/listening일 때만 마이크 PCM(16k mono Int16)을 보내고,
/// thinking/speaking 중에는 보내지 않는다 (서버도 무시). 탭 = interrupt.
@MainActor
final class CallEngine: NSObject, ObservableObject {
    @Published var state = "connecting"   // connecting | idle | listening | thinking | speaking | ended
    @Published var userCaption = ""
    @Published var charCaption = ""
    @Published var error: String?

    private var ws: URLSessionWebSocketTask?
    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?
    private var pcmBuffer = Data()

    // 재생 큐 — 도착 순서대로 순차 재생 (mp3/wav 모두 AVAudioPlayer가 디코드)
    private var playQueue: [Data] = []
    private var player: AVAudioPlayer?
    private var turnEnded = false

    private static let targetFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)!

    func start(api: APIClient, companionId: String) {
        let task = URLSession.shared.webSocketTask(with: api.voiceURL(companionId: companionId))
        ws = task
        task.resume()
        sendJSON(["type": "auth", "token": api.token])
        receiveLoop()
        do {
            try startAudio()
        } catch {
            self.error = "마이크를 열 수 없어요: \(error.localizedDescription)"
        }
    }

    func stop() {
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        player?.stop()
        ws?.cancel(with: .normalClosure, reason: nil)
        try? AVAudioSession.sharedInstance().setActive(false)
        state = "ended"
    }

    /// 화면 탭 — 유나가 말하거나 생각 중일 때 끼어들기
    func interrupt() {
        guard state == "speaking" || state == "thinking" else { return }
        playQueue.removeAll()
        player?.stop()
        player = nil
        turnEnded = false
        sendJSON(["type": "interrupt"])
    }

    // MARK: - 오디오 캡처

    private func startAudio() throws {
        let session = AVAudioSession.sharedInstance()
        // voiceChat 모드 = 에코 캔슬레이션 (스피커 재생 중 마이크로 안 들어가게)
        try session.setCategory(.playAndRecord, mode: .voiceChat,
                                options: [.defaultToSpeaker, .allowBluetoothHFP])
        try session.setActive(true)

        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        converter = AVAudioConverter(from: inputFormat, to: Self.targetFormat)

        input.installTap(onBus: 0, bufferSize: 2048, format: inputFormat) { [weak self] buffer, _ in
            self?.handleCapture(buffer)
        }
        engine.prepare()
        try engine.start()
    }

    private nonisolated func handleCapture(_ buffer: AVAudioPCMBuffer) {
        Task { @MainActor in
            guard self.state == "idle" || self.state == "listening",
                  let converter = self.converter else { return }
            let ratio = 16000.0 / buffer.format.sampleRate
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio + 16)
            guard let out = AVAudioPCMBuffer(pcmFormat: Self.targetFormat,
                                             frameCapacity: capacity) else { return }
            var fed = false
            converter.convert(to: out, error: nil) { _, status in
                if fed {
                    status.pointee = .noDataNow
                    return nil
                }
                fed = true
                status.pointee = .haveData
                return buffer
            }
            guard out.frameLength > 0, let ch = out.int16ChannelData else { return }
            self.pcmBuffer.append(Data(bytes: ch[0], count: Int(out.frameLength) * 2))
            // ~100ms(3200B) 단위로 송신 — 서버 VAD의 프레임 단위와 무관 (서버가 재분할)
            while self.pcmBuffer.count >= 3200 {
                let chunk = self.pcmBuffer.prefix(3200)
                self.pcmBuffer.removeFirst(3200)
                self.ws?.send(.data(Data(chunk))) { _ in }
            }
        }
    }

    // MARK: - 수신

    private func receiveLoop() {
        ws?.receive { [weak self] result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .failure:
                    if self.state != "ended" { self.error = "연결이 끊어졌어요" }
                case .success(let message):
                    switch message {
                    case .string(let text): self.handleEvent(text)
                    case .data(let data): self.enqueueAudio(data)
                    @unknown default: break
                    }
                    self.receiveLoop()
                }
            }
        }
    }

    private func handleEvent(_ text: String) {
        guard let obj = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any],
              let type = obj["type"] as? String else { return }
        switch type {
        case "ready":
            break
        case "state":
            state = obj["value"] as? String ?? state
        case "stt":
            userCaption = obj["text"] as? String ?? ""
            charCaption = ""
        case "text":
            // 오디오 태그([laughs] 등)는 음성으로만 — 자막에서 숨긴다
            charCaption = String((charCaption + (obj["delta"] as? String ?? ""))
                .replacing(/\[[a-zA-Z][a-zA-Z ]{1,30}\]/, with: " ")
                .suffix(120))
        case "audio":
            break  // 메타만 — 실 데이터는 다음 바이너리 프레임
        case "turn_end":
            turnEnded = true
            maybePlaybackEnd()
        case "interrupted":
            playQueue.removeAll()
            player?.stop()
            player = nil
        case "error":
            charCaption = "⚠ " + (obj["message"] as? String ?? "오류")
        default:
            break
        }
    }

    // MARK: - 재생

    private func enqueueAudio(_ data: Data) {
        playQueue.append(data)
        playNext()
    }

    private func playNext() {
        guard player == nil, !playQueue.isEmpty else { return }
        let data = playQueue.removeFirst()
        do {
            let p = try AVAudioPlayer(data: data)
            p.delegate = self
            player = p
            p.play()
        } catch {
            player = nil
            playNext()  // 못 여는 청크는 건너뛴다
        }
    }

    private func maybePlaybackEnd() {
        if turnEnded && player == nil && playQueue.isEmpty {
            turnEnded = false
            sendJSON(["type": "playback_end"])
        }
    }

    private func sendJSON(_ obj: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: obj),
              let text = String(data: data, encoding: .utf8) else { return }
        ws?.send(.string(text)) { _ in }
    }
}

extension CallEngine: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully: Bool) {
        Task { @MainActor in
            self.player = nil
            self.playNext()
            self.maybePlaybackEnd()
        }
    }
}
