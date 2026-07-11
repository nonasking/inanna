"""계정 인증 — P4 제품 모드의 멀티유저 레이어.

셀프호스팅 단일 토큰(INANNA_AUTH_TOKEN → 'local' 유저)과 공존한다:
그 토큰이면 기존처럼 'local', 아니면 계정 세션 토큰을 조회해 해당
계정의 user_id('u<id>')로 스코핑한다. 모든 저장소가 이미 user_id
스코핑이라 이 레이어만으로 멀티유저가 성립한다.

Sign in with Apple(P4 등록 후)은 어댑터 자리만: accounts.apple_sub에
검증된 subject를 넣는 login_apple()을 붙이면 나머지는 동일하다.
비밀번호는 stdlib scrypt (외부 의존 없음).
"""
import hashlib
import re
import secrets
import time

from .memory import db

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"{salt.hex()}${h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, want = stored.split("$")
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return secrets.compare_digest(h.hex(), want)
    except Exception:
        return False


def _issue_token(account_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db.conn() as c:
        c.execute("INSERT INTO auth_tokens (token, account_id, created_at) VALUES (?, ?, ?)",
                  (token, account_id, time.time()))
    return token


def register(email: str, password: str) -> str:
    """계정 생성 → 세션 토큰. ValueError는 사용자에게 그대로 보여줄 메시지."""
    email = email.strip().lower()
    if not _EMAIL.match(email):
        raise ValueError("이메일 형식이 올바르지 않습니다")
    if len(password) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다")
    with db.conn() as c:
        if c.execute("SELECT 1 FROM accounts WHERE email = ?", (email,)).fetchone():
            raise ValueError("이미 가입된 이메일입니다")
        cur = c.execute(
            "INSERT INTO accounts (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, _hash_password(password), time.time()))
        account_id = cur.lastrowid
    return _issue_token(account_id)


def login(email: str, password: str) -> str | None:
    """성공 시 세션 토큰, 실패 시 None (원인 비구분 — 계정 존재 노출 방지)."""
    with db.conn() as c:
        row = c.execute("SELECT id, password_hash FROM accounts WHERE email = ?",
                        (email.strip().lower(),)).fetchone()
    if not row or not row["password_hash"] or not _verify_password(password, row["password_hash"]):
        return None
    return _issue_token(row["id"])


def logout(token: str) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))


def resolve_token(token: str) -> str | None:
    """세션 토큰 → user_id ('u<account_id>'). 없으면 None."""
    if not token:
        return None
    with db.conn() as c:
        row = c.execute("SELECT account_id FROM auth_tokens WHERE token = ?",
                        (token,)).fetchone()
        if not row:
            return None
        c.execute("UPDATE auth_tokens SET last_used = ? WHERE token = ?",
                  (time.time(), token))
    return f"u{row['account_id']}"


def account_info(user_id: str) -> dict | None:
    if not user_id.startswith("u"):
        return None
    with db.conn() as c:
        row = c.execute("SELECT id, email, created_at FROM accounts WHERE id = ?",
                        (int(user_id[1:]),)).fetchone()
    return dict(row) if row else None


def delete_account(user_id: str) -> None:
    """계정 + 모든 데이터 완전 삭제 — App Store 5.1.1(v) 요건이자 데이터 소유 원칙.

    호출측(main)이 컴패니언 파일·참조 오디오 삭제를 함께 수행한다.
    """
    account_id = int(user_id[1:])
    with db.conn() as c:
        c.execute("DELETE FROM auth_tokens WHERE account_id = ?", (account_id,))
        c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        c.execute("DELETE FROM messages WHERE session_id IN"
                  " (SELECT id FROM sessions WHERE user_id = ?)", (user_id,))
        c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM usage WHERE user_id = ?", (user_id,))
