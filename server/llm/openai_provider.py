"""OpenAI 호환 프로바이더 — 업계 공용 규격 하나로 광범위하게 커버.

OpenAI, OpenRouter, Groq, DeepSeek 같은 클라우드와 LM Studio, llama.cpp
server, vLLM, Ollama(/v1) 같은 로컬 서버가 모두 이 규격을 말한다.
"""
import json
from collections.abc import Iterator

import httpx

from .base import join_system


class OpenAICompatProvider:
    name = "openai"

    def __init__(self, model: str, base_url: str, api_key: str = ""):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.last_usage: dict | None = None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _payload(self, system: str | list[str], messages: list[dict],
                 max_tokens: int, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": join_system(system)}, *messages],
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def stream_chat(self, system: str | list[str], messages: list[dict],
                    max_tokens: int = 2048) -> Iterator[str]:
        out_chars = 0
        # 스트리밍 usage는 서버 구현마다 달라서(stream_options 미지원 다수)
        # 문자수 기반 추정치로 기록한다 (한국어 ≈ 1토큰/1.5자)
        in_chars = len(join_system(system)) + sum(len(m.get("content", "")) for m in messages)
        with httpx.stream(
            "POST", f"{self.base_url}/chat/completions",
            json=self._payload(system, messages, max_tokens, stream=True),
            headers=self._headers(),
            timeout=httpx.Timeout(180, connect=10),
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    out_chars += len(delta)
                    yield delta
        self.last_usage = {"input_tokens": int(in_chars / 1.5),
                           "output_tokens": int(out_chars / 1.5), "estimated": 1}

    def complete(self, system: str | list[str], messages: list[dict],
                 max_tokens: int = 1024) -> str:
        r = httpx.post(
            f"{self.base_url}/chat/completions",
            json=self._payload(system, messages, max_tokens, stream=False),
            headers=self._headers(),
            timeout=httpx.Timeout(180, connect=10),
        )
        r.raise_for_status()
        choices = r.json().get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content") or ""
