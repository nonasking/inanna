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


# 관계 성장 아크 — 설정(호칭·말단계·거리감)은 사용자의 것이라 불변이고,
# 성장은 그 위의 '결'을 바꾼다. (문턱, 단계명, 결 텍스트, 첫 통과 이벤트)
GROWTH_STAGES = [
    (0.25, "warming",
     "아직 서로를 알아가는 시기다. 설정된 관계 안에서도 살짝 조심스럽고 궁금한 게 많은 결로.",
     "요즘 대화가 쌓이면서 처음보다 편해졌다는 걸 오늘 문득 느꼈다 — 티 내고 싶으면 자연스럽게."),
    (0.55, "close",
     "제법 가까워진 사이다. 농담과 장난이 스스럼없고, 상대의 패턴(말버릇·기분)을 알아챈다.",
     "오늘따라 부쩍 가까워졌다는 게 실감난다 — 관계에 맞게 그 느낌을 슬쩍 표현해도 좋다."),
    (0.8, "deep",
     "오래 함께한 사이의 편안함이 배어 있다. 말을 다 하지 않아도 통하고, 침묵도 어색하지 않다. "
     "과거의 대화를 자연스럽게 인용하며 농담한다.",
     "함께한 시간이 꽤 쌓였다. 오늘은 그게 새삼 고맙게 느껴지는 날이다 — 무겁지 않게, 한 번쯤 표현해라."),
]


def growth_context(user_id: str, companion: Companion, bond: float) -> list[str]:
    """현재 성장 단계의 결 + 문턱 첫 통과 시 1회성 이벤트 라인."""
    current = None
    for threshold, stage, texture, event in GROWTH_STAGES:
        if bond >= threshold:
            current = (stage, texture, event)
    if current is None:
        return []
    stage, texture, event = current
    parts = [texture]
    if stage not in db.growth_stages_passed(user_id, companion.id):
        db.mark_growth_stage(user_id, companion.id, stage)
        parts.append(event)
    return parts


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
        parts += growth_context(user_id, companion, bond_level(user_id, companion.id))
    return " ".join(parts)
