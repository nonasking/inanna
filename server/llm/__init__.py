from functools import lru_cache

from .. import config
from .base import LLMProvider

# 프로바이더 id → (표시 이름, 기본 모델을 주는 config 속성)
PROVIDERS = {
    "anthropic": "Anthropic (Claude)",
    "ollama": "Ollama (로컬)",
    "openai": "OpenAI 호환 (클라우드/로컬 서버)",
}


@lru_cache(maxsize=16)
def _make(provider: str, model: str) -> LLMProvider:
    if provider == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(model or config.OLLAMA_MODEL, config.OLLAMA_BASE_URL)
    if provider == "openai":
        from .openai_provider import OpenAICompatProvider
        return OpenAICompatProvider(model or config.OPENAI_MODEL,
                                    config.OPENAI_BASE_URL, config.OPENAI_API_KEY)
    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(model or config.ANTHROPIC_MODEL)
    raise ValueError(f"unknown provider: {provider!r}")


def get_provider(provider: str = "", model: str = "") -> LLMProvider:
    """provider/model이 비면 전역 기본. 컴패니언 오버라이드가 이 인자로 들어온다."""
    return _make(provider or config.PROVIDER, model)


def get_summary_provider() -> LLMProvider:
    """기억 요약 전용 — 분리 설정이 없으면 대화 기본과 동일."""
    if config.SUMMARY_PROVIDER or config.SUMMARY_MODEL:
        return _make(config.SUMMARY_PROVIDER or config.PROVIDER, config.SUMMARY_MODEL)
    return get_provider()
