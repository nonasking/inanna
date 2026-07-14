import sqlite3
import time
from contextlib import contextmanager

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'local',
    companion_id TEXT NOT NULL,
    started_at REAL NOT NULL,
    summarized INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'local',
    companion_id TEXT NOT NULL,
    layer TEXT NOT NULL DEFAULT 'episodic',
    content TEXT NOT NULL,
    created_at REAL NOT NULL,
    source_session INTEGER
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    password_hash TEXT,              -- scrypt salt$hash (SIWA 계정은 NULL)
    apple_sub TEXT UNIQUE,           -- Sign in with Apple subject (P4 어댑터 자리)
    tier TEXT,                       -- 과금 티어 (NULL = 기본, billing.DEFAULT_TIER)
    invite TEXT,                     -- 가입에 쓴 초대 코드 (클로즈베타 추적)
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    created_at REAL NOT NULL,
    last_used REAL
);
CREATE TABLE IF NOT EXISTS invites (
    code TEXT PRIMARY KEY,
    note TEXT,                       -- 누구에게 준 코드인지 (운영 메모)
    created_at REAL NOT NULL,
    used_by TEXT,                    -- 사용한 계정 user_id ('u<id>') — NULL이면 미사용
    used_at REAL
);
CREATE TABLE IF NOT EXISTS refusals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    companion_id TEXT,
    ts REAL NOT NULL                 -- 프로바이더가 거절한 사실만 기록 (내용 저장 안 함)
);
CREATE TABLE IF NOT EXISTS growth (
    user_id TEXT NOT NULL,
    companion_id TEXT NOT NULL,
    stage TEXT NOT NULL,             -- 성장 문턱 통과 기록 (1회성 이벤트용)
    ts REAL NOT NULL,
    PRIMARY KEY (user_id, companion_id, stage)
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'local',
    companion_id TEXT,
    kind TEXT NOT NULL,                 -- llm | llm_summary | tts
    provider TEXT, model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    estimated INTEGER DEFAULT 0,        -- 1이면 문자수 기반 추정치
    tts_chars INTEGER DEFAULT 0,
    audio_bytes INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_companion ON sessions(user_id, companion_id);
CREATE INDEX IF NOT EXISTS idx_memories_user_companion ON memories(user_id, companion_id);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
CREATE INDEX IF NOT EXISTS idx_refusals_user ON refusals(user_id, ts);
"""


@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        # 마이그레이션 — CREATE IF NOT EXISTS는 기존 테이블에 칼럼을 못 더한다
        for col in ("tier TEXT", "invite TEXT", "suspended_at REAL"):
            try:
                c.execute(f"ALTER TABLE accounts ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # 이미 있음


def active_session(user_id: str, companion_id: str) -> int | None:
    """마지막 메시지가 SESSION_GAP 이내인 세션이 있으면 그 id."""
    with conn() as c:
        row = c.execute(
            """SELECT s.id, MAX(m.ts) AS last_ts FROM sessions s
               JOIN messages m ON m.session_id = s.id
               WHERE s.user_id = ? AND s.companion_id = ? GROUP BY s.id
               ORDER BY last_ts DESC LIMIT 1""",
            (user_id, companion_id),
        ).fetchone()
    if row and row["last_ts"] and time.time() - row["last_ts"] < config.SESSION_GAP_SECONDS:
        return row["id"]
    return None


def create_session(user_id: str, companion_id: str) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO sessions (user_id, companion_id, started_at) VALUES (?, ?, ?)",
            (user_id, companion_id, time.time()),
        )
        return cur.lastrowid


def add_message(session_id: int, role: str, content: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO messages (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )


def session_messages(session_id: int, limit: int = 200) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT role, content, ts FROM messages WHERE session_id = ? ORDER BY id LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def unsummarized_sessions(user_id: str, companion_id: str,
                          exclude: int | None = None) -> list[int]:
    """메시지가 있는 미요약 세션 id 목록 (오래된 순)."""
    with conn() as c:
        rows = c.execute(
            """SELECT DISTINCT s.id FROM sessions s
               JOIN messages m ON m.session_id = s.id
               WHERE s.user_id = ? AND s.companion_id = ? AND s.summarized = 0
               ORDER BY s.id""",
            (user_id, companion_id),
        ).fetchall()
    return [r["id"] for r in rows if r["id"] != exclude]


def mark_summarized(session_id: int) -> None:
    with conn() as c:
        c.execute("UPDATE sessions SET summarized = 1 WHERE id = ?", (session_id,))


def add_memory(user_id: str, companion_id: str, content: str,
               source_session: int | None = None, layer: str = "episodic") -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO memories (user_id, companion_id, layer, content, created_at, source_session)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, companion_id, layer, content, time.time(), source_session),
        )


def recent_memories(user_id: str, companion_id: str, limit: int) -> list[str]:
    return [r["content"] for r in recent_memories_rows(user_id, companion_id, limit)]


def recent_memories_rows(user_id: str, companion_id: str, limit: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, content FROM memories WHERE user_id = ? AND companion_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (user_id, companion_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def all_memories(user_id: str, companion_id: str, limit: int = 1000) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, content, layer, created_at FROM memories"
            " WHERE user_id = ? AND companion_id = ? ORDER BY id LIMIT ?",
            (user_id, companion_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def update_memory(user_id: str, memory_id: int, content: str) -> bool:
    """기억 정정 — 사용자가 소유한 기억만. (기억 열람·정정 UI)"""
    with conn() as c:
        cur = c.execute(
            "UPDATE memories SET content = ? WHERE id = ? AND user_id = ?",
            (content, memory_id, user_id))
        return cur.rowcount > 0


def delete_memory(user_id: str, memory_id: int) -> bool:
    with conn() as c:
        cur = c.execute("DELETE FROM memories WHERE id = ? AND user_id = ?",
                        (memory_id, user_id))
        return cur.rowcount > 0


def relationship_stats(user_id: str, companion_id: str) -> dict | None:
    """관계 진행 컨텍스트용 — 첫 대화 시각, 마지막 메시지 시각."""
    with conn() as c:
        row = c.execute(
            """SELECT MIN(s.started_at) AS first_ts, MAX(m.ts) AS last_ts
               FROM sessions s JOIN messages m ON m.session_id = s.id
               WHERE s.user_id = ? AND s.companion_id = ?""",
            (user_id, companion_id),
        ).fetchone()
    if not row or row["first_ts"] is None:
        return None
    return {"first_ts": row["first_ts"], "last_ts": row["last_ts"]}


def message_count(user_id: str, companion_id: str) -> int:
    """관계의 축적량 — 유대감(bond) 계산용."""
    with conn() as c:
        row = c.execute(
            """SELECT COUNT(*) AS n FROM messages m
               JOIN sessions s ON s.id = m.session_id
               WHERE s.user_id = ? AND s.companion_id = ?""",
            (user_id, companion_id)).fetchone()
    return row["n"]


def recent_history(user_id: str, companion_id: str, limit: int = 50) -> list[dict]:
    """UI 복원용 — 컴패니언의 최근 메시지 (세션 무관)."""
    with conn() as c:
        rows = c.execute(
            """SELECT m.role, m.content, m.ts FROM messages m
               JOIN sessions s ON s.id = m.session_id
               WHERE s.user_id = ? AND s.companion_id = ? ORDER BY m.id DESC LIMIT ?""",
            (user_id, companion_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def create_invite(code: str, note: str = "") -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO invites (code, note, created_at) VALUES (?, ?, ?)",
                  (code, note or None, time.time()))


def claim_invite(code: str, user_id: str) -> bool:
    """1회용 초대 코드 소진 — 미사용 코드일 때만 True (원자적)."""
    with conn() as c:
        cur = c.execute(
            "UPDATE invites SET used_by = ?, used_at = ? WHERE code = ? AND used_by IS NULL",
            (user_id, time.time(), code))
        return cur.rowcount > 0


def release_invite(user_id: str) -> None:
    """계정 삭제 시 코드를 되돌린다 (재초대 가능하게)."""
    with conn() as c:
        c.execute("UPDATE invites SET used_by = NULL, used_at = NULL WHERE used_by = ?",
                  (user_id,))


def list_invites() -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT code, note, used_by, used_at, created_at FROM invites ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


def growth_stages_passed(user_id: str, companion_id: str) -> set[str]:
    with conn() as c:
        rows = c.execute("SELECT stage FROM growth WHERE user_id = ? AND companion_id = ?",
                         (user_id, companion_id)).fetchall()
    return {r["stage"] for r in rows}


def mark_growth_stage(user_id: str, companion_id: str, stage: str) -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO growth (user_id, companion_id, stage, ts)"
                  " VALUES (?, ?, ?, ?)", (user_id, companion_id, stage, time.time()))


_USAGE_FIELDS = ("provider", "model", "input_tokens", "output_tokens",
                 "cache_read_tokens", "cache_write_tokens", "estimated",
                 "tts_chars", "audio_bytes")


def add_usage(user_id: str, companion_id: str | None, kind: str, **fields) -> None:
    """사용량 기록 — P4 과금 단위 경제 계산의 실데이터 (턴수·토큰·캐시·음성량)."""
    cols = ["ts", "user_id", "companion_id", "kind"]
    vals: list = [time.time(), user_id, companion_id, kind]
    for k in _USAGE_FIELDS:
        if k in fields and fields[k] is not None:
            cols.append(k)
            vals.append(fields[k])
    with conn() as c:
        c.execute(f"INSERT INTO usage ({', '.join(cols)}) VALUES "
                  f"({', '.join('?' * len(cols))})", vals)


def usage_summary(user_id: str, days: int = 30) -> list[dict]:
    """kind·provider·model별 합계 (기간 내). /api/usage 및 단위 경제 계산용."""
    since = time.time() - days * 86400
    with conn() as c:
        rows = c.execute(
            """SELECT kind, provider, model, COUNT(*) AS calls,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens,
                      SUM(cache_read_tokens) AS cache_read_tokens,
                      SUM(cache_write_tokens) AS cache_write_tokens,
                      SUM(tts_chars) AS tts_chars,
                      SUM(audio_bytes) AS audio_bytes,
                      MAX(estimated) AS has_estimates
               FROM usage WHERE user_id = ? AND ts >= ?
               GROUP BY kind, provider, model ORDER BY kind, provider, model""",
            (user_id, since),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_companion_data(user_id: str, companion_id: str) -> None:
    with conn() as c:
        c.execute(
            "DELETE FROM messages WHERE session_id IN"
            " (SELECT id FROM sessions WHERE user_id = ? AND companion_id = ?)",
            (user_id, companion_id))
        c.execute("DELETE FROM sessions WHERE user_id = ? AND companion_id = ?",
                  (user_id, companion_id))
        c.execute("DELETE FROM memories WHERE user_id = ? AND companion_id = ?",
                  (user_id, companion_id))
