from collections.abc import Iterator

import anthropic


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str):
        # ANTHROPIC_API_KEY 또는 `ant auth login` 프로필을 자동으로 사용
        self.client = anthropic.Anthropic()
        self.model = model

    def _system_blocks(self, system: str | list[str]) -> list[dict]:
        # [안정, 휘발] 블록 — 안정 블록(페르소나)만 캐시 브레이크포인트.
        # 휘발 블록(시각·recall)을 뒤에 둬야 매 턴 캐시가 살아남는다.
        if isinstance(system, str):
            system = [system]
        blocks = [{"type": "text", "text": system[0],
                   "cache_control": {"type": "ephemeral"}}]
        blocks += [{"type": "text", "text": t} for t in system[1:]]
        return blocks

    def _with_history_breakpoint(self, messages: list[dict]) -> list[dict]:
        # 마지막 '어시스턴트' 메시지에 캐시 브레이크포인트 — 시스템+원문 이력이
        # 증분 캐시되는 프리픽스가 된다 (시스템 블록만으론 최소 1024토큰 미달).
        # 마지막 사용자 메시지는 휘발 컨텍스트(기억 recall·시각)로 감싸져 턴마다
        # 달라지므로 브레이크포인트 뒤에 둬야 이력 캐시가 살아남는다.
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                marked = {"role": "assistant", "content": [
                    {"type": "text", "text": m["content"],
                     "cache_control": {"type": "ephemeral"}}]}
                return messages[:i] + [marked] + messages[i + 1:]
        return messages

    @staticmethod
    def _usage(u) -> dict:
        return {
            "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
            "cache_read_tokens": u.cache_read_input_tokens or 0,
            "cache_write_tokens": u.cache_creation_input_tokens or 0,
        }

    def stream_chat(self, system: str | list[str], messages: list[dict],
                    max_tokens: int = 2048, stats: dict | None = None) -> Iterator[str]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=self._system_blocks(system),
            messages=self._with_history_breakpoint(messages),
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
            if stats is not None:
                # 프로바이더가 안전 정책으로 거절했는지 — 내용 판정은 하지 않고 사실만 본다
                stats["refusal"] = final.stop_reason == "refusal"
                stats["usage"] = self._usage(final.usage)

    def complete(self, system: str | list[str], messages: list[dict],
                 max_tokens: int = 1024, stats: dict | None = None) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self._system_blocks(system),
            messages=messages,
        )
        if stats is not None:
            stats["refusal"] = response.stop_reason == "refusal"
            stats["usage"] = self._usage(response.usage)
        return next((b.text for b in response.content if b.type == "text"), "")
