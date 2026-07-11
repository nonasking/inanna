"""세션 요약 → 기억(episodic). 새 세션이 열릴 때 지난 미요약 세션을 정리한다."""
import datetime

from ..llm import get_summary_provider
from . import db

SUMMARY_SYSTEM = (
    "너는 대화 기록을 '캐릭터의 기억'으로 요약하는 도우미다. "
    "아래 대화에서 캐릭터가 다음에 만났을 때 기억하고 있어야 할 것만 뽑아 "
    "한국어로 1~4줄로 요약해라. 각 줄은 '- '로 시작한다. "
    "사용자에 대해 알게 된 사실, 나눈 약속, 감정적으로 중요한 순간을 우선한다. "
    "사소한 잡담은 버린다. 마지막 줄에는 반드시 '- 분위기: <한 단어>' 형식으로 "
    "그 대화의 감정 톤(예: 즐거움, 위로, 설렘, 다툼, 차분함)을 적어라. "
    "요약 외의 말은 하지 마라."
)


def summarize_session(user_id: str, companion_id: str, session_id: int) -> str | None:
    messages = db.session_messages(session_id)
    if len(messages) < 2:
        db.mark_summarized(session_id)
        return None

    date = datetime.datetime.fromtimestamp(messages[0]["ts"]).strftime("%Y-%m-%d")
    transcript = "\n".join(
        f"{'사용자' if m['role'] == 'user' else '나'}: {m['content']}" for m in messages
    )
    # 아주 긴 세션은 뒷부분 위주로 (최근 맥락이 기억 가치가 높다)
    if len(transcript) > 24000:
        transcript = transcript[-24000:]

    try:
        summary = get_summary_provider().complete(
            SUMMARY_SYSTEM,
            [{"role": "user", "content": transcript}],
            max_tokens=500,
        ).strip()
    except Exception:
        return None  # 요약 실패는 대화를 막지 않는다 — 다음 기회에 재시도

    if summary:
        db.add_memory(user_id, companion_id, f"[{date}] {summary}", source_session=session_id)
    db.mark_summarized(session_id)
    return summary


def catch_up(user_id: str, companion_id: str, exclude_session: int | None = None) -> None:
    for sid in db.unsummarized_sessions(user_id, companion_id, exclude=exclude_session):
        summarize_session(user_id, companion_id, sid)
