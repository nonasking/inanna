"""첫 만남 온보딩 — 폼이 아니라 대화로 컴패니언이 형성된다.

흐름: 관계·이름만 명시 선택(계약) → 원형(proto) 컴패니언과 첫 만남 대화
→ 대화에서 성격·말투·호칭을 추출(요약 모델 = 품질 필요, 1회성)
→ 컴패니언의 입으로 확인 → 저장. 온보딩 대화는 '처음 만난 날'의
첫 기억이 되어 남는다 (버려지는 설정 절차가 아니라 관계의 시작).

직접 설정(빌더)은 그대로 존치 — 형성된 값은 편집 화면에 전부 노출된다.
"""
import datetime
import json
import re
from collections.abc import Iterator

from ..companion.schema import Companion
from ..llm import get_provider, get_summary_provider
from ..memory import db
from . import compiler

ONBOARD_HINT = (
    "지금은 사용자와 '처음 만나는' 대화다. 아직 서로를 모른다 — 설정된 관계의 "
    "출발점에서, 가볍게 인사하고 서로를 알아가라. 상대의 말투·반응·취향에 맞춰 "
    "네 성격이 형성되는 중이다: 상대가 편안해할 결을 찾아가되, 줏대 없이 "
    "맞추기만 하지는 마라(네 색깔이 생겨야 한다). 질문은 한 번에 하나, "
    "취조하지 말고 자연스럽게. 한 번에 1~3문장."
)

# 온보딩 대화는 모델이 먼저 말을 건다 (Anthropic은 첫 메시지가 user여야 함)
_SEED = {"role": "user", "content":
         "(첫 만남이다. 네가 먼저 자연스럽게 인사를 건네라 — 이 지시문은 상대에게 보이지 않는다)"}

_EXTRACT_SYSTEM = (
    "너는 대화록에서 화자(컴패니언)의 형성된 성격을 구조화하는 도구다. "
    "JSON 외의 어떤 텍스트도 출력하지 마라."
)

_EXTRACT_PROMPT = """아래는 '{name}'(관계: {template})와 사용자의 첫 만남 대화다.
이 대화에서 형성된 {name}의 성격을 추출해 JSON으로 출력해라.

규칙:
- traits: {{"밝음","다정함","장난기","직설","애교"}} 각 0.0~1.0 (대화에서 드러난 정도)
- speech_quirks: 대화에서 실제로 쓴 특징적 말버릇 0~3개 (없으면 빈 배열, 지어내지 마라)
- description: 2~4문장 — 대화에서 드러난 성격·취향·배경. 대화에 없는 건 쓰지 마라
- calls_me: {name}가 사용자를 부르기로 한 호칭 (대화에서 정해졌으면, 아니면 "")
- speech_level: "banmal" | "jondaemal" | "mixed" (대화에서 {name}가 쓴 말투)
- confirm: {name}의 말투로, 방금 나눈 대화를 바탕으로 "나 이런 사람인 것 같은데, 맞지?" 느낌의
  확인 대사 1~2문장 (자기 성격 요약을 자연스럽게 담아서)
- first_memory: "처음 만난 날" 기억 한 문장 — 무슨 얘기를 나눴고 어떤 분위기였는지

대화록:
{transcript}

JSON:"""


def _providers(user_id: str):
    """(선호, 폴백).

    셀프호스팅 오너: 요약 모델(좋은 모델) 우선, 실패 시 대화 기본으로 폴백.
    계정(과금) 유저: 티어 모델로 강제 — 온보딩이 쿼터·티어를 우회하는
    경로가 되지 않게 한다 (보안 H1).
    """
    from .. import billing
    tiered = billing.effective_model(user_id)
    if tiered:
        return get_provider(*tiered), None
    preferred = get_summary_provider()
    fallback = get_provider()
    return preferred, (fallback if fallback is not preferred else None)


def _record(user_id: str, companion: Companion, provider, stats: dict) -> None:
    from .. import safety
    if stats.get("usage"):
        db.add_usage(user_id, companion.id, "llm",
                     provider=provider.name, model=provider.model,
                     **stats["usage"])
    # 첫 만남도 실제 모델·실제 비용이 드는 경로 — preview와 대칭으로 거절을 집계한다
    # (한쪽만 비면 그쪽으로 악용이 몰린다).
    if stats.get("refusal"):
        safety.record_refusal(user_id, companion.id)


def onboard_stream(user_id: str, companion: Companion,
                   messages: list[dict]) -> Iterator[str]:
    """원형 컴패니언과의 첫 만남 대화 — 무저장(사용량은 기록)."""
    from .. import billing, safety
    safety.check_suspended(user_id)
    billing.check_chat_quota(user_id)
    system = compiler.compile_system_prompt(companion, extra_context=ONBOARD_HINT)
    msgs = [m for m in messages
            if m.get("role") in ("user", "assistant") and m.get("content")]
    msgs.insert(0, _SEED)
    preferred, fallback = _providers(user_id)
    stats: dict = {}
    try:
        yield from preferred.stream_chat(system, msgs, max_tokens=1024, stats=stats)
        _record(user_id, companion, preferred, stats)
    except Exception:
        if fallback is None:
            raise
        stats = {}
        yield from fallback.stream_chat(system, msgs, max_tokens=1024, stats=stats)
        _record(user_id, companion, fallback, stats)


def extract(user_id: str, companion: Companion, messages: list[dict]) -> dict:
    transcript = "\n".join(
        f"{'사용자' if m['role'] == 'user' else companion.name}: {m['content']}"
        for m in messages if m.get("content"))
    prompt = _EXTRACT_PROMPT.format(
        name=companion.name, template=companion.relationship.template,
        transcript=transcript)
    from .. import billing, safety
    safety.check_suspended(user_id)
    billing.check_chat_quota(user_id)
    preferred, fallback = _providers(user_id)
    msg = [{"role": "user", "content": prompt}]
    try:
        raw = preferred.complete(_EXTRACT_SYSTEM, msg, max_tokens=1024)
    except Exception:
        if fallback is None:
            raise
        raw = fallback.complete(_EXTRACT_SYSTEM, msg, max_tokens=1024)
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.M).strip()
    # 로컬 모델이 JSON 앞뒤로 잡담을 붙이는 경우 대비 — 최외곽 객체만 취한다
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    data = json.loads(raw)
    # 스키마 범위로 정리 (모델 출력 방어)
    return {
        "traits": {k: max(0.0, min(1.0, float(v)))
                   for k, v in (data.get("traits") or {}).items()},
        "speech_quirks": [str(q) for q in (data.get("speech_quirks") or [])][:3],
        "description": str(data.get("description", "")),
        "calls_me": str(data.get("calls_me", "")),
        "speech_level": data.get("speech_level")
        if data.get("speech_level") in ("banmal", "jondaemal", "mixed") else "banmal",
        "confirm": str(data.get("confirm", "")),
        "first_memory": str(data.get("first_memory", "")),
    }


_ID_OK = re.compile(r"[a-z0-9_-]{1,64}")


def _safe_id(companion: Companion) -> str:
    """클라이언트가 준 id가 서버 규칙([a-z0-9_-])에 안 맞으면(한글 이름 등)
    안전한 id를 생성한다. 이름은 companion.name에 그대로 남는다."""
    if _ID_OK.fullmatch(companion.id):
        return companion.id
    import secrets
    return f"c-{secrets.token_hex(4)}"


def complete(user_id: str, companion: Companion, messages: list[dict],
             first_memory: str) -> None:
    """저장 + 온보딩 대화를 첫 세션·첫 기억으로 남긴다."""
    from ..companion import store
    companion.id = _safe_id(companion)   # 한글 이름 등으로 온 잘못된 id 방어
    store.save(user_id, companion)
    sid = db.create_session(user_id, companion.id)
    for m in messages:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            db.add_message(sid, m["role"], m["content"])
    db.mark_summarized(sid)  # 첫 기억은 아래에서 직접 쓴다 (중복 요약 방지)
    today = datetime.date.today().isoformat()
    line = first_memory or "서로 인사를 나누고 알아가기 시작했다."
    db.add_memory(user_id, companion.id, f"[{today}] 처음 만난 날 — {line}",
                  source_session=sid)
