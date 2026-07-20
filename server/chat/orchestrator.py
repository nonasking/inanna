"""대화 루프 — 세션 관리, 프롬프트 조립, 스트리밍, 기억 기록."""
import time
from collections.abc import Iterator

from .. import billing, config, safety
from ..companion.schema import Companion
from ..llm import get_provider
from ..memory import db, recall, summarizer
from ..tts.base import strip_audio_tags
from . import compiler, relationship


def _to_llm_messages(rows: list[dict]) -> list[dict]:
    msgs = [{"role": r["role"], "content": r["content"]} for r in rows]
    # 첫 메시지는 user여야 한다 (첫 인사가 assistant로 저장된 경우 대비)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def _trim_history(msgs: list[dict]) -> list[dict]:
    """이력 창 자르기 — 잘리는 지점을 10개 단위로 양자화해 캐시 프리픽스가
    턴마다 밀리지 않게 한다 (매 턴 1개씩 밀리면 캐시가 항상 미스)."""
    if len(msgs) <= config.HISTORY_LIMIT:
        return msgs
    cut = len(msgs) - config.HISTORY_LIMIT
    cut = ((cut + 9) // 10) * 10
    msgs = msgs[cut:]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


# 세션별 휘발 컨텍스트 캐시 — 세션 안에서 기억·상황을 고정해 프롬프트를
# append-only로 유지한다 (위 chat_stream 주석 참고). 기억 구성이 실제로 바뀌면
# 그 턴만 갱신되고(캐시 1회 미스), 이후 다시 안정된다.
_session_ctx: dict[int, dict] = {}


def _session_context(session_id: int, memories: list[str], situation: str) -> dict:
    """세션의 휘발 컨텍스트(기억·상황)를 첫 계산 시점으로 고정한다.

    질의별 recall이 매 턴 다른 기억을 물어오면 시스템 블록이 흔들리고, 로컬 모델의
    KV 캐시는 프롬프트가 직전 요청의 확장일 때만 살아남으므로 매 턴 전체 재처리
    (실측 3천 토큰 = 11~16초)가 된다. 세션 안에서 고정하면 첫 턴만 미스하고 이후는
    캐시 히트(0.3초)다. 대가: 세션 도중의 질의별 recall 적응은 포기 — 대신 이력
    전체가 프롬프트에 있으므로 맥락은 유지되고, 새 기억은 다음 세션에 반영된다.
    """
    cached = _session_ctx.get(session_id)
    if cached is not None:
        return cached                    # 세션 안에서는 불변 — 프롬프트가 append-only
    ctx = {"memories": list(dict.fromkeys(memories))[:config.SESSION_MEMORY_CAP],
           "situation": situation}
    _session_ctx[session_id] = ctx
    if len(_session_ctx) > 200:          # 오래된 세션 정리 (장기 구동 대비)
        for sid in list(_session_ctx)[:100]:
            _session_ctx.pop(sid, None)
    return ctx


def ensure_session(user_id: str, companion: Companion) -> tuple[int, bool]:
    """(session_id, is_new). 새 세션이면 지난 세션들을 요약해 기억으로 넘긴다."""
    sid = db.active_session(user_id, companion.id)
    if sid is not None:
        return sid, False
    sid = db.create_session(user_id, companion.id)
    summarizer.catch_up(user_id, companion.id, exclude_session=sid)
    return sid, True


REVISIT_GAP_DAYS = 3

def proactive_greeting(user_id: str, companion: Companion, session_id: int,
                       gap_days: int) -> str | None:
    """오랜만에 돌아온 사용자에게 컴패니언이 먼저 건네는 인사 (기획 #3).

    실패(쿼터·프로바이더 오류)는 조용히 건너뛴다 — 인사는 보너스지 의무가 아니다.
    """
    try:
        billing.check_chat_quota(user_id)
        system = compiler.compile_blocks(companion)
        memories = db.recent_memories(user_id, companion.id, config.MEMORY_RECENT)
        ctx = ("\n".join(f"- {m}" for m in memories) + "\n\n") if memories else ""
        seed = [{"role": "user", "content":
                 f"[컨텍스트 — 상대의 말 아님]\n{ctx}상대가 {gap_days}일 만에 돌아왔다. "
                 "네가 먼저 반갑게 인사를 건네라 — 관계에 맞는 톤으로, 1~2문장. "
                 "기억에 있는 것만 언급한다.\n[/컨텍스트]"}]
        tiered = billing.effective_model(user_id)
        provider = get_provider(*(tiered or (companion.model.provider, companion.model.name)))
        stats: dict = {}
        text = provider.complete(system, seed, max_tokens=256, stats=stats).strip()
        if not text:
            return None
        text = strip_audio_tags(text)
        db.add_message(session_id, "assistant", text)
        if stats.get("usage"):
            db.add_usage(user_id, companion.id, "llm",
                         provider=provider.name, model=provider.model,
                         **stats["usage"])
        return text
    except Exception:
        return None


def greeting(companion: Companion, session_id: int) -> str | None:
    """새 세션의 첫 인사 — first_message가 정의돼 있으면 그것을 사용."""
    if not companion.persona.first_message:
        return None
    text = companion.persona.first_message.replace("{{char}}", companion.name)
    text = text.replace("{{user}}", companion.relationship.calls_me or "너")
    db.add_message(session_id, "assistant", text)
    return text


def prefill(user_id: str, companion: Companion, session_id: int,
            extra_context: str = "") -> None:
    """실제 대화 프롬프트로 모델의 KV 캐시를 미리 채운다 (통화 시작 등).

    첫 턴이 캐시 미스를 맞으면 프롬프트 재처리(수 초~십수 초)가 그대로 지연이
    된다. 사용자가 말하기 전에 미리 태워두면 첫 응답도 캐시 히트로 시작한다.
    실패는 조용히 무시 — 프리필은 보너스지 의무가 아니다.
    """
    try:
        situation = relationship.build_context(user_id, companion)
        recent = db.recent_memories_rows(user_id, companion.id, config.MEMORY_RECENT)
        memories = [m["content"] for m in recent]
        ctx = _session_context(session_id, memories, situation)
        extra = ctx["situation"]
        if extra_context:
            extra = f"{extra}\n{extra_context}" if extra else extra_context
        extra = _with_farewell(user_id, extra)   # chat_stream과 프리픽스 일치
        system = compiler.compile_blocks(companion, memories=ctx["memories"],
                                         extra_context=extra)
        history = _trim_history(_to_llm_messages(db.session_messages(session_id)))
        if not history:
            history = [{"role": "user", "content": "."}]
        tiered = billing.effective_model(user_id)
        provider = get_provider(*(tiered or (companion.model.provider,
                                             companion.model.name)))
        if not hasattr(provider, "prefill"):
            return
        provider.prefill(system, history)
    except Exception:
        pass


# 남은 출력 토큰이 이 이하면 컴패니언이 자연스럽게 하루를 마무리하게 한다
# (2~3턴 분량). 차단 직전의 "뚝 끊김"을 서사적 마무리로 바꾸는 장치 —
# 제한을 캐릭터의 거절이 아니라 '오늘은 여기까지'라는 관계 이벤트로.
FAREWELL_TOKENS = 800

_FAREWELL_HINT = (
    "오늘 함께할 수 있는 대화가 곧 끝난다. 지금부터는 자연스럽게, 다정하게 "
    "하루를 마무리하는 쪽으로 대화를 이끌어라 — 내일 다시 만나자는 기대를 담아서. "
    "사용량·제한·요금 같은 시스템 사정은 절대 입에 담지 않는다.")


def _with_farewell(user_id: str, extra: str) -> str:
    left = billing.chat_tokens_left(user_id)
    if left is None or left > FAREWELL_TOKENS:
        return extra
    return f"{extra}\n{_FAREWELL_HINT}" if extra else _FAREWELL_HINT


def chat_stream(user_id: str, companion: Companion, session_id: int,
                user_message: str, extra_context: str = "",
                events: dict | None = None) -> Iterator[str]:
    """사용자 메시지 처리 → 응답 델타 스트림. 완료 시 DB에 기록.

    events: 요청별 부가 신호를 받는 dict — 쿼터 80% 통과 시 events["notice"]에
    조용한 안내 문구가 담긴다 (텍스트 채팅 전용; 음성 경로는 넘기지 않아 TTS로
    읽히지 않는다).

    주의: 제너레이터가 완주해야 assistant 응답이 저장된다. 중간에 close()하면
    호출자가 축적분을 직접 저장해야 한다 (음성 인터럽트 경로).
    """
    safety.check_suspended(user_id)    # 정지 계정 차단 (셀프호스팅 오너는 통과)
    billing.check_chat_quota(user_id)  # 계정 유저 월간 쿼터 (셀프호스팅은 통과)

    # 관계 진행(오랜만/기념일)은 이번 메시지 저장 전 상태 기준으로 계산.
    # extra_context(음성 힌트 등)는 세션 고정 컨텍스트와 별개로 매 턴 붙인다 —
    # 상수라 프롬프트는 여전히 안정적이다.
    situation = relationship.build_context(user_id, companion)

    db.add_message(session_id, "user", user_message)

    # 기억 = 최근 N개 + 현재 발화와 관련 높은 K개 (시간순 병합)
    recent = db.recent_memories_rows(user_id, companion.id, config.MEMORY_RECENT)
    relevant = recall.get_relevant(
        user_id, companion.id, user_message,
        k=config.MEMORY_RELEVANT, exclude_ids={m["id"] for m in recent})
    memories = [m["content"] for m in sorted(recent + relevant, key=lambda m: m["id"])]

    # 프롬프트 캐시 전략 (2026-07-12 실측으로 재설계):
    # 메시지 배열은 순수 누적(append-only)이어야 캐시가 산다. 로컬 모델(ollama/
    # llama.cpp)의 KV 캐시는 "직전 요청의 프롬프트가 이번 프롬프트의 접두사일 때"만
    # 재사용되므로, 매 턴 마지막 메시지에 기억·상황을 끼워 넣으면(예전 방식) 다음
    # 턴에 그 자리가 원문으로 돌아가며 캐시가 통째로 깨진다(실측: 프롬프트 재처리
    # 2.5s). 그래서 휘발 컨텍스트는 시스템 블록에 싣고 세션 동안 고정한다 —
    # 이력은 원문 그대로 쌓이므로 프롬프트가 append-only가 된다.
    ctx = _session_context(session_id, memories, situation)
    extra = ctx["situation"]
    if extra_context:
        extra = f"{extra}\n{extra_context}" if extra else extra_context
    # 잔량이 바닥에 가까우면 마무리 힌트 — 힌트가 붙는 첫 턴만 캐시 미스이고,
    # 잔량은 계속 낮으므로 이후 턴은 다시 안정적이다.
    extra = _with_farewell(user_id, extra)
    system = compiler.compile_blocks(companion, memories=ctx["memories"],
                                     extra_context=extra)
    history = _trim_history(_to_llm_messages(db.session_messages(session_id)))

    # 제품 모드: 계정 유저의 모델은 티어가 결정 (컴패니언 오버라이드 무시).
    # 어떤 티어든 기억·관계 데이터는 동일하다.
    tiered = billing.effective_model(user_id)
    provider = get_provider(*(tiered or (companion.model.provider, companion.model.name)))
    # 프로바이더 인스턴스는 lru_cache로 여러 요청이 공유하므로, 결과는 요청-로컬
    # stats에 받는다 (인스턴스 속성에 쓰면 동시 요청이 서로 덮어 거절·사용량이
    # 엉뚱한 계정에 귀속된다).
    stats: dict = {}
    parts: list[str] = []
    t0 = time.monotonic()
    ttft = None
    for delta in provider.stream_chat(system, history,
                                      max_tokens=config.CHAT_MAX_TOKENS, stats=stats):
        if ttft is None:
            ttft = time.monotonic() - t0
        parts.append(delta)
        yield delta
    u = stats.get("usage") or {}
    pe = stats.get("prompt_eval")
    print(f"[chat {companion.id}] {provider.name}/{provider.model} "
          f"ttft {ttft or 0:.2f}s total {time.monotonic() - t0:.2f}s "
          f"in={u.get('input_tokens', '?')} out={u.get('output_tokens', '?')}"
          + (f" prompt_eval {pe:.2f}s" if pe is not None else ""),
          flush=True)

    # 오디오 태그([laughs] 등, 통화 중 생성)는 음성 연기용 — 기록에는 남기지 않는다
    reply = strip_audio_tags("".join(parts).strip())
    if reply:
        db.add_message(session_id, "assistant", reply)
    if stats.get("usage"):
        db.add_usage(user_id, companion.id, "llm",
                     provider=provider.name, model=provider.model,
                     **stats["usage"])
        if events is not None:
            notice = billing.quota_notice(user_id, stats["usage"].get("output_tokens", 0))
            if notice:
                events["notice"] = notice
    # 프로바이더가 안전 정책으로 거절했으면 '사실'만 기록 (내용 판정은 하지 않는다)
    if stats.get("refusal"):
        safety.record_refusal(user_id, companion.id)


def preview_stream(user_id: str, companion: Companion,
                   messages: list[dict]) -> Iterator[str]:
    """빌더 미리보기 — 저장/기억 없이 현재 설정으로만 응답. (요건 P0 '미리보기 대화')

    보안(H1): 요청 본문의 Companion.model은 계정 유저에게는 무시된다 —
    티어가 모델을 강제하고, 사용량도 기록한다 (무기록 우회 방지).
    """
    safety.check_suspended(user_id)
    billing.check_chat_quota(user_id)
    system = compiler.compile_system_prompt(
        companion,
        extra_context="지금은 사용자가 너를 만들어보며 시험 삼아 대화하는 중이다. 설정대로 자연스럽게 반응해라.",
    )
    msgs = [m for m in messages if m.get("role") in ("user", "assistant") and m.get("content")]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    tiered = billing.effective_model(user_id)
    provider = get_provider(*(tiered or (companion.model.provider, companion.model.name)))
    stats: dict = {}
    yield from provider.stream_chat(system, msgs,
                                    max_tokens=config.CHAT_MAX_TOKENS, stats=stats)
    if stats.get("usage"):
        db.add_usage(user_id, companion.id, "llm",
                     provider=provider.name, model=provider.model,
                     **stats["usage"])
    if stats.get("refusal"):
        safety.record_refusal(user_id, companion.id)
