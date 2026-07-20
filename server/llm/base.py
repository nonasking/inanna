from collections.abc import Iterator
from typing import Protocol


class LLMProvider(Protocol):
    name: str
    model: str

    def stream_chat(self, system: str | list[str], messages: list[dict],
                    max_tokens: int = 2048, stats: dict | None = None) -> Iterator[str]:
        """system + messages([{role, content}])로 응답 텍스트를 델타 단위로 스트리밍.

        system이 리스트면 [안정, 휘발] 블록 — 캐시를 지원하는 프로바이더는
        안정 블록만 캐시하고, 나머지는 이어 붙인다.

        stats: 요청별 결과 dict. 넘기면 프로바이더가 호출 종료 시
        {"usage": {...}, "refusal": bool, "prompt_eval": float}를 채운다. 프로바이더
        인스턴스는 lru_cache로 여러 요청이 공유하므로, 호출 결과를 인스턴스 속성이
        아니라 이 요청-로컬 dict에 담아 동시 요청 간 오염을 막는다.
        """
        ...

    def complete(self, system: str | list[str], messages: list[dict],
                 max_tokens: int = 1024, stats: dict | None = None) -> str:
        """비스트리밍 단발 호출 (요약 등 내부 용도). stats는 stream_chat과 동일."""
        ...


def join_system(system: str | list[str]) -> str:
    """캐시 개념이 없는 프로바이더용 — 블록을 단일 문자열로."""
    return "\n\n".join(system) if isinstance(system, list) else system
