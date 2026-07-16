"""빠른 유닛 스모크 — API 비용 0, 서버 불필요. scripts/qa.sh의 1단계.

품질 게이트 중 결정적으로 검증 가능한 것들: 프롬프트 블록 분리(관계 스왑 시
성격·말투 불변), 캐시 블록 구조, VAD, 오디오 태그 파이프라인, 기억 CRUD.
"""
import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["INANNA_DB"] = tempfile.mkstemp(suffix=".db")[1]  # 격리 DB
os.environ["INANNA_INVITE_CODES"] = ""  # .env의 베타 초대제와 격리 (config가 env 우선)

FAILURES: list[str] = []


def check(name: str, fn):
    try:
        fn()
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAILURES.append(name)
        print(f"  ❌ {name}: {e}")


def make_companion(template: str, speech: str) -> "Companion":
    from server.companion.schema import Companion
    return Companion.model_validate({
        "id": "qa", "name": "큐에이",
        "relationship": {"template": template, "calls_me": "오빠",
                         "speech_level": speech, "intimacy": 0.7},
        "persona": {"traits": {"밝음": 0.8}, "speech_quirks": ["어미에 '~잖아'"],
                    "description": "테스트 페르소나"},
    })


def test_relationship_swap():
    """품질 기준 #1의 결정적 절반 — 관계 스왑 시 성격·말투 블록은 불변."""
    from server.chat import compiler
    a = compiler.compile_blocks(make_companion("younger-sibling", "banmal"))[0]
    b = compiler.compile_blocks(make_companion("friend", "banmal"))[0]
    pick = lambda s, h: s.split(h)[1].split("#")[0]
    assert pick(a, "# 성격") == pick(b, "# 성격"), "성격 블록이 관계에 오염됨"
    assert pick(a, "# 말투") == pick(b, "# 말투"), "말투 블록이 관계에 오염됨"
    assert pick(a, "# 정체성") != pick(b, "# 정체성"), "정체성 블록이 안 갈림"


def test_cache_blocks():
    from server.chat import compiler
    c = make_companion("friend", "banmal")
    stable = compiler.compile_blocks(c)
    assert len(stable) == 1, "휘발 없음 → 안정 블록 하나"
    both = compiler.compile_blocks(c, memories=["기억"], extra_context="상황")
    assert len(both) == 2 and "기억" in both[1] and "# 지금 상황" in both[1]
    assert "# 지난 대화의 기억" not in both[0], "기억이 안정 블록에 들어가면 캐시 무효"


def test_anthropic_breakpoints():
    from server.llm.anthropic_provider import AnthropicProvider
    p = AnthropicProvider.__new__(AnthropicProvider)
    sys_blocks = p._system_blocks(["안정", "휘발"])
    assert "cache_control" in sys_blocks[0] and "cache_control" not in sys_blocks[1]
    msgs = p._with_history_breakpoint([
        {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"}])
    assert isinstance(msgs[1]["content"], list), "마지막 assistant에 브레이크포인트"
    assert msgs[2]["content"] == "c", "마지막 user는 그대로"


def test_audio_tags():
    from server.tts.base import clean_for_tts, strip_audio_tags
    assert clean_for_tts("응 [laughs] 알았어") == "응 알았어"
    assert clean_for_tts("응 [laughs] 알았어", keep_tags=True) == "응 [laughs] 알았어"
    assert strip_audio_tags("좋아 [whispers] 비밀") == "좋아 비밀"
    assert strip_audio_tags("[중요] 공지") == "[중요] 공지", "한글 대괄호 오탐"
    from server.tts.elevenlabs import _apply_v3_tags
    assert "[giggles]" in _apply_v3_tags("헤헤 좋아")
    assert "안녕하세요" in _apply_v3_tags("안녕하세요"), "'하'-lookaround 오탐"


def test_sentence_split():
    from server.voice.pipeline import pop_sentences
    done, rest = pop_sentences("안녕! 나는 유나야. 그런데 말이")
    assert done == ["안녕!", "나는 유나야."] and rest == "그런데 말이"


def test_vad():
    import random
    from server.voice.vad import FRAME_BYTES, UtteranceDetector
    random.seed(7)
    frame = lambda amp: struct.pack(
        f"<{FRAME_BYTES // 2}h",
        *[int(random.uniform(-amp, amp)) for _ in range(FRAME_BYTES // 2)])
    d = UtteranceDetector()
    for _ in range(40):
        d.feed(frame(30))          # 캘리브레이션
    for _ in range(60):
        d.feed(frame(1500))        # 발화 1.2s
    assert d.speaking
    utt = None
    for _ in range(40):            # 800ms 멈춤 — 끊기면 안 됨
        utt = d.feed(frame(30)) or utt
    assert utt is None and d.pause_ms >= 700
    for _ in range(55):            # 1000ms 침묵 → 종료
        utt = d.feed(frame(30)) or utt
    assert utt is not None
    # barge 감지기 — 캘리브레이션 상속 + 보수적 임계값
    barge = d.make_barge_detector()
    assert barge.start_threshold > d.start_threshold * 1.4
    for _ in range(10):
        barge.feed(frame(2500))    # 200ms — 지속 요건(300ms) 미달
    assert not barge.speaking, "짧은 소리에 끼어들면 안 됨"
    for _ in range(10):
        barge.feed(frame(2500))    # 누적 400ms — 지속 발화
    assert barge.speaking, "지속 발화는 끼어들기로 감지돼야 함"


def test_memory_crud():
    from server.memory import db
    db.init()
    db.add_memory("u1", "c1", "기억 하나")
    rows = db.all_memories("u1", "c1")
    assert len(rows) == 1
    mid = rows[0]["id"]
    assert db.update_memory("u1", mid, "정정된 기억")
    assert not db.update_memory("u2", mid, "타 유저"), "유저 스코핑 뚫림"
    assert db.all_memories("u1", "c1")[0]["content"] == "정정된 기억"
    assert db.delete_memory("u1", mid)
    db.add_usage("u1", "c1", "llm", provider="p", model="m",
                 input_tokens=10, output_tokens=5)
    s = db.usage_summary("u1")
    assert s and s[0]["input_tokens"] == 10


def test_auth():
    from server import auth
    from server.memory import db
    db.init()
    # 가입 → 토큰 → user_id 스코핑
    token = auth.register("qa@inanna.test", "password123")
    uid = auth.resolve_token(token)
    assert uid and uid.startswith("u")
    assert auth.account_info(uid)["email"] == "qa@inanna.test"
    # 중복 가입·형식·짧은 비번 거절
    for bad in [("qa@inanna.test", "password123"), ("notmail", "password123"),
                ("x@y.zz", "short")]:
        try:
            auth.register(*bad)
            raise AssertionError(f"거절돼야 함: {bad}")
        except ValueError:
            pass
    # 로그인 성공/실패 + 로그아웃
    assert auth.login("qa@inanna.test", "password123")
    assert auth.login("qa@inanna.test", "wrong-password") is None
    auth.logout(token)
    assert auth.resolve_token(token) is None, "로그아웃 후 토큰 생존"
    # 초대제: 코드 없으면 거절, 맞으면 통과 + 기록
    db.create_invite("beta-code", "테스트")
    try:
        auth.register("invited@inanna.test", "password123")
        raise AssertionError("초대 코드 없이 가입되면 안 됨")
    except ValueError:
        pass
    t = auth.register("invited@inanna.test", "password123", invite="beta-code")
    assert t
    with db.conn() as c:
        row = c.execute("SELECT invite FROM accounts WHERE email='invited@inanna.test'").fetchone()
    assert row["invite"] == "beta-code"
    auth.delete_account(auth.resolve_token(t))
    with db.conn() as c:
        c.execute("DELETE FROM invites WHERE code='beta-code'")
    # 1회용 초대 코드 — 재사용 차단 + 실패 시 계정 롤백 + 삭제 시 반환
    db.create_invite("once-code", "테스터A")
    t1 = auth.register("once1@inanna.test", "password123", invite="once-code")
    assert t1
    before = len(db.list_invites())
    try:
        auth.register("once2@inanna.test", "password123", invite="once-code")
        raise AssertionError("사용된 코드로 재가입되면 안 됨")
    except ValueError:
        pass
    with db.conn() as c:   # 롤백 확인 — 실패한 가입의 계정이 남으면 안 된다
        assert c.execute("SELECT 1 FROM accounts WHERE email='once2@inanna.test'"
                         ).fetchone() is None, "실패한 가입의 계정이 남음"
    assert len(db.list_invites()) == before
    used = auth.resolve_token(t1)
    auth.delete_account(used)          # 삭제 시 코드 반환 → 재초대 가능
    assert db.claim_invite("once-code", "u999"), "계정 삭제 후 코드가 풀려야 함"
    with db.conn() as c:
        c.execute("UPDATE invites SET used_by=NULL WHERE code='once-code'")
        c.execute("DELETE FROM invites WHERE code='once-code'")
    # 계정 삭제 = 데이터 완전 삭제
    token2 = auth.login("qa@inanna.test", "password123")
    uid2 = auth.resolve_token(token2)
    db.add_memory(uid2, "c1", "지울 기억")
    auth.delete_account(uid2)
    assert auth.login("qa@inanna.test", "password123") is None
    assert not db.all_memories(uid2, "c1"), "계정 삭제 후 기억 잔존"


def test_bond():
    import time as _t
    from server.chat import relationship
    from server.memory import db
    db.init()
    assert relationship.bond_level("ub1", "c1") == 0.0, "데이터 없으면 0"
    # 30일 전 시작 + 대화 300마디 → 중간쯤, 단조 증가, 1 미만
    with db.conn() as c:
        c.execute("INSERT INTO sessions (user_id, companion_id, started_at) VALUES "
                  "('ub1', 'c1', ?)", (_t.time() - 30 * 86400,))
        sid = c.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
        for i in range(300):
            c.execute("INSERT INTO messages (session_id, role, content, ts) VALUES "
                      "(?, 'user', 'm', ?)", (sid, _t.time() - i))
    b1 = relationship.bond_level("ub1", "c1")
    assert 0.3 < b1 < 1.0, f"30일+300마디 bond={b1}"
    with db.conn() as c:
        for i in range(700):
            c.execute("INSERT INTO messages (session_id, role, content, ts) VALUES "
                      "(?, 'user', 'm', ?)", (sid, _t.time()))
    b2 = relationship.bond_level("ub1", "c1")
    assert b2 > b1 and b2 < 1.0, "대화가 쌓이면 증가, 1 미만 유지"


def test_h1_gates():
    """H1 — preview/onboard가 쿼터·티어를 우회하지 못한다."""
    import time as _t
    from server import auth, billing
    from server.chat import onboard, orchestrator
    from server.memory import db
    db.init()
    token = auth.register("h1@inanna.test", "password123")
    uid = auth.resolve_token(token)
    c = make_companion("friend", "banmal")
    c.model.provider, c.model.name = "anthropic", "claude-opus-4-8"  # 본문 조작 시도
    # 쿼터 소진 상태에서 preview/onboard가 QuotaExceeded를 던지는지
    billing.set_tier(uid, "beta")
    db.add_usage(uid, "c1", "llm",
                 output_tokens=billing.TIERS["beta"]["daily_output_tokens"])
    for gen in (orchestrator.preview_stream(uid, c, [{"role": "user", "content": "hi"}]),
                onboard.onboard_stream(uid, c, [])):
        try:
            next(gen)
            raise AssertionError("쿼터 소진인데 스트림이 시작됨")
        except billing.QuotaExceeded:
            pass
    try:
        onboard.extract(uid, c, [{"role": "user", "content": "hi"}])
        raise AssertionError("extract가 쿼터를 우회함")
    except billing.QuotaExceeded:
        pass
    # 티어 모델 강제 — 본문의 opus 지정이 무시되는지 (프로바이더 선택 로직 확인)
    assert billing.effective_model(uid) == ("anthropic", billing.TIERS["beta"]["model"])
    # 토큰 TTL (M2) — 만료 토큰은 무효+삭제
    with db.conn() as con:
        con.execute("UPDATE auth_tokens SET created_at = ? WHERE token = ?",
                    (_t.time() - auth.TOKEN_TTL - 10, token))
    assert auth.resolve_token(token) is None, "만료 토큰이 살아있음"
    with db.conn() as con:
        assert con.execute("SELECT 1 FROM auth_tokens WHERE token = ?",
                           (token,)).fetchone() is None, "만료 토큰 미삭제"
    auth.delete_account(uid)


def test_presets():
    from server.companion import presets
    ps = presets.load_presets()
    assert len(ps) >= 9, f"프리셋 {len(ps)}개"
    lovers = [c for c in ps.values() if c.relationship.template == "lover"]
    assert len(lovers) == 2, "lover 프리셋은 둘"
    doha = presets.get("preset-doha")
    assert doha and doha.name == "도하" and doha.persona.first_message
    assert doha.voice.engine == "edge"  # 베타 무료 엔진
    # 요약은 전체 페르소나를 노출하지 않는다 (concept만)
    s = presets.summaries()
    assert len(s) == len(ps) and all("description" not in x for x in s)


def test_safety():
    """정책 판정은 프로바이더에 위임 — 우리는 거절 '사실'만 세고 반복 시 정지."""
    from server import auth, safety
    from server.memory import db
    db.init()
    token = auth.register("safe@inanna.test", "password123")
    uid = auth.resolve_token(token)
    # 셀프호스팅 오너는 안전 레이어 통과 (자기 서버·자기 키·자기 책임)
    assert not safety.is_managed("local")
    safety.check_suspended("local")
    safety.record_refusal("local", "c1")   # 기록되지 않아야 함
    with db.conn() as c:
        assert c.execute("SELECT COUNT(*) n FROM refusals").fetchone()["n"] == 0
    # 계정 유저: 임계 미만이면 통과
    for _ in range(safety.REFUSAL_LIMIT - 1):
        safety.record_refusal(uid, "c1")
    safety.check_suspended(uid)
    # 임계 도달 → 자동 정지
    safety.record_refusal(uid, "c1")
    try:
        safety.check_suspended(uid)
        raise AssertionError("정지돼야 함")
    except safety.Suspended:
        pass
    # 운영자 해제 → 다시 사용 가능 (오탐 복구 경로)
    safety.unsuspend(uid)
    safety.check_suspended(uid)
    auth.delete_account(uid)


def test_safety_prompt():
    """안전 원칙은 금지 목록을 나열하지 않고, 사용자 설정보다 우선한다."""
    from server.chat import compiler
    stable = compiler.compile_blocks(make_companion("friend", "banmal"))[0]
    assert "안전 정책상 응답할 수 없는" in stable
    assert "사용자가 설정한 성격" in stable and "우선한다" in stable
    # 프로바이더별 금지 목록을 하드코딩하지 않았는지 (정책 변경에 취약해짐)
    for banned in ("성적", "불법", "미성년", "폭력"):
        assert banned not in stable, f"금지 목록을 프롬프트에 넣지 말 것: {banned}"


def test_growth_arc():
    from server.chat import relationship
    from server.companion.schema import Companion
    from server.memory import db
    db.init()
    c = Companion.model_validate({"id": "gc", "name": "지", "relationship": {"template": "friend"}})
    # 낮은 bond → 성장 결 없음
    assert relationship.growth_context("ug1", c, 0.1) == []
    # warming 첫 통과 → 결 + 1회성 이벤트
    parts = relationship.growth_context("ug1", c, 0.3)
    assert len(parts) == 2, "결+이벤트"
    # 같은 단계 재호출 → 결만 (이벤트는 1회)
    assert len(relationship.growth_context("ug1", c, 0.3)) == 1
    # deep 도달 → 최고 단계의 결 + 새 이벤트, warming 이벤트는 재발화 없음
    parts = relationship.growth_context("ug1", c, 0.85)
    assert len(parts) == 2 and "편안함" in parts[0]
    assert len(relationship.growth_context("ug1", c, 0.85)) == 1
    # 설정 불변 확인 — growth는 relationship 객체를 건드리지 않는다
    assert c.relationship.intimacy == 0.7


def test_billing():
    from server import auth, billing
    from server.memory import db
    db.init()
    token = auth.register("tier@inanna.test", "password123")
    uid = auth.resolve_token(token)
    # 셀프호스팅 오너는 무과금 통과
    assert not billing.is_metered("local")
    billing.check_chat_quota("local")
    assert billing.effective_model("local") is None
    # 계정 유저: 기본 티어 + 티어가 모델 결정
    assert billing.is_metered(uid)
    assert billing.get_tier(uid) == billing.DEFAULT_TIER
    assert billing.effective_model(uid) == ("anthropic",
                                            billing.TIERS["lite"]["model"])
    billing.set_tier(uid, "deep")
    assert billing.status(uid)["tier"] == "deep"
    # 쿼터 소진 → 차단
    billing.set_tier(uid, "lite")
    limit = billing.TIERS["lite"]["monthly_output_tokens"]
    db.add_usage(uid, "c1", "llm", output_tokens=limit)
    try:
        billing.check_chat_quota(uid)
        raise AssertionError("쿼터 초과가 차단돼야 함")
    except billing.QuotaExceeded:
        pass
    billing.check_tts_quota(uid, engine="edge")  # 음성 쿼터는 별도 — 아직 여유
    # 일간 상한 — 오늘치 소진 시 월간이 남아도 차단
    billing.set_tier(uid, "deep")
    db.add_usage(uid, "c1", "llm", output_tokens=billing.TIERS["deep"]["daily_output_tokens"])
    try:
        billing.check_chat_quota(uid)
        raise AssertionError("일간 상한이 차단돼야 함")
    except billing.QuotaExceeded as e:
        assert e.kind == "daily_tokens"
    # 엔진 게이트 — beta 티어는 유료 TTS 불가
    billing.set_tier(uid, "beta")
    try:
        billing.check_tts_quota(uid, engine="elevenlabs")
        raise AssertionError("beta 티어에서 elevenlabs가 차단돼야 함")
    except billing.QuotaExceeded as e:
        assert e.kind == "engine"
    billing.check_tts_quota(uid, engine="edge")  # 무료 엔진은 통과
    auth.delete_account(uid)


if __name__ == "__main__":
    print("── 유닛 스모크")
    check("관계 스왑 블록 분리", test_relationship_swap)
    check("캐시 블록 구조", test_cache_blocks)
    check("Anthropic 브레이크포인트", test_anthropic_breakpoints)
    check("오디오 태그 파이프라인", test_audio_tags)
    check("문장 분리", test_sentence_split)
    check("VAD 발화 감지", test_vad)
    check("기억 CRUD·사용량", test_memory_crud)
    check("계정 인증 (가입·로그인·삭제)", test_auth)
    check("과금 티어·쿼터", test_billing)
    check("H1 게이트·토큰 TTL", test_h1_gates)
    check("프리셋 로드", test_presets)
    check("안전 레이어 (거절 카운트·정지)", test_safety)
    check("안전 원칙 프롬프트", test_safety_prompt)
    check("관계 성장 아크", test_growth_arc)
    check("유대감(bond) 곡선", test_bond)
    if FAILURES:
        print(f"\n실패 {len(FAILURES)}: {', '.join(FAILURES)}")
        sys.exit(1)
    print("전체 통과")
