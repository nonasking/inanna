import json
from collections.abc import Iterator

import httpx

from .. import config
from .base import join_system


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _payload(self, system: str | list[str], messages: list[dict], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": join_system(system)}, *messages],
            "stream": stream,
            # 모델을 상주시켜 콜드 로드와 프리픽스 캐시 소멸을 막는다 (config 주석 참고)
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {"num_ctx": config.OLLAMA_NUM_CTX},
        }

    def prefill(self, system: str | list[str], messages: list[dict]) -> None:
        """프롬프트만 처리해 KV 캐시를 채운다 (생성은 하지 않는다)."""
        body = self._payload(system, messages, stream=False)
        body["options"] = {**body["options"], "num_predict": 1}
        try:
            httpx.post(f"{self.base_url}/api/chat", json=body,
                       timeout=httpx.Timeout(180, connect=5))
        except Exception:
            pass

    def warmup(self) -> None:
        """모델을 미리 올려둔다 — 첫 대화가 콜드 로드를 맞지 않게. 실패는 무시."""
        try:
            httpx.post(f"{self.base_url}/api/chat",
                       json={"model": self.model, "messages": [{"role": "user", "content": "."}],
                             "stream": False, "keep_alive": config.OLLAMA_KEEP_ALIVE,
                             "options": {"num_ctx": config.OLLAMA_NUM_CTX, "num_predict": 1}},
                       timeout=httpx.Timeout(120, connect=5))
        except Exception:
            pass

    def stream_chat(self, system: str | list[str], messages: list[dict],
                    max_tokens: int = 2048, stats: dict | None = None) -> Iterator[str]:
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
                    if stats is not None:
                        # 마지막 청크에 정확한 토큰 카운트가 실려 온다
                        stats["usage"] = {
                            "input_tokens": chunk.get("prompt_eval_count", 0),
                            "output_tokens": chunk.get("eval_count", 0),
                        }
                        # 프롬프트 처리 시간 — 프리픽스 캐시 히트 여부의 지표
                        stats["prompt_eval"] = chunk.get("prompt_eval_duration", 0) / 1e9
                    break

    def complete(self, system: str | list[str], messages: list[dict],
                 max_tokens: int = 1024, stats: dict | None = None) -> str:
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json=self._payload(system, messages, stream=False),
            timeout=httpx.Timeout(120, connect=5),
        )
        r.raise_for_status()
        data = r.json()
        if stats is not None:
            stats["usage"] = {
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            }
        return data.get("message", {}).get("content", "")
