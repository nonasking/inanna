"""대화 루프 — 세션 관리, 프롬프트 조립, 스트리밍, 기억 기록."""
from collections.abc import Iterator

from .. import billing, config
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


def ensure_session(user_id: str, companion: Companion) -> tuple[int, bool]:
    """(session_id, is_new). 새 세션이면 지난 세션들을 요약해 기억으로 넘긴다."""
    sid = db.active_session(user_id, companion.id)
    if sid is not None:
        return sid, False
    sid = db.create_session(user_id, companion.id)
    summarizer.catch_up(user_id, companion.id, exclude_session=sid)
    return sid, True


def greeting(companion: Companion, session_id: int) -> str | None:
    """새 세션의 첫 인사 — first_message가 정의돼 있으면 그것을 사용."""
    if not companion.persona.first_message:
        return None
    text = companion.persona.first_message.replace("{{char}}", companion.name)
    text = text.replace("{{user}}", companion.relationship.calls_me or "너")
    db.add_message(session_id, "assistant", text)
    return text


def chat_stream(user_id: str, companion: Companion, session_id: int,
                user_message: str, extra_context: str = "") -> Iterator[str]:
    """사용자 메시지 처리 → 응답 델타 스트림. 완료 시 DB에 기록.

    주의: 제너레이터가 완주해야 assistant 응답이 저장된다. 중간에 close()하면
    호출자가 축적분을 직접 저장해야 한다 (음성 인터럽트 경로).
    """
    billing.check_chat_quota(user_id)  # 계정 유저 월간 쿼터 (셀프호스팅은 통과)

    # 관계 진행(오랜만/기념일)은 이번 메시지 저장 전 상태 기준으로 계산
    situation = relationship.build_context(user_id, companion)
    if extra_context:
        situation = f"{situation}\n{extra_context}" if situation else extra_context

    db.add_message(session_id, "user", user_message)

    # 기억 = 최근 N개 + 현재 발화와 관련 높은 K개 (시간순 병합)
    recent = db.recent_memories_rows(user_id, companion.id, config.MEMORY_RECENT)
    relevant = recall.get_relevant(
        user_id, companion.id, user_message,
        k=config.MEMORY_RELEVANT, exclude_ids={m["id"] for m in recent})
    memories = [m["content"] for m in sorted(recent + relevant, key=lambda m: m["id"])]

    # 프롬프트 캐시 전략: 시스템(페르소나)+대화 이력이 캐시 프리픽스.
    # 매 턴 바뀌는 것들(recall 기억, 시각, 음성 힌트)은 시스템에 넣으면
    # 뒤따르는 이력 캐시까지 전부 무효화되므로, 마지막 사용자 메시지에 싣는다.
    system = compiler.compile_blocks(companion)
    history = _trim_history(_to_llm_messages(db.session_messages(session_id)))

    ctx_parts = []
    if memories:
        ctx_parts.append("지난 대화의 기억:\n" + "\n".join(f"- {m}" for m in memories))
    if situation:
        ctx_parts.append("지금 상황: " + situation)
    if ctx_parts and history and history[-1]["role"] == "user":
        ctx = "\n\n".join(ctx_parts)
        history[-1] = {"role": "user", "content":
                       f"[컨텍스트 — 상대의 말 아님]\n{ctx}\n[/컨텍스트]\n\n{user_message}"}

    # 제품 모드: 계정 유저의 모델은 티어가 결정 (컴패니언 오버라이드 무시).
    # 어떤 티어든 기억·관계 데이터는 동일하다.
    tiered = billing.effective_model(user_id)
    provider = get_provider(*(tiered or (companion.model.provider, companion.model.name)))
    provider.last_usage = None
    parts: list[str] = []
    for delta in provider.stream_chat(system, history, max_tokens=config.CHAT_MAX_TOKENS):
        parts.append(delta)
        yield delta

    # 오디오 태그([laughs] 등, 통화 중 생성)는 음성 연기용 — 기록에는 남기지 않는다
    reply = strip_audio_tags("".join(parts).strip())
    if reply:
        db.add_message(session_id, "assistant", reply)
    if provider.last_usage:
        db.add_usage(user_id, companion.id, "llm",
                     provider=provider.name, model=provider.model,
                     **provider.last_usage)


def preview_stream(companion: Companion, messages: list[dict]) -> Iterator[str]:
    """빌더 미리보기 — 저장/기억 없이 현재 설정으로만 응답. (요건 P0 '미리보기 대화')"""
    system = compiler.compile_system_prompt(
        companion,
        extra_context="지금은 사용자가 너를 만들어보며 시험 삼아 대화하는 중이다. 설정대로 자연스럽게 반응해라.",
    )
    msgs = [m for m in messages if m.get("role") in ("user", "assistant") and m.get("content")]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    provider = get_provider(companion.model.provider, companion.model.name)
    yield from provider.stream_chat(system, msgs, max_tokens=config.CHAT_MAX_TOKENS)
