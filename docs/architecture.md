# Inanna — 아키텍처 설계

> 2026-07-10 초안. 요건: [requirements.md](requirements.md)

## 1. 형태 (2026-07-10 갱신: App Store 배포 염두)

**개발 모드(현재): 맥 셀프호스팅 서버 + 웹 클라이언트. 제품 모드(P4): 호스티드 백엔드 + SwiftUI 네이티브 앱(App Store).**

웹 클라이언트는 기능 검증용 개발 클라이언트이고, 최종 클라이언트는 네이티브 앱이다. 따라서 서버가 제품의 전부이고 클라이언트는 얇게 유지한다 — API(REST+SSE, P2부터 WebSocket 오디오)가 계약. 선반영된 구조: 전 데이터 user_id 스코핑(셀프호스팅=`local`), bearer 인증(`INANNA_AUTH_TOKEN`). 제품 모드 전환 시 교체 지점: 인증(bearer→계정/Sign in with Apple), 저장소(SQLite→Postgres, YAML→DB), TTS(로컬→워커), 푸시(APNs).

## 2. 스택

| 레이어 | 선택 | 이유 |
|---|---|---|
| 서버 | **Python + FastAPI** | 음성 스택(GPT-SoVITS/whisper/CosyVoice)이 전부 파이썬 생태계. 스트리밍(SSE/WebSocket) 지원 |
| LLM | 프로바이더 추상화: **Anthropic API 기본** / Ollama 옵션 | 감성 대화 품질은 모델이 절반. 로컬 폴백으로 비용 0원 경로 유지 |
| TTS | 플러그인: **CosyVoice(1차)** / GPT-SoVITS(2차) / Edge TTS(개발 폴백) | 한국어 + 제로샷 클로닝 + Apache. GPT-SoVITS는 커뮤니티 최대지만 맥 셋업이 무거움 |
| STT (P2) | whisper.cpp (Metal) | 맥 로컬 실시간 |
| 저장 | SQLite + 파일(YAML 페르소나, 오디오) | 단일 사용자 셀프호스팅에 충분, 백업=파일 복사 |
| 클라이언트 | 서버가 서빙하는 SPA (Svelte 또는 vanilla) → PWA | 폰 홈화면 설치. 프레임워크는 P0에서 가볍게 시작 |
| 임베딩 (P2) | sqlite-vec + 로컬 임베딩 모델 | 외부 의존 없이 archival recall |

## 3. 컴포넌트

```
┌─ Web Client (PWA) ──────────────────────────────┐
│  채팅 UI · 컴패니언 빌더(관계/성격/목소리 편집) · 오디오 재생 │
└──────────────┬──────────────────────────────────┘
               │ HTTP / SSE (Tailscale 경유 폰 접속)
┌─ FastAPI Server ─────────────────────────────────┐
│                                                   │
│  CompanionStore     YAML/SQLite. CCv2/v3 임포터     │
│  PromptCompiler     Relationship+Persona+Memory    │
│                     → system prompt               │
│  ChatOrchestrator   대화 루프, 스트리밍, 세션 관리      │
│  MemoryService      요약 생성(대화 종료/N턴마다),      │
│                     core/episodic/archival 계층    │
│  LLMProvider        anthropic | ollama            │
│  TTSEngine (P1)     cosyvoice | gpt-sovits | edge │
│  VoiceRegistry (P1) 참조 오디오 → 보이스 프로필        │
└───────────────────────────────────────────────────┘
```

## 4. 데이터 모델 (P0)

```yaml
# companions/yuna.yaml
id: yuna
name: 유나
relationship:
  template: younger-sister        # 출발점
  calls_me: "오빠"                 # 파생값, 전부 오버라이드 가능
  i_call: "유나"
  speech_level: banmal
  intimacy: 0.7                   # 거리감 0~1
  backstory: >-
    어릴 때부터 같이 자란 사이. …
persona:
  traits: {cheerful: 0.8, direct: 0.6, playful: 0.9, caring: 0.7}
  speech_quirks: ["어미에 '~잖아' 자주", "놀릴 때 'ㅋㅋ' 남발"]
  description: >-
    (자유 텍스트 — CCv3 description 호환)
  lorebook:
    - keys: ["고향", "부산"]
      content: "…"
voice:
  engine: cosyvoice
  reference_audio: voices/yuna-ref.wav   # 사용자가 넣은 파일. 프로젝트는 배포 안 함
  speed: 1.0
# appearance 없음 — 무형 컴패니언이 설계 원칙 (requirements §1)
```

- **관계 템플릿**은 코드가 아닌 데이터(`templates/*.yaml`)로 — 호칭 후보·말단계·거리감 기본값·관계 서사 힌트를 정의.
- CCv2/v3 임포트: `description/personality/scenario/first_mes/character_book` → 위 스키마 매핑. 익스포트(P3)에서 `x_voice` 확장.

### SQLite (기억)

```
sessions(id, companion_id, started_at)
messages(id, session_id, role, content, ts)
memories(id, companion_id, layer, content, embedding, importance, created_at, source_session)
  -- layer: core | episodic | archival
```

## 5. 프롬프트 컴파일 (품질의 핵심)

```
[system]
1. 정체성:      이름·관계 서사 ("너는 사용자의 여동생 유나다. …")
2. 관계 규칙:    호칭·말단계·거리감 — "반드시 '오빠'라고 부른다. 반말. …"
3. 성격:        traits → 자연어 변환 (persona 프로젝트의 trait→prompt 방식 참고)
4. 말투:        speech_quirks + few-shot 대화 예시 (말투 유지에 가장 효과적)
5. 기억:        core 요약 + 관련 episodic/archival recall
6. 가드:        "AI임을 부정하는 질문엔 …" 등 운영 규칙
[messages] 최근 N턴 (+로어북 키워드 트리거 삽입)
```

- 말투 붕괴 방지는 few-shot 예시(카드 생태계의 `mes_example`이 검증한 방식)가 1순위 수단.
- 관계만 바꾸면 1·2번 블록만 갈리고 3·4는 유지 → "같은 성격, 다른 관계" 테스트 가능(품질 기준 #1).

## 6. 음성 파이프라인 (P1→P2)

```
P1 (턴 기반):  응답 텍스트 → TTSEngine → wav → 클라이언트 재생
P2 (실시간):   마이크 → whisper.cpp → LLM 스트리밍 → 문장 단위 TTS 스트리밍 → 재생
              (문장 경계 분할로 첫 오디오 지연 최소화, 인터럽트 시 파이프라인 취소)
```

- TTSEngine 인터페이스: `synthesize(text, voice_profile) -> audio`, `register_voice(ref_audio) -> voice_profile`
- 맥 실측 후 결정: CosyVoice(MPS) 지연이 대화용으로 부족하면 → 폴백 Edge TTS(개발), 또는 GPU 박스/콜랩 원격 TTS 워커 옵션(Tailscale로 연결).

## 7. 리포 구조 (P0)

```
inanna/
├── server/
│   ├── main.py              # FastAPI 엔트리
│   ├── companion/           # 스키마, 스토어, CCv2/v3 임포터, 템플릿
│   ├── chat/                # orchestrator, prompt compiler
│   ├── memory/              # 요약, 계층 저장
│   ├── llm/                 # anthropic.py, ollama.py
│   └── tts/                 # (P1) engine 인터페이스 + 어댑터
├── web/                     # 클라이언트
├── templates/               # 관계 템플릿 yaml
├── companions/              # 사용자 데이터 (gitignore)
├── voices/                  # 사용자 참조 오디오 (gitignore)
└── docs/
```

## 8. 흡수할 것 / 지킬 것 (아이디어 철학 적용)

- **탐욕적 흡수(구현)**: CCv2/v3 스펙(카드 호환), Open-LLM-VTuber의 음성 루프·인터럽트 설계, Letta의 계층 메모리 패턴, ~/dev/persona의 trait EMA(관계가 대화로 미세 조정되는 P2 기능 후보), SillyTavern의 로어북 개념(코드는 AGPL — 보지 말 것).
- **순진함 보호(비전)**: "관계가 1급 개념"이라는 축은 기존 프로젝트 어디에도 없다 — 기존 설계에 맞추려고 이 축을 희석하지 말 것. 갈라지는 지점(관계 템플릿→파생 프롬프트, 관계의 시간적 진행)이 차별화 후보.

## 9. 리스크

| 리스크 | 대응 |
|---|---|
| 맥에서 한국어 TTS 지연이 대화용 미달 | P1에서 실측 → 원격 TTS 워커 옵션 설계 이미 반영 |
| 말투 일관성 붕괴 (LLM 한계) | few-shot 예시 + 주기적 스타일 리마인더 주입, 품질 기준 #2로 상시 검증 |
| LLM API 비용 | Ollama 폴백 + 요약으로 컨텍스트 절약 |
| 공유 기능 요구가 생길 때 저작권 | 비목표 유지. 도입 시 takedown 체계 선행 (requirements §2) |
```
