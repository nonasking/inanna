# 커스텀 AI 컴패니언 에이전트 — 선행 사례 조사 보고서

> 조사일: 2026-07-10 · 방법: 5개 검색 각도 병렬 웹 리서치 → 25+ 소스 수집 → 주장별 교차 검증(반박 0건, 48건 통과)
> 요건: ① 관계 유형(연인/친구/동생)·성격·말투 커스텀 ② 목소리 입히기(TTS/보이스 클로닝) ③ 서브컬처 캐릭터 + 저작권 안전

---

## 1. 한눈에 보는 결론

- **"페르소나 커스텀 + 음성 + 서브컬처 캐릭터"를 셋 다 제대로 하는 단일 서비스는 아직 없다.** 각 축의 강자는 있지만 교집합이 비어 있다.
- 오픈소스 쪽은 부품이 전부 나와 있다: SillyTavern(페르소나/카드 생태계) + Open-LLM-VTuber·AIRI(음성+아바타 파이프라인) + GPT-SoVITS 등(보이스 클로닝). **조립은 가능하나 "관계 중심 설계"를 한 프로젝트는 없다.**
- 저작권의 실전 규칙: **캐릭터 성격·외형은 저작권/상표 리스크**(디즈니→Character.AI 삭제 요구, 웹툰 6사→제타 형사고소), **목소리는 저작권이 아니라 퍼블리시티권 리스크**(Lehrman v. Lovo 판결, ELVIS Act). 개인 로컬 사용은 사실상 안전지대, 배포/상용화 순간 리스크가 발생.

---

## 2. 상용 서비스 기능 매트릭스

| 서비스 | 페르소나 커스텀 | 음성 | 서브컬처 캐릭터 | 저작권 대응 |
|---|---|---|---|---|
| **Character.AI** (미국) | ◎ 무제한 커스텀 캐릭터, 파라미터 지정 | ○ 캐릭터별 보이스 | △ UGC로 범람 | 사후 삭제(notice-and-takedown). 2025-09 디즈니 C&D 후 해당 캐릭터 일괄 삭제, "권리자와 공식 파트너십 원한다" 입장 |
| **제타(스캐터랩)** (한국) | ◎ 프롬프트 1200자·로어북·스타일 탭(시점/말투/분위기) | ✕ **음성 기능 2026-06-12 삭제됨** | △ UGC 실태 존재 | 사후 삭제+경고 누적제. **2025-12~ 웹툰 플랫폼 6곳(카카오엔터·리디 등)이 저작권법 위반 방조로 형사고소** |
| **Cotomo(Starley)** (일본) | △ 이름·목소리·아이콘 수준 | ◎ 1초 미만 저지연 음성 특화, 성우 19종 | △ | **성우 기획사 아오니프로덕션과 공식 콜라보로 성우 보이스 라이선스 제공** — 합법 음성 IP의 대표 사례 |
| **Grok Ani(xAI)** | ✕ 고정 캐릭터("what you see is what you get") | ◎ 실시간 합성+립싱크 85%+감정 | △ 미사 아마네 "오마주" 오리지널(라이선스 회피 설계) | 유사-오리지널 전략. 2026년 일부 기능이 안전/법적 이슈로 제한 |
| **Kindroid** | ◎ 자유 텍스트 "Codex" 성격 정의 | ◎ ElevenLabs 기반 **보이스 클로닝 제공** | △ | UGC 사용자 책임 |
| **Replika** | △ 로맨스 기능 제거 후 제한적, UGC 캐릭터 없음 | ○ 음성통화+3D 아바타 | ✕ | 자체 캐릭터만 |
| **Gatebox** (일본, HW) | ✕ 자체 캐릭터 1종 | ○ | ◎ **하츠네 미쿠 공식 라이선스 한정판** | 공식 IP 콜라보 모델. 단 2020년 서비스 중단으로 "캐릭터 사망" — 클로즈드 서비스 종속성 리스크의 고전 사례 |

시장 신호 몇 가지:
- 제타는 가입자 600만(2026-03), 일본에서 반년 만에 2배 성장, 스캐터랩 2025년 창사 첫 흑자(매출 ~260억) — **캐릭터 챗 비즈니스 모델은 수익성이 검증됨**.
- Grok Ani 목소리 변경(2026-03) 때 #BringBackAni 청원 사태 — **목소리는 사용자가 대체 불가능한 정체성으로 취급하는 핵심 기능**.
- Character.AI는 미성년 안전 소송(Garcia 사건, "AI 앱=제조물" 판결)으로 2026-01 합의, 18세 미만 오픈 대화 차단. 발단 봇이 '대너리스'(IP 캐릭터)였다는 점에서 IP·안전 리스크가 교차.

---

## 3. 오픈소스 생태계 (직접 만들 때의 부품들)

| 프로젝트 | 역할 | 핵심 사실 | 라이선스 |
|---|---|---|---|
| **SillyTavern** (★30.5k) | 캐릭터 롤플레이 프론트엔드의 사실상 표준 | 캐릭터 카드 중심 설계, 다수 LLM API 통합, TTS 확장(ElevenLabs/XTTS/Kokoro 등), 로어북(WorldInfo) | **AGPL-3.0** — 파생작은 소스 공개 의무 |
| **Open-LLM-VTuber** (★12.4k) | 로컬 음성대화 + Live2D 컴패니언 | 완전 오프라인 가능, 음성 인터럽트, 커스텀 Live2D 임포트, TTS 백엔드 10여 종(GPT-SoVITS/CosyVoice/Fish 등) 플러그인식 | MIT (동봉 Live2D 모델은 별도 라이선스) |
| **AIRI (moeru-ai)** (★41.5k, v0.11.0 2026-07-08) | Neuro-sama 지향 "셀프호스팅 사이버 생명체" | VRM+Live2D, 멀티 TTS, 마인크래프트 플레이, WebGPU 브라우저 추론, Discord/Telegram. **단 관계/성격 커스텀 도구는 빈약** | MIT |
| **Letta (ex-MemGPT)** | 스테이트풀 에이전트 메모리 | Core/Recall/Archival 계층 메모리를 에이전트가 스스로 편집 — "관계가 축적되는 컴패니언"의 기반 기술 | Apache-2.0 |
| **Character Card Spec V2/V3** | 페르소나의 이식 가능한 표준 포맷 | PNG에 JSON 임베드. V2: system_prompt·로어북 내장. V3: 멀티 에셋·다국어·데코레이터. **음성(voice) 에셋 타입은 표준에 없음**(x_ 확장만 가능) | 커뮤니티 스펙 |

**시사점**: 기존 카드 생태계(수십만 장의 캐릭터 카드)와의 호환은 CCv2/v3 임포트로 확보하는 게 정석. 그리고 **카드 스펙에 '목소리' 슬롯이 없다는 것** 자체가 표준화 틈새다.

---

## 4. 음성 스택 — 오픈소스 TTS/보이스 클로닝 비교

| 모델 | 클로닝 요구량 | 언어 | 속도/지연 | 라이선스(상용) |
|---|---|---|---|---|
| **GPT-SoVITS** (★59.6k) | 제로샷 5초 / 파인튜닝 1분 | **한·일·영·중·광둥** | 실측 최속(~10초/RTF 0.014) | **MIT ✓** |
| **CosyVoice 3** (알리바바) | 제로샷, 교차언어 | 9개 언어+방언 | ~150ms 초저지연 | Apache ✓ |
| **Fish Speech / S2 Pro** | 10–30초 | 80+ 언어 | <150ms(API) | 가중치 **CC-BY-NC ✕** — 상용은 유료 API |
| **Chatterbox (Resemble)** | 제로샷 5–10초 | 다국어 | 실시간급, 4–6GB VRAM | **MIT ✓** (블라인드 테스트에서 ElevenLabs보다 선호 63.8~65.3%) |
| **Kokoro** | (프리셋 보이스) | 다국어 | **CPU/라즈베리파이 실시간** | Apache ✓ |
| **XTTS v2 (Coqui)** | 6초 | 17개 언어 | 보통 | CPML **✕ 비상용** |

- 2026-05 실측 비교(RTX 4090): 음색 유사도는 Fish Speech·CosyVoice 우세, 속도는 GPT-SoVITS 압승. **실시간 대화형이면 GPT-SoVITS/CosyVoice 계열, 품질 우선 배치 생성이면 Fish 계열.**
- 애니 캐릭터 보이스 학습 모델은 AI Hub 등 커뮤니티에서 대량 유통 중(저작권 그레이존).
- 맥(Apple Silicon)에서는 VoxCPM이 CPU/MPS 지원으로 추천된 바 있음 — GPU 없는 개발 환경에서도 파이프라인 구축 가능.
- 경고 사례: MS VibeVoice는 MIT였는데도 오용 때문에 2025-09 추론 코드가 내려감 — 보이스 클로닝은 배포 방식 자체가 리스크 관리 대상.

---

## 5. 저작권/법적 지형 — "어디까지 안전한가"

### 캐릭터(성격·외형) 축
- **디즈니 → Character.AI C&D(2025-09)**: 저작권+상표(무임승차)+브랜드 안전(아동 유해)을 동시에 문제 삼음. 플랫폼은 지목된 캐릭터만 선별 삭제(반응적 대응). 플랫폼에 삭제 '의무'가 있는지는 법적으로 미확정이며, Fordham IP 논문은 "침해 가능성 높고 책임은 사용자가 아니라 플랫폼"이라고 주장.
- **한국**: 웹툰 플랫폼 6곳이 제타 운영사를 **저작권법 위반 '방조' 혐의로 형사고소**(2025-12~, 2026-05 보도) — UGC 플랫폼 운영자가 형사 리스크까지 지는 국면. 한국에서 캐릭터 UGC 서비스를 열려면 이 사건의 귀추가 직접적 선례가 됨.

### 목소리 축
- **Lehrman v. Lovo (S.D.N.Y. 2025-07)**: 연방 저작권·상표 청구 기각 — **목소리 자체는 저작권 대상이 아님**(17 U.S.C. §114(b), 직접 녹음 복제가 아닌 모방은 침해 불성립). 그러나 **주(州) 퍼블리시티권 청구는 생존** — 실존 인물(성우) 음성 클로닝의 진짜 리스크는 퍼블리시티권.
- **규제 확산**: 테네시 ELVIS Act(AI 음성 클론에 퍼블리시티권 명시 확장, 2024), 캘리포니아 AB 1836/2602, 뉴욕 디지털 레플리카 조항 등 주법 패치워크. 기준선은 **"구체적·철회가능·문서화된 사전 서면 동의"**.
- **일본**: 성우들이 'NOMORE 무단생성AI' 결성, '성문권(声紋権)' 법제화 운동 중 — 아직 법이 없어서 운동 단계라는 것 자체가 시사점.

### 합법 접근의 실존 모델 (공식 라이선스 사례)
1. **아오니프로덕션 × CoeFont(2024-10)**: 성우 10인(노자와 마사코 포함) 음성의 공식 AI화. 단 **허용 용도는 가상 비서·의료·내비 등이고, 애니 연기·더빙은 계약으로 배제 — "캐릭터 대화/컴패니언" 용도는 공백**.
2. **카지 유키 'Soyogi Fractal'**: 성우 본인이 CeVIO AI로 자기 목소리를 가상 캐릭터화, 하츠네 미쿠식 UGC 라이선스로 개방 + 본인 목소리로 대화하는 Soyogi AI 앱 출시 — **성우 주도 음성 IP화의 원형**.
3. **Gatebox × 하츠네 미쿠**: 공식 IP 라이선스 컴패니언 하드웨어. 서비스 중단과 함께 캐릭터가 "죽은" 사례이기도 함.
4. **Cotomo × 아오니**: 상용 컴패니언 앱에 성우 라이선스 보이스를 넣은 현행 사례.
5. 반대편 전략 — **Grok Ani의 "저작권 무관 오마주 오리지널"**: 라이선스 없이 유사 미학만 차용. 규제·안전 이슈로 기능이 계속 깎이는 중.

### 실무 요약
| 시나리오 | 리스크 |
|---|---|
| 개인이 로컬에서 좋아하는 캐릭터 페르소나+음성으로 사용 | 사실상 낮음 (SillyTavern 생태계가 이 위치) |
| 캐릭터 카드/음성 모델을 **공유·배포** | 그레이존 진입 — 커뮤니티는 사후 삭제로 운영 중 |
| **상용 서비스**로 서브컬처 IP UGC 허용 | 디즈니 C&D·제타 형사고소가 보여준 실질 리스크. notice-and-takedown 체계 필수 |
| 실존 성우 목소리 클로닝 탑재 | 퍼블리시티권 — 동의/라이선스 없이는 불가 |
| 공식 IP·성우 라이선스 확보 | 안전하나 계약 범위가 용도별로 세분화됨(굿즈/광고/대화 각각 별도) |

---

## 6. 비어 있는 틈새 = 차별화 기회

1. **"관계 유형 우선" 설계가 없다.** 모든 서비스가 '캐릭터'를 만들지 '관계'를 만들지 않는다. 연인/친구/동생/선후배 같은 관계 프레임을 1급 개념으로 두고 성격·말투·거리감·호칭이 관계에서 파생되게 하는 설계는 상용·오픈소스 어디에도 없다. (Grok Ani는 호감도 시스템이 있지만 캐릭터도 관계 유형도 고정.)
2. **페르소나 커스텀 × 음성의 교집합이 비어 있다.** 커스텀 강자(제타·Character.AI)는 음성이 약하거나 삭제됐고(제타 2026-06), 음성 강자(Cotomo·Grok Ani)는 커스텀이 없다. Kindroid 정도가 근접하나 클라우드 종속 + 서브컬처 축 부재.
3. **캐릭터 카드 표준에 '목소리' 슬롯이 없다.** CCv3까지도 voice 에셋 타입 미정의. "카드 + 참조 오디오 몇 초 = 어디서나 같은 캐릭터가 같은 목소리로" — 카드 호환 + 음성 확장(x_voice)을 정의하면 생태계 표준을 선점할 수 있는 지점.
4. **관계 축적(장기 기억)의 소유권.** 상용 서비스는 관계 데이터가 회사에 있고(Gatebox 미쿠처럼 서비스 종료 = 관계 소멸), 오픈소스는 메모리가 빈약. Letta류 계층 메모리를 붙인 "내가 소유하는, 죽지 않는 관계"는 셀프호스팅 진영의 감성적 킬러 포인트.
5. **저작권 안전 경로의 사업 공백**: 아오니×CoeFont 계약이 컴패니언 대화 용도를 비워둔 것처럼, **"성우/IP 공식 라이선스 기반 컴패니언"은 수요(제타 600만, Ani 팬덤) 대비 공급이 없다.** 개인 프로젝트 단계에서는 ① 로컬/셀프호스팅으로 책임을 사용자에게 두는 SillyTavern 모델 + ② 오리지널 캐릭터 기본 제공 + ③ IP는 사용자가 직접 입히는 구조(플랫폼이 배포하지 않음)가 안전한 기본형.

### 개인 프로젝트로 시작할 때의 추천 스택 (참고)
- 프론트/파이프라인: Open-LLM-VTuber(음성 대화 루프 참고) or AIRI(라이브 아바타), 페르소나 포맷은 CCv3 호환
- 음성: GPT-SoVITS(한국어 지원+MIT+실시간, 커뮤니티 최대) 기본, 맥 개발은 VoxCPM/Kokoro 보조
- 메모리: Letta 계층 메모리 패턴
- 라이선스 주의: SillyTavern 코드 재사용 시 AGPL 전염, Fish Speech 가중치 비상용, 동봉 Live2D 모델 별도 라이선스

---

## 주요 출처
- 상용: [TechCrunch — Disney C&D](https://techcrunch.com/2025/10/01/character-ai-removes-disney-characters-after-receiving-cease-and-desist-letter/) · [전자신문 — 제타 600만](https://www.etnews.com/20260403000179) · [나무위키 — zeta](https://namu.wiki/w/zeta(애플리케이션)) · [Grok Ani 리뷰](https://aicompanionguides.com/blog/grok-ani-review/) · [Cotomo 리뷰](https://aipure.ai/articles/cotomo-review-revolutionary-voice-based-ai-companion)
- 오픈소스: [SillyTavern](https://github.com/SillyTavern/SillyTavern) · [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) · [AIRI](https://github.com/moeru-ai/airi) · [CC Spec V2](https://github.com/malfoyslastname/character-card-spec-v2) / [V3](https://github.com/kwaroran/character-card-spec-v3) · [Letta](https://github.com/letta-ai/letta)
- 음성: [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) · [2026 보이스클로닝 실측 비교](https://liudon.com/posts/voice-cloning-solution-comparison/) · [오픈소스 TTS 라이선스 비교](https://nerdynav.com/open-source-ai-voice/)
- 법률: [Lehrman v. Lovo 분석 (Fredrikson)](https://www.fredlaw.com/alert-federal-court-dismisses-trademark-and-copyright-claims-over-ai-voice-clones-but-leaves-door-open-under-state-publicity-law) · [2026 퍼블리시티권 리스크맵 (Holon Law)](https://holonlaw.com/entertainment-law/synthetic-media-voice-cloning-and-the-new-right-of-publicity-risk-map-for-2026/) · [Fordham IP 논문](https://ir.lawnet.fordham.edu/iplj/vol36/iss4/4/) · [Aoni×CoeFont (ANN)](https://www.animenewsnetwork.com/news/2024-10-08/aoni-production-agency-coefont-collaborate-on-ai-replicated-voice-service-trained-on-voice-actors/.216457) · [카지 유키 Soyogi](https://blog.vive.com/us/who-owns-your-voice-japans-top-voice-actor-clones-with-ai/)

> ⚠️ 검증 노트: 제타 가입자 수치(전자신문)와 디즈니 C&D 세부는 검증 단계가 세션 한도로 일부 미완료(주장 자체는 원문 인용 확보). 나무위키 출처(제타 음성 기능 삭제, Gatebox)는 커뮤니티 문서 특성상 교차 확인 권장.

---

## 부록 A. 사용자의 캐릭터 이름 직접 입력과 분쟁 소지 (2026-07-10 추가 리서치)

**질문**: 설정에서 사용자가 (서브컬처) 캐릭터 이름을 직접 입력할 수 있게 하면 저작권 분쟁 소지가 있는가?

**결론**: 이름 입력 허용 자체는 소지가 낮다. 위험은 이름이 아니라 플랫폼의 행위에서 발생한다.

1. **저작권**: 제호·명칭 단독은 저작물성 부정 (한국 대법원 일관, 미국 short phrases 법리 동일). 단 캐릭터 총체(형상+명칭+성격)는 별개 저작물로 보호 가능 — 대법원 2007다63409(신야구). 위험 지점은 이름이 아니라 "총체적 재현"이며, 이는 자유 텍스트 설정이 있는 한 상존하고 비공개+사용자 영역 포지션이 커버.
2. **상표**: 유명 캐릭터 이름은 다수 상표 등록. 그러나 침해는 출처표시 기능의 "상표적 사용"일 때만 성립 — 사용자의 비공개 컴패니언 명명은 비해당. 플랫폼이 마케팅·추천·검색에 쓰면 해당 (디즈니→Character.AI C&D의 프레임).
3. **사적 이용**: 저작권법 30조. 호스티드 서버 저장의 사적복제 해당 여부는 그레이존이나, 공유 없음 = 공중송신 없음 → 분쟁 성립 구조 자체가 희박. 선례(제타·Character.AI)는 전부 공개 UGC 전제.

**실무 규칙**:
- 이름 입력 자유 (필터링 불필요·과차단 해악)
- 플랫폼은 유명 캐릭터 이름을 프리셋/추천/자동완성으로 제공 금지 (사용자 행위→플랫폼 행위 전환점)
- 마케팅·스크린샷·앱스토어 메타데이터·심사 데모 계정에 IP 노출 금지 (Apple 5.2, 최다 리젝 사유)
- ToS 사용자 책임 조항 + 침해 신고 창구

출처: [대법원 2007다63409](https://casenote.kr/%EB%8C%80%EB%B2%95%EC%9B%90/2007%EB%8B%A463409) · [캐릭터 저작권·상표권 개요](https://www.help-me.kr/blog/article/%EC%BA%90%EB%A6%AD%ED%84%B0%EC%A0%80%EC%9E%91%EA%B6%8C%EA%B3%BC%EC%83%81%ED%91%9C%EA%B6%8C%EC%9D%98%EC%B0%A8%EC%9D%B4%EC%A0%90%EA%B3%BC%EA%B6%8C%EB%A6%AC%ED%99%95%EB%B3%B4%EC%A0%84%EB%9E%B5/) · [상표적 사용 요건](https://www.nepla.ai/wiki/%EC%A7%80%EC%8B%9D%EC%9E%AC%EC%82%B0/%EC%83%81%ED%91%9C/%EC%83%81%ED%91%9C%EA%B6%8C-%EC%B9%A8%ED%95%B4%EC%86%8C%EC%86%A1%EC%97%90%EC%84%9C-%EC%83%81%ED%91%9C%EC%9D%98-%EC%82%AC%EC%9A%A9-%EC%9A%94%EA%B1%B4-%ED%8C%90%EB%8B%A8-6349gp35o9zx) · [미국 캐릭터 보호 법리](https://www.nolo.com/legal-encyclopedia/protecting-fictional-characters-under-copyright-law.html) · [저작권법 30조](https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=695&ccfNo=3&cciNo=2&cnpClsNo=3) · [클라우드와 사적복제](https://brunch.co.kr/@jdglaw1/392) · [Apple App Review Guidelines 5.2](https://developer.apple.com/app-store/review/guidelines/)
