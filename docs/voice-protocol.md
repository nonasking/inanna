# Inanna 음성 통화 WebSocket 프로토콜 v1

> **이 문서는 클라이언트 계약이다.** 웹 클라이언트(`web/call.js`)는 레퍼런스 구현이고,
> P4 SwiftUI 네이티브 앱은 이 프로토콜을 그대로 재사용한다. 변경 시 버전을 올린다.

## 연결

```
WS(S) /api/ws/voice/{companion_id}
```

- 서버에 `INANNA_AUTH_TOKEN`이 설정된 경우, 접속 후 **5초 내 첫 메시지**로 인증:
  `{"type": "auth", "token": "<token>"}` — 실패/미인증 시 close **4401**
- 컴패니언이 없으면 close **4404**
- 인증 통과 시 서버가 `ready`를 보낸다

## 오디오 포맷

| 방향 | 포맷 | 프레이밍 |
|---|---|---|
| 클라 → 서버 (마이크) | **16kHz mono PCM16LE raw** | 바이너리 프레임, 100ms(3,200B) 권장 |
| 서버 → 클라 (TTS) | 엔진 네이티브 (sovits=WAV, edge=MP3) | `audio` JSON 직후 바이너리 1프레임 (문장 단위) |

WS 메시지 순서 보장을 이용해 "JSON 메타 → 바이너리" 쌍으로 상관관계를 유지한다.

## 이벤트

**클라 → 서버 (JSON)**

| type | 필드 | 의미 |
|---|---|---|
| `auth` | `token` | 최초 1회 |
| `interrupt` | — | 끼어들기: 진행 중 턴 취소 요청 |
| `playback_end` | — | 클라 재생 큐 소진 (speaking→idle 전이 트리거) |

**서버 → 클라 (JSON)**

| type | 필드 | 의미 |
|---|---|---|
| `ready` | `session_id`, `voice_engine`, `bond`(0~1 유대감 — 오브 시각 변화용) | 인증 완료 |
| `state` | `value`: idle\|listening\|thinking\|speaking | 상태 전이 (UI 반영) |
| `stt` | `text` | 사용자 발화 인식 결과 |
| `text` | `delta` | 응답 텍스트 델타 (자막) |
| `audio` | `seq`, `mime`, `text` | 직후 바이너리 프레임 예고 |
| `turn_end` | — | 이번 턴 오디오 송신 완료 |
| `interrupted` | — | 취소 완료 (뒤이어 state:idle) |
| `error` | `message` | 파이프라인 오류 (연결은 유지) |

## 상태 머신 (서버 권위)

```
idle ──(VAD 발화 시작)──▶ listening ──(VAD 종료)──▶ thinking ──(STT→LLM→TTS)──▶ speaking
 ▲                                                                                │
 ├──────────────────────(클라 playback_end)───────────────────────────────────────┘
 └──────────(interrupt → interrupted)── thinking/speaking 어디서든
```

- **barge-in** (2026-07-12, half-duplex에서 승격): 클라이언트는 모든 활성 상태에서
  마이크 프레임을 계속 보낸다 (AEC 필수 — 웹 `echoCancellation`, iOS `.voiceChat`).
  서버는 `thinking`/`speaking` 중 수신 프레임을 보수적 감지기(임계 ×1.6, 지속 300ms)로
  판정하고, 끼어들기 확정 시 `interrupted`를 보내고 그 발화를 이어서 인식한다.
  클라이언트는 `interrupted` 수신 즉시 재생을 중단해야 한다 (탭 인터럽트와 동일 경로).
  오디오가 없는 턴은 `turn_end` 후 바로 idle.
- **barge-in 승격 경로**(P2.5+): "speaking 중 바이너리 허용 + 서버 VAD 감지 시 자동 interrupt"만
  추가하면 되며 메시지 스키마 변경은 없다.

## 구현 노트

- VAD: 에너지 기반. 접속 첫 0.8s로 노이즈 플로어 캘리브레이션 — **통화 시작 직후 1초는 말하지 말 것**
  (클라이언트가 무음을 보내는 동안). 발화 종료 판정 750ms — 문장 사이 0.75s 이상 쉬면 별개 발화가 된다.
- STT: whisper-server(:9881) — `INANNA_WHISPER_URL`. 환각 필터에 걸린 발화는 조용히 무시(idle 복귀).
- 대화 기록: 음성 턴도 텍스트 채팅과 동일한 `messages`에 저장된다 (기억 요약 대상 포함).
  인터럽트 시 부분 응답도 저장된다.
- 검증: `tests/voice_e2e.py` (5개 시나리오 — 스크립트 클라이언트로 서버 루프 전체 검증 가능)
