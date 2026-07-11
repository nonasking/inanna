"""Edge TTS — 마이크로소프트 뉴럴 보이스. 무료·즉시 동작하는 프리셋 엔진.

보이스 클로닝은 안 되지만 한국어 품질이 준수해서 개발 기본값으로 쓴다.
"""
import edge_tts

from ..companion.schema import Voice
from .base import clean_for_tts

# 큐레이션된 프리셋 (전체 목록은 `edge-tts --list-voices`)
PRESETS = [
    {"id": "ko-KR-SunHiNeural", "name": "선히 (여)", "gender": "female", "lang": "ko"},
    {"id": "ko-KR-InJoonNeural", "name": "인준 (남)", "gender": "male", "lang": "ko"},
    {"id": "ko-KR-HyunsuMultilingualNeural", "name": "현수 (남·다국어)", "gender": "male", "lang": "ko"},
    {"id": "ja-JP-NanamiNeural", "name": "나나미 (여·일본어)", "gender": "female", "lang": "ja"},
    {"id": "en-US-AriaNeural", "name": "Aria (여·영어)", "gender": "female", "lang": "en"},
]
DEFAULT_VOICE = "ko-KR-SunHiNeural"


class EdgeEngine:
    name = "edge"
    chunk_min_chars = 0
    concurrency = 2  # 통화 청크 병렬 합성

    def voices(self) -> list[dict]:
        return PRESETS

    async def synthesize(self, text: str, voice: Voice,
                         prev_text: str = "") -> tuple[bytes, str]:
        text = clean_for_tts(text)
        if not text:
            return b"", "audio/mpeg"
        rate = f"{'+' if voice.speed >= 1 else ''}{round((voice.speed - 1) * 100)}%"
        communicate = edge_tts.Communicate(
            text, voice.voice_id or DEFAULT_VOICE, rate=rate,
        )
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks), "audio/mpeg"
