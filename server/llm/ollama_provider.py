import json
from collections.abc import Iterator

import httpx

from .base import join_system


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.last_usage: dict | None = None

    def _payload(self, system: str | list[str], messages: list[dict], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": join_system(system)}, *messages],
            "stream": stream,
        }

    def stream_chat(self, system: str | list[str], messages: list[dict],
                    max_tokens: int = 2048) -> Iterator[str]:
        with httpx.stream(
            "POST", f"{self.base_url}/api/chat",
            json=self._payload(system, messages, stream=True),
            timeout=httpx.Timeout(120, connect=5),
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if chunk.get("done"):
                    # 마지막 청크에 정확한 토큰 카운트가 실려 온다
                    self.last_usage = {
                        "input_tokens": chunk.get("prompt_eval_count", 0),
                        "output_tokens": chunk.get("eval_count", 0),
                    }
                    break

    def complete(self, system: str | list[str], messages: list[dict],
                 max_tokens: int = 1024) -> str:
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json=self._payload(system, messages, stream=False),
            timeout=httpx.Timeout(120, connect=5),
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")
