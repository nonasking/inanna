"""관계 진행 컨텍스트 — 시간의 흐름을 컴패니언이 인지하게 한다.

함께한 일수, 기념일, 오랜만 감지, 현재 시각을 '지금 상황' 블록으로 만든다.
사용자가 설정한 거리감(intimacy)은 건드리지 않는다 — 설정은 사용자의 것,
시간의 흐름은 상황의 것.
"""
import datetime
import time

from ..companion.schema import Companion
from ..memory import db

MILESTONES = (50, 100, 200, 300, 365, 500, 730, 1000)
_WEEKDAYS = "월화수목금토일"


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 11:
        return "아침"
    if 11 <= hour < 14:
        return "점심때"
    if 14 <= hour < 18:
        return "오후"
    if 18 <= hour < 22:
        return "저녁"
    return "밤늦은 시간"


def build_context(user_id: str, companion: Companion) -> str:
    now = time.time()
    dt = datetime.datetime.fromtimestamp(now)
    parts = [
        f"오늘은 {dt.year}년 {dt.month}월 {dt.day}일 {_WEEKDAYS[dt.weekday()]}요일, "
        f"지금은 {_time_of_day(dt.hour)}({dt.hour}시경)이다."
    ]

    stats = db.relationship_stats(user_id, companion.id)
    if stats:
        days = int((now - stats["first_ts"]) // 86400) + 1
        if days >= 2:
            parts.append(f"둘이 대화를 시작한 지 {days}일째다.")
        if days in MILESTONES:
            parts.append(
                f"오늘은 함께한 지 {days}일이 되는 날이다 — 관계에 맞게 자연스럽게 챙겨라.")
        gap_days = (now - stats["last_ts"]) / 86400
        if gap_days >= 3:
            parts.append(
                f"마지막 대화 이후 {int(gap_days)}일 만이다. 오랜만인 걸 관계에 맞게 반영해라 "
                "(반가움, 서운함, 궁금함 등).")
    return " ".join(parts)
