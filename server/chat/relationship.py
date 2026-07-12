"""관계 진행 컨텍스트 — 시간의 흐름을 컴패니언이 인지하게 한다.

함께한 일수, 기념일, 오랜만 감지, 현재 시각을 '지금 상황' 블록으로 만든다.
사용자가 설정한 거리감(intimacy)은 건드리지 않는다 — 설정은 사용자의 것,
시간의 흐름은 상황의 것.
"""
import datetime
import math
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


def bond_level(user_id: str, companion_id: str) -> float:
    """유대감 0~1 — 함께한 시간과 대화량의 포화 곡선.

    통화 오브의 시각 변화(색·광량)에 쓰인다: 관계가 깊어질수록 빛이
    따뜻하고 풍성해진다. 설정(intimacy)이 아니라 축적의 함수 — 나비의
    '변태' 서사를 오브의 시간 변화로 이식한 것.
    ~2주+수백 마디에 0.5, ~석 달 꾸준히 대화하면 0.9쯤에 수렴한다.
    """
    stats = db.relationship_stats(user_id, companion_id)
    if not stats:
        return 0.0
    days = max((time.time() - stats["first_ts"]) / 86400, 0)
    msgs = db.message_count(user_id, companion_id)
    return round(1 - math.exp(-(days / 45 + msgs / 900)), 3)


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
