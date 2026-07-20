"""안전 레이어 — 정책을 '복제'하지 않고 '위임'한다.

원칙 (2026-07-12 확정):
- 무엇이 금지인지는 **모델·프로바이더가 판정한다**. 우리는 금지 목록을 코드나
  프롬프트에 넣지 않는다 — 프로바이더마다 다르고 계속 바뀌므로 따라잡을 수 없다.
- 우리가 하는 일은 두 가지뿐:
  ① 거절의 '연출' (compiler의 대화 원칙 — 캐릭터를 유지한 채 거절)
  ② 거절이 '일어났다는 사실'만 계정 단위로 카운트 → 반복되면 자동 정지
- 즉 정책의 **내용**은 몰라도 되고, **이벤트**만 세면 된다. 정책이 바뀌면
  거절 패턴도 따라 바뀌므로 이 코드는 유지보수가 필요 없다.

호스팅 주체 기준으로 적용된다: 셀프호스팅 오너('local')는 자기 서버·자기 키·
자기 책임이므로 통과. 계정 유저(우리 서버에서 우리 키로 도는 사람)만 대상.
"""
import time

from .memory import db

# 롤링 창(24시간) 안에서 이만큼 거절이 쌓이면 계정 정지
REFUSAL_LIMIT = 5
REFUSAL_WINDOW = 24 * 3600
SUSPEND_MESSAGE = (
    "이용정책에 반하는 요청이 반복되어 계정이 정지되었습니다. "
    "문의는 서비스 운영자에게 해주세요."
)


class Suspended(Exception):
    def __init__(self):
        super().__init__(SUSPEND_MESSAGE)


def is_managed(user_id: str) -> bool:
    """우리 서버·우리 키로 도는 계정만 안전 레이어 대상 (셀프호스팅 오너 제외)."""
    return user_id.startswith("u")


def record_refusal(user_id: str, companion_id: str | None) -> None:
    """프로바이더가 거절했다 — 사실만 기록하고, 임계를 넘으면 계정을 정지한다."""
    if not is_managed(user_id):
        return
    with db.conn() as c:
        c.execute("INSERT INTO refusals (user_id, companion_id, ts) VALUES (?, ?, ?)",
                  (user_id, companion_id, time.time()))
        # 창을 벗어난 오래된 행은 카운트에 안 쓰이므로 정리 (무한 증가 방지)
        c.execute("DELETE FROM refusals WHERE user_id = ? AND ts < ?",
                  (user_id, time.time() - REFUSAL_WINDOW))
        n = c.execute(
            "SELECT COUNT(*) AS n FROM refusals WHERE user_id = ? AND ts >= ?",
            (user_id, time.time() - REFUSAL_WINDOW)).fetchone()["n"]
        if n >= REFUSAL_LIMIT:
            c.execute("UPDATE accounts SET suspended_at = ? WHERE id = ?",
                      (time.time(), int(user_id[1:])))
    print(f"[safety] {user_id} 거절 {n}/{REFUSAL_LIMIT}"
          + (" → 계정 정지" if n >= REFUSAL_LIMIT else ""), flush=True)


def check_suspended(user_id: str) -> None:
    """정지된 계정이면 차단. 대화·통화·온보딩 등 모든 LLM 경로 앞에서 호출."""
    if not is_managed(user_id):
        return
    with db.conn() as c:
        row = c.execute("SELECT suspended_at FROM accounts WHERE id = ?",
                        (int(user_id[1:]),)).fetchone()
    if row and row["suspended_at"]:
        raise Suspended()


def unsuspend(user_id: str) -> None:
    """운영자가 소명 후 해제 (오탐 대비 — 자동 정지는 되돌릴 수 있어야 한다)."""
    with db.conn() as c:
        c.execute("UPDATE accounts SET suspended_at = NULL WHERE id = ?",
                  (int(user_id[1:]),))
        c.execute("DELETE FROM refusals WHERE user_id = ?", (user_id,))
