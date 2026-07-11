"""whisper.cpp 상주 서버(/inference) 클라이언트."""
import re
import struct

import httpx

from .. import config

# 무음/잡음에서 whisper가 지어내는 한국어 상투 환각들
_HALLUCINATIONS = (
    "시청해 주셔서", "시청해주셔서", "시청 해주셔서", "구독", "좋아요 부탁",
    "다음 영상에서", "뉴스 김", "MBC 뉴스", "KBS 뉴스", "자막 제공",
    "감사합니다.",  # 단독 "감사합니다."만 찍히는 패턴
)
_HAS_CONTENT = re.compile(r"[가-힣a-zA-Z0-9]")


def wav_bytes(pcm: bytes, rate: int = 16000) -> bytes:
    """raw PCM16 mono → WAV 컨테이너."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16,
        1, 1, rate, rate * 2, 2, 16, b"data", len(pcm),
    ) + pcm


async def transcribe(pcm: bytes) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=3)) as client:
        r = await client.post(
            f"{config.WHISPER_URL.rstrip('/')}/inference",
            files={"file": ("utterance.wav", wav_bytes(pcm), "audio/wav")},
            data={"response_format": "json"},
        )
        r.raise_for_status()
        return (r.json().get("text") or "").strip()


def is_valid(text: str) -> bool:
    if len(text) < 2 or not _HAS_CONTENT.search(text):
        return False
    if text in _HALLUCINATIONS:
        return False
    return not any(h in text for h in _HALLUCINATIONS if len(h) > 4)
