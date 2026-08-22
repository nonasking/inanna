# App Store 제출 정보 (Inanna v1.0)

App Store Connect에 입력할 값 모음. 심사 리스크 대응까지 포함.

## 앱 기본

| 항목 | 값 |
|---|---|
| 이름 | Inanna |
| 번들 ID | dev.nonasking.inanna |
| 기본 언어 | 한국어 |
| 카테고리 | 기본: 라이프스타일 / 보조: 엔터테인먼트 |
| 버전 | 1.0 (빌드 1) |
| 가격 | 무료 (IAP 없음) |
| 배포 지역 | **대한민국만** (EU 제외 — DSA trader 요건 회피) |

## 연령 등급 설문 (정직하게 → 16+ 목표)

- AI 챗봇/생성형 대화 기능: **예**
- 성적 콘텐츠/노출: 없음 (모델 안전 정책으로 노골적 성적 표현 차단)
- 성인/암시적 테마(Mature/Suggestive): **Frequent** (관계·연애 대화 특성상 정직하게)
- 폭력/공포/도박/약물: 없음
- 만 14세 미만 이용 불가 (처리방침·앱에 명시)
- → 예상 등급: 글로벌 16+, 한국 표시 약 15+

## 개인정보

- 개인정보처리방침 URL: https://inanna.day/static/privacy.html
  (※ 정식 출시 시 안정적 도메인 권장 — 아래 '남은 리스크' 참고)
- App Privacy 라벨(수집 데이터):
  - 이메일 주소 — 앱 기능, 사용자와 연결됨, 추적 안 함
  - 사용자 콘텐츠(대화 내용) — 앱 기능, 연결됨, 추적 안 함
  - 오디오 데이터(통화) — 앱 기능, 연결됨, 추적 안 함
- 수출 규정: 비면제 암호화 없음(TLS만) — Info.plist에 선언 완료

## 심사용 데모 계정 (App Review Information)

```
로그인 방식: 이메일 + 비밀번호 (앱 첫 화면 '계정' 탭)
이메일: appreview@inanna.demo
비밀번호: Review-Inanna-2026
```
- 초대코드 없이 로그인 가능(이미 가입 완료), 도하(연인) 컴패니언 + 대화 기록 준비됨
- **서버가 심사 기간 내내 켜져 있어야 함** (맥 절전 해제 필수)

## 심사 노트 (Review Notes) — 초안

```
Inanna is a relationship-centered AI companion (voice + text). Companions
have no avatar by design — identity is expressed through voice and a color
"aura", not illustrations, so no third-party or copyrighted imagery is used.

Content safety: the app does not permit explicit sexual content. Policy
enforcement is delegated to the underlying model (Anthropic Claude); the
app counts provider refusals and auto-suspends accounts that repeatedly
attempt policy-violating use.

UGC controls (Guideline 1.2): users can report any AI reply (long-press
the message), block/remove a companion, and reach the developer at
nonasking@gmail.com. Reports are reviewed within 24h.

Third-party AI disclosure (5.1.2(i)): a first-launch consent screen
discloses that conversation text is sent to Anthropic (US) for response
generation, and voice text to ElevenLabs, before any data leaves the device.

Account deletion (5.1.1(v)): available in-app under the account menu.

Differentiation (4.3): unlike catalog-style character chat apps, Inanna
treats the *relationship* as the primary object — it is self-hosted
(the user owns their data and conversation history), formless by design,
and does not distribute preset characters as a consumable catalog.
```

## 스크린샷 (준비됨, 1320×2868)

목록 / 채팅 / 통화 / 추천 컴패니언 — 4장. 시뮬레이터 실서버 구동 캡처.

## 남은 리스크·확인 필요

1. **UIBackgroundModes: audio** — 통화 중 화면 잠금 시 음성 유지 목적. 심사에서
   "백그라운드 오디오 선언했으나 실제 미사용"으로 지적될 수 있음(2.5.4). 통화가
   실제로 잠금 상태에서 이어져야 하면 유지, 아니면 제거 권장. → 결정 필요.
2. **처리방침 도메인** — 현재 Tailscale Funnel 주소(맥이 꺼지면 접속 불가).
   심사 중 서버가 내려가면 리젝 사유. 최소한 심사 기간 상시 가동, 장기적으로는
   GitHub Pages 등 정적 호스팅에 처리방침만 올려두는 것 권장.
3. **서버 가용성** — 맥 한 대 운영. 데모 계정 접속이 심사의 핵심이라 절전 해제 필수.
