# 클로즈베타 운영 가이드

> 2026-07-12. 목표: 지인 소수(~10명)에게 웹 버전을 열어 실사용 피드백 수집.

## 준비된 것

- **초대제 가입 (1회용 코드)**: 코드는 **한 번 쓰면 소진**된다 — 코드가 유출돼도 계정을
  무한 생성해 쿼터를 새로 받는 우회가 막힌다. 계정 생성과 원자적으로 처리되고(실패 시 롤백),
  계정 삭제 시 코드가 반환되어 재초대할 수 있다.
  - 발급: `POST /api/admin/invites {"count":3,"note":"누구용"}` (오너 토큰) → 코드 목록
  - 현황: `GET /api/admin/invites` → 코드별 사용 여부·사용자
  - `.env`의 `INANNA_INVITE_CODES`는 부트스트랩 시드 (기동 시 1회용 코드로 등록)
  - 발급된 코드가 하나라도 있으면 초대제가 켜진다
- **웹 계정 화면**: 미인증 접속 시 로그인/가입/토큰 화면. 초대제면 가입 탭에 코드 입력란 자동 표시.
- **격리**: 계정마다 컴패니언·대화·기억 완전 분리 (user_id 스코핑). 오너(`local`)의 데이터와도 분리.
- **비용 가드**: 신규 가입 기본 티어는 `INANNA_DEFAULT_TIER`(현재 **beta**) —
  월간 15만/일간 2만 출력 토큰, 월 9천/일 1,500 음성 문자, 초과 시 402(일간은 자정 UTC 리셋).
  **TTS 엔진 게이트**: beta/lite는 무료 엔진(edge)만 — 유료 ElevenLabs·sovits는 상위 티어 전용
  (진짜 비용 폭탄은 토큰이 아니라 TTS 문자). 모델은 티어가 결정(beta=Haiku) →
  테스터가 Opus를 태울 수 없다. 개별 조정: `PUT /api/billing/tier`(오너가 특정 테스터 승급).
- **안전 레이어** (`server/safety.py`) — 정책을 *복제하지 않고 위임*한다:
  - 금지 목록을 우리 코드·프롬프트에 넣지 않는다 (프로바이더마다 다르고 계속 바뀐다).
    판정은 모델의 안전 정책이 하고, 우리는 **거절의 연출**만 정의한다 —
    "정책상 응답 못 할 요청이면 캐릭터를 유지한 채 자연스럽게 거절해라"
    (compiler의 대화 원칙 마지막 줄, 사용자 설정보다 우선).
  - 프로바이더가 거절하면(Anthropic `stop_reason: refusal`) **사실만 카운트** —
    내용은 저장하지 않는다. 24시간 창에서 5회 누적 시 **계정 자동 정지**(403),
    운영자가 `POST /api/admin/unsuspend/{id}`로 해제 가능(오탐 복구).
  - 정책이 바뀌어도 코드는 그대로다. 셀프호스팅 오너(`local`)는 통과 —
    자기 서버·자기 키·자기 책임.
- **가입 시 약관 동의 필수** — 프로바이더(Anthropic AUP) 정책을 참조하고,
  위반 반복 시 정지될 수 있음을 고지. 정책 내용을 우리가 복제하지 않으므로 갱신 불필요.
- **브루트포스 방어**: 인증 엔드포인트 IP당 20회/10분 → 429.
- **계정 삭제**: `DELETE /api/auth/account` = 계정+컴패니언+대화+기억 완전 삭제.

## 테스터 초대 절차

1. `.env`의 `INANNA_INVITE_CODES` 확인/추가 → `launchctl kickstart -k gui/$(id -u)/com.inanna.server`
2. 접속 주소 + 초대 코드를 전달
3. 테스터: 가입 → 컴패니언 생성(웹 빌더) → 채팅/통화

## 노출 방식 — **B 적용됨 (2026-07-12)**

**공개 주소: `https://macbookpro.tail9f8fdd.ts.net`** (`tailscale funnel --bg 8787`, 443).
끄기: `tailscale funnel --https=443 off`. 8443 Funnel(IoT MQTT)은 별개로 유지 중.
적용 시 확인: 공개 200 / 무인증 API 401 / invite_required true.

## 노출 방식 (참고 — 선택지였던 것)

| 방식 | 방법 | 특징 |
|---|---|---|
| **A. Tailscale 초대** (권장) | 테스터를 tailnet에 초대(무료 3명) 또는 기기 공유 | 공개 인터넷 노출 없음. 초대 수 제한 |
| **B. Funnel 공개** | `tailscale funnel --bg 8787` (443 사용) | 누구나 접속 가능한 https URL. **주의: 8443 Funnel은 IoT MQTT 전용 — 건드리지 말 것.** 초대 코드가 유일한 게이트가 되므로 코드 관리 중요 |

> B는 공개 인터넷 노출이므로 실행 전 확인: 초대 코드 설정됨, `INANNA_AUTH_TOKEN` 설정됨(오너 API 보호), 키 rotate 완료.

## 운영 중 모니터링

- 사용량: `GET /api/usage` (오너 토큰) 또는 `sqlite3 inanna.db "SELECT user_id, SUM(output_tokens) FROM usage GROUP BY user_id"`
- 가입 현황: `sqlite3 inanna.db "SELECT email, invite, datetime(created_at,'unixepoch') FROM accounts"`
- 통화 진단: `/tmp/inanna.log`의 `[voice …]` 라인

## 알려진 제약 (테스터 안내용)

- 기본 모델은 티어 기준(lite=Haiku). 서버 전역이 로컬 모델(ollama)로 설정된 경우
  오너 대화만 영향 — 계정 유저는 티어 모델을 쓴다.
- 음성 통화는 HTTPS 필수(마이크). 반말/존댓말·호칭은 컴패니언 설정을 따른다.
- 통화 중 말로 끼어들기(barge-in)는 또렷한 목소리 기준 — 조용한 환경 권장.

## 베타 전 체크리스트

- [ ] 노출된 적 있는 API 키 rotate (Anthropic, ElevenLabs)
- [ ] `INANNA_INVITE_CODES` 설정 + 코드 전달 대상 기록
- [ ] 노출 방식 결정 (A/B) 및 적용
- [ ] lite 쿼터 하향 검토 (베타 기간 비용 상한 = 인원 × lite 토큰 단가)
- [ ] 피드백 수집 채널 (카톡방 등)
