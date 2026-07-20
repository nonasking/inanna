"""과금 골격 — 티어(모델 선택형) + 월간 쿼터. (requirements P4 설계 확정본)

원칙:
- 티어는 추상화된 이름으로 팔고(라이트/스탠다드/딥), 실체는 모델 등급 + 기본량.
- 기억·관계 데이터는 티어와 무관하게 동일 — 요금이 바뀌어도 나를 똑같이 기억한다.
- 무제한 없음: 월간 쿼터 소진 시 명확히 안내 (초과 크레딧은 IAP 연동 시).
- 셀프호스팅 오너('local')는 이 레이어를 통과하지 않는다 (자기 키 = 자기 비용).

숫자(쿼터·모델 매핑)는 단위 경제 계산 후 확정 — 지금은 자리표시 기본값이며
usage 테이블(2026-07-11부터 수집)이 그 계산의 입력이다.
"""
import os
import time
from datetime import datetime, timezone

from .memory import db

# 티어 정의 — model은 컴패니언 오버라이드를 무시하고 티어가 결정한다 (제품 모드).
# quota는 월간 LLM 출력 토큰 / TTS 문자 수.
# tts_engines: 허용 TTS — 비용의 실체는 토큰보다 유료 TTS 문자라 티어로 게이트.
# daily_*: 월간 쿼터를 하루에 태우는 폭주 방지 (일간 상한).
TIERS = {
    "beta": {
        "name": "베타",
        "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
        "monthly_output_tokens": 150_000, "daily_output_tokens": 20_000,
        "monthly_tts_chars": 9_000, "daily_tts_chars": 1_500,
        "tts_engines": {"edge"},
    },
    "lite": {
        "name": "라이트",
        "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
        "monthly_output_tokens": 300_000, "daily_output_tokens": 30_000,
        "monthly_tts_chars": 30_000, "daily_tts_chars": 3_000,
        "tts_engines": {"edge"},
    },
    "standard": {
        "name": "스탠다드",
        "provider": "anthropic", "model": "claude-sonnet-5",
        "monthly_output_tokens": 600_000, "daily_output_tokens": 60_000,
        "monthly_tts_chars": 100_000, "daily_tts_chars": 8_000,
        "tts_engines": {"edge", "sovits", "elevenlabs"},
    },
    "deep": {
        "name": "딥",
        "provider": "anthropic", "model": "claude-opus-4-8",
        "monthly_output_tokens": 1_000_000, "daily_output_tokens": 100_000,
        "monthly_tts_chars": 250_000, "daily_tts_chars": 15_000,
        "tts_engines": {"edge", "sovits", "elevenlabs"},
    },
}
DEFAULT_TIER = os.environ.get("INANNA_DEFAULT_TIER", "lite")


# 소진 안내는 '사실 + 리셋 시점'만 — 막힌 순간의 업셀은 반감이 가장 큰 지점이라
# 티어 안내는 이용 현황 화면에만 둔다 (2026-07 사용량 UX 리서치).
_QUOTA_MESSAGES = {
    "tokens": "이번 달 대화량을 다 썼어요. 다음 달 1일에 다시 채워져요.",
    "daily_tokens": "오늘 사용량을 다 썼어요. 내일 다시 만나요!",
    "tts": "이번 달 음성 사용량을 다 썼어요. 텍스트 대화는 계속할 수 있어요.",
    "daily_tts": "오늘 음성 사용량을 다 썼어요. 텍스트 대화는 계속할 수 있어요.",
    "engine": "이 요금제에서는 기본 보이스만 쓸 수 있어요. (컴패니언 편집에서 프리셋 보이스를 선택해주세요)",
}


class QuotaExceeded(Exception):
    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(_QUOTA_MESSAGES.get(kind, _QUOTA_MESSAGES["tokens"]))


def is_metered(user_id: str) -> bool:
    """계정 유저만 과금 대상 — 셀프호스팅 오너는 무제한."""
    return user_id.startswith("u")


def get_tier(user_id: str) -> str:
    with db.conn() as c:
        row = c.execute("SELECT tier FROM accounts WHERE id = ?",
                        (int(user_id[1:]),)).fetchone()
    return (row["tier"] if row and row["tier"] else DEFAULT_TIER)


def set_tier(user_id: str, tier: str) -> None:
    if tier not in TIERS:
        raise ValueError(f"알 수 없는 티어: {tier}")
    with db.conn() as c:
        c.execute("UPDATE accounts SET tier = ? WHERE id = ?",
                  (tier, int(user_id[1:])))


def _month_start() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()


def _day_start() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()


def _next_month_start() -> float:
    now = datetime.now(timezone.utc)
    y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return datetime(y, m, 1, tzinfo=timezone.utc).timestamp()


def _usage_since(user_id: str, since: float) -> dict:
    with db.conn() as c:
        row = c.execute(
            """SELECT COALESCE(SUM(output_tokens), 0) AS out_tokens,
                      COALESCE(SUM(tts_chars), 0) AS tts_chars
               FROM usage WHERE user_id = ? AND ts >= ?""",
            (user_id, since)).fetchone()
    return {"output_tokens": row["out_tokens"], "tts_chars": row["tts_chars"]}


def month_usage(user_id: str) -> dict:
    return _usage_since(user_id, _month_start())


def day_usage(user_id: str) -> dict:
    return _usage_since(user_id, _day_start())


def status(user_id: str) -> dict:
    """/api/billing 응답 — 앱 설정 화면과 쿼터 게이지용."""
    if not is_metered(user_id):
        return {"metered": False}
    tier = get_tier(user_id)
    spec = TIERS[tier]
    used = month_usage(user_id)
    return {
        "metered": True, "tier": tier, "tier_name": spec["name"],
        "used": used,
        "used_today": day_usage(user_id),
        "limits": {"output_tokens": spec["monthly_output_tokens"],
                   "tts_chars": spec["monthly_tts_chars"],
                   "daily_output_tokens": spec["daily_output_tokens"],
                   "daily_tts_chars": spec["daily_tts_chars"]},
        "tts_engines": sorted(spec["tts_engines"]),
        "daily_resets_at": _day_start() + 86400,
        "resets_at": _next_month_start(),
    }


NOTICE_FRACTION = 0.8   # 임계 통과 시 한 번만 조용히 알린다 (통신사 80% 룰)


def quota_notice(user_id: str, added_tokens: int) -> str | None:
    """방금 턴이 80% 임계를 '넘겼을' 때만 안내 문구 — 그 외엔 None.

    add_usage 이후에 호출한다. 통과 순간에만 반환하므로 하루/한 달에 한 번만
    뜬다 — 상시 카운터는 매 발화를 과금 미터로 만들어 몰입을 깬다.
    """
    if not is_metered(user_id) or added_tokens <= 0:
        return None
    spec = TIERS[get_tier(user_id)]
    day = day_usage(user_id)["output_tokens"]
    month = month_usage(user_id)["output_tokens"]
    if day - added_tokens < spec["daily_output_tokens"] * NOTICE_FRACTION <= day:
        return "오늘 나눌 수 있는 대화가 얼마 남지 않았어요."
    if month - added_tokens < spec["monthly_output_tokens"] * NOTICE_FRACTION <= month:
        return "이번 달 대화가 얼마 남지 않았어요."
    return None


def chat_tokens_left(user_id: str) -> int | None:
    """오늘/이번 달 중 먼저 소진되는 쪽의 남은 출력 토큰. 무과금 유저는 None."""
    if not is_metered(user_id):
        return None
    spec = TIERS[get_tier(user_id)]
    return min(spec["daily_output_tokens"] - day_usage(user_id)["output_tokens"],
               spec["monthly_output_tokens"] - month_usage(user_id)["output_tokens"])


def effective_model(user_id: str) -> tuple[str, str] | None:
    """계정 유저의 (provider, model) — 티어가 결정. 셀프호스팅은 None(기존 로직)."""
    if not is_metered(user_id):
        return None
    spec = TIERS[get_tier(user_id)]
    return spec["provider"], spec["model"]


def check_chat_quota(user_id: str) -> None:
    if not is_metered(user_id):
        return
    spec = TIERS[get_tier(user_id)]
    if month_usage(user_id)["output_tokens"] >= spec["monthly_output_tokens"]:
        raise QuotaExceeded("tokens")
    if day_usage(user_id)["output_tokens"] >= spec["daily_output_tokens"]:
        raise QuotaExceeded("daily_tokens")


def check_tts_quota(user_id: str, engine: str | None = None) -> None:
    if not is_metered(user_id):
        return
    spec = TIERS[get_tier(user_id)]
    if engine and engine not in spec["tts_engines"]:
        raise QuotaExceeded("engine")
    if month_usage(user_id)["tts_chars"] >= spec["monthly_tts_chars"]:
        raise QuotaExceeded("tts")
    if day_usage(user_id)["tts_chars"] >= spec["daily_tts_chars"]:
        raise QuotaExceeded("daily_tts")
