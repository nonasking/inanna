"""ElevenLabs — 감정 표현 특화 상용 TTS. `INANNA_ELEVENLABS_API_KEY` 필요.

멀티링구얼 모델이 한국어를 지원하고, 텍스트의 감정 결을 억양에 자동 반영한다.
v3 계열 모델은 [laughs] 같은 오디오 태그로 웃음·한숨을 실제 소리로 연기한다.
"""
import re
import time

import httpx

from .. import config
from ..companion.schema import Voice
from .base import AUDIO_TAG_RE, clean_for_tts

BASE = "https://api.elevenlabs.io/v1"

# v3 오디오 태그 변환 — "하하"를 낭독하는 대신 실제로 웃게 한다.
# 자막/대화 기록에는 원문이 남고, 합성 입력만 바뀐다.
_V3_TAGS = [
    (re.compile(r"(?<![가-힣])하{2,}(?![가-힣])"), " [laughs] "),
    (re.compile(r"(?<![가-힣])[헤히]{2,}(?![가-힣])"), " [giggles] "),
    (re.compile(r"[ㅋ]{2,}"), " [laughs] "),
    (re.compile(r"[ㅎ]{2,}"), " [giggles] "),
    (re.compile(r"(?<![가-힣])(에휴|하아|후우)(?![가-힣])"), " [sighs] "),
]


def _apply_v3_tags(text: str) -> str:
    for pattern, tag in _V3_TAGS:
        text = pattern.sub(tag, text)
    return re.sub(r"\s+", " ", text).strip()


class ElevenLabsEngine:
    name = "elevenlabs"
    # 요청 간 운율 연속성이 없어 문장을 묶어 보내는 게 자연스럽다 (톤 튐 방지)
    chunk_min_chars = 60
    concurrency = 3  # 통화 청크 병렬 합성 (플랜 동시 요청 한도 내)

    def __init__(self):
        self._voices_cache: list[dict] = []
        self._voices_at = 0.0

    def _headers(self) -> dict:
        return {"xi-api-key": config.ELEVENLABS_API_KEY}

    def voices(self) -> list[dict]:
        if not config.ELEVENLABS_API_KEY:
            return []
        if self._voices_cache and time.time() - self._voices_at < 300:
            return self._voices_cache
        try:
            r = httpx.get(f"{BASE}/voices", headers=self._headers(),
                          timeout=httpx.Timeout(10, connect=3))
            r.raise_for_status()
            self._voices_cache = [
                {"id": v["voice_id"], "name": v.get("name", v["voice_id"]),
                 "gender": (v.get("labels") or {}).get("gender", ""), "lang": "multi"}
                for v in r.json().get("voices", [])
            ]
            self._voices_at = time.time()
        except Exception:
            return self._voices_cache or []
        return self._voices_cache

    async def synthesize(self, text: str, voice: Voice,
                         prev_text: str = "") -> tuple[bytes, str]:
        if not config.ELEVENLABS_API_KEY:
            raise RuntimeError("ElevenLabs API 키가 설정되지 않았습니다 (INANNA_ELEVENLABS_API_KEY)")
        if not voice.voice_id:
            raise RuntimeError("ElevenLabs 보이스가 선택되지 않았습니다")
        model = voice.model or config.ELEVENLABS_MODEL
        is_v3 = "v3" in model
        if is_v3:
            text = _apply_v3_tags(text)  # clean_for_tts 전에 — ㅋㅋ를 지우기 전에 태그로
        # v3는 LLM이 직접 쓴 오디오 태그([whispers] 등)도 소리로 연기한다
        text = clean_for_tts(text, keep_tags=is_v3)
        if not text or not re.search(r"[가-힣a-zA-Z0-9]", AUDIO_TAG_RE.sub("", text)):
            return b"", "audio/mpeg"  # 태그만 남은 경우(웃음만 있는 문장)도 스킵
        payload = {
            "text": text,
            "model_id": voice.model or config.ELEVENLABS_MODEL,
            # stability 0.5 = Natural — 낮으면 표현력↑ 대신 톤이 출렁인다.
            # (v3 계열은 0.0/0.5/1.0 단계값 요구)
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                               "speed": voice.speed},
        }
        if prev_text:
            # request stitching — 직전 발화를 운율 맥락으로 (문장별 억양 리셋/톤 튐 방지)
            payload["previous_text"] = prev_text[-500:]

        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5)) as client:
            url = f"{BASE}/text-to-speech/{voice.voice_id}?output_format=mp3_44100_128"
            r = await client.post(url, json=payload, headers=self._headers())
            if r.status_code >= 400 and "previous_text" in payload:
                # 일부 모델(v3 알파 등)이 stitching 미지원일 수 있음 — 빼고 재시도
                payload.pop("previous_text")
                r = await client.post(url, json=payload, headers=self._headers())
            if r.status_code >= 400:
                raise RuntimeError(f"ElevenLabs: {r.text[:200]}")
            return r.content, "audio/mpeg"
