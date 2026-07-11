"""과금 골격 — 티어(모델 선택형) + 월간 쿼터. (requirements P4 설계 확정본)

원칙:
- 티어는 추상화된 이름으로 팔고(라이트/스탠다드/딥), 실체는 모델 등급 + 기본량.
- 기억·관계 데이터는 티어와 무관하게 동일 — 요금이 바뀌어도 나를 똑같이 기억한다.
- 무제한 없음: 월간 쿼터 소진 시 명확히 안내 (초과 크레딧은 IAP 연동 시).
- 셀프호스팅 오너('local')는 이 레이어를 통과하지 않는다 (자기 키 = 자기 비용).

숫자(쿼터·모델 매핑)는 단위 경제 계산 후 확정 — 지금은 자리표시 기본값이며
usage 테이블(2026-07-11부터 수집)이 그 계산의 입력이다.
"""
import time
from datetime import datetime, timezone

from .memory import db

# 티어 정의 — model은 컴패니언 오버라이드를 무시하고 티어가 결정한다 (제품 모드).
# quota는 월간 LLM 출력 토큰 / TTS 문자 수.
TIERS = {
    "lite": {
        "name": "라이트",
        "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
        "monthly_output_tokens": 300_000, "monthly_tts_chars": 30_000,
    },
    "standard": {
        "name": "스탠다드",
        "provider": "anthropic", "model": "claude-sonnet-5",
        "monthly_output_tokens": 600_000, "monthly_tts_chars": 100_000,
    },
    "deep": {
        "name": "딥",
        "provider": "anthropic", "model": "claude-opus-4-8",
        "monthly_output_tokens": 1_000_000, "monthly_tts_chars": 250_000,
    },
}
DEFAULT_TIER = "lite"


class QuotaExceeded(Exception):
    def __init__(self, kind: str):
        self.kind = kind  # tokens | tts
        super().__init__(
            "이번 달 사용량을 다 썼어요. 다음 달에 초기화되거나, 상위 티어로 올릴 수 있어요."
            if kind == "tokens" else
            "이번 달 음성 사용량을 다 썼어요. 텍스트 대화는 계속할 수 있어요.")


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


def month_usage(user_id: str) -> dict:
    since = _month_start()
    with db.conn() as c:
        row = c.execute(
            """SELECT COALESCE(SUM(output_tokens), 0) AS out_tokens,
                      COALESCE(SUM(tts_chars), 0) AS tts_chars
               FROM usage WHERE user_id = ? AND ts >= ?""",
            (user_id, since)).fetchone()
    return {"output_tokens": row["out_tokens"], "tts_chars": row["tts_chars"]}


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
        "limits": {"output_tokens": spec["monthly_output_tokens"],
                   "tts_chars": spec["monthly_tts_chars"]},
        "resets_at": _month_start() + 32 * 86400,  # 대략 다음 달 초 (표시용)
    }


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


def check_tts_quota(user_id: str) -> None:
    if not is_metered(user_id):
        return
    spec = TIERS[get_tier(user_id)]
    if month_usage(user_id)["tts_chars"] >= spec["monthly_tts_chars"]:
        raise QuotaExceeded("tts")
