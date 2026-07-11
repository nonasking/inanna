from collections.abc import Iterator
from typing import Protocol


class LLMProvider(Protocol):
    name: str
    model: str

    def stream_chat(self, system: str | list[str], messages: list[dict],
                    max_tokens: int = 2048) -> Iterator[str]:
        """system + messages([{role, content}])로 응답 텍스트를 델타 단위로 스트리밍.

        system이 리스트면 [안정, 휘발] 블록 — 캐시를 지원하는 프로바이더는
        안정 블록만 캐시하고, 나머지는 이어 붙인다.
        """
        ...

    def complete(self, system: str | list[str], messages: list[dict],
                 max_tokens: int = 1024) -> str:
        """비스트리밍 단발 호출 (요약 등 내부 용도)."""
        ...


def join_system(system: str | list[str]) -> str:
    """캐시 개념이 없는 프로바이더용 — 블록을 단일 문자열로."""
    return "\n\n".join(system) if isinstance(system, list) else system
