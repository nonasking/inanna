"""관련 기억 검색 — BM25 (한글 문자 바이그램 + 영숫자 토큰).

임베딩 모델 없이 동작하는 렉시컬 검색. 기억이 수백 개 규모까지는 충분하고,
임베딩 백엔드(sqlite-vec 등)가 가능해지면 get_relevant만 교체하면 된다.
(현재 Python 3.14 venv에서 torch/onnxruntime 휠 부재로 임베딩 보류)
"""
import math
import re
from collections import Counter

from . import db

_HANGUL = re.compile(r"[가-힣]")
_ALNUM = re.compile(r"[a-zA-Z0-9]+")

K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
    chars = _HANGUL.findall(text)
    bigrams = [a + b for a, b in zip(chars, chars[1:])]
    words = [w.lower() for w in _ALNUM.findall(text)]
    return bigrams + words


def _bm25_scores(query_tokens: list[str], docs: list[list[str]]) -> list[float]:
    n = len(docs)
    if n == 0:
        return []
    avg_len = sum(len(d) for d in docs) / n or 1.0
    # 문서 빈도
    df: Counter = Counter()
    for d in docs:
        for t in set(d):
            df[t] += 1
    scores = [0.0] * n
    q_counts = Counter(query_tokens)
    for term in q_counts:
        if term not in df:
            continue
        idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
        for i, d in enumerate(docs):
            tf = d.count(term)
            if tf == 0:
                continue
            scores[i] += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * len(d) / avg_len))
    return scores


def get_relevant(user_id: str, companion_id: str, query: str,
                 k: int = 5, exclude_ids: set[int] | None = None) -> list[dict]:
    """현재 발화와 관련 높은 기억 top-k. [{id, content}] (score>0만)."""
    exclude_ids = exclude_ids or set()
    rows = [r for r in db.all_memories(user_id, companion_id)
            if r["id"] not in exclude_ids]
    if not rows:
        return []
    q = tokenize(query)
    docs = [tokenize(r["content"]) for r in rows]
    scores = _bm25_scores(q, docs)
    ranked = sorted(zip(scores, rows), key=lambda x: -x[0])
    return [r for s, r in ranked[:k] if s > 0.5]
