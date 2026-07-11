from functools import lru_cache

from .base import TTSEngine

ENGINES = {
    "edge": "프리셋 보이스",
    "sovits": "보이스 클로닝 (GPT-SoVITS)",
    "elevenlabs": "감정 표현 (ElevenLabs)",
}


@lru_cache(maxsize=4)
def get_engine(name: str) -> TTSEngine:
    if name == "edge":
        from .edge import EdgeEngine
        return EdgeEngine()
    if name == "sovits":
        from .sovits import SovitsEngine
        return SovitsEngine()
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsEngine
        return ElevenLabsEngine()
    raise ValueError(f"unknown tts engine: {name!r}")
