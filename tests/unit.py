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
    billing.check_tts_quota(uid)  # 음성 쿼터는 별도 — 아직 여유
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
    check("유대감(bond) 곡선", test_bond)
    if FAILURES:
        print(f"\n실패 {len(FAILURES)}: {', '.join(FAILURES)}")
        sys.exit(1)
    print("전체 통과")
