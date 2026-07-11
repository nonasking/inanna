"""GPT-SoVITS 어댑터 — 참조 오디오 기반 보이스 클로닝.

GPT-SoVITS api_v2 서버(`python api_v2.py`)를 별도 프로세스/원격 머신에서 돌리고
INANNA_SOVITS_URL로 연결한다. 참조 오디오는 Inanna의 voices/ 디렉터리에 있고,
api_v2가 같은 머신이면 절대경로로 전달된다 (원격 워커면 공유 볼륨 필요 — P2에서
업로드 방식으로 개선).
"""
import httpx

from .. import config
from ..companion.schema import Voice
from .base import clean_for_tts


class SovitsEngine:
    name = "sovits"
    chunk_min_chars = 0  # CPU 합성이 느려서 문장 단위 조기 시작이 유리

    def voices(self) -> list[dict]:
        return []  # 프리셋 없음 — 참조 오디오가 곧 보이스

    async def synthesize(self, text: str, voice: Voice,
                         prev_text: str = "") -> tuple[bytes, str]:
        if not config.SOVITS_URL:
            raise RuntimeError("INANNA_SOVITS_URL이 설정되지 않았습니다 (GPT-SoVITS 워커 필요)")
        if not voice.reference_audio:
            raise RuntimeError("참조 오디오가 등록되지 않았습니다")

        ref_path = config.VOICES_DIR / voice.reference_audio
        params = {
            "text": clean_for_tts(text),
            "text_lang": "ko",
            "ref_audio_path": str(ref_path),
            "prompt_text": voice.ref_text or "",
            "prompt_lang": "ko",
            "speed_factor": voice.speed,
            "media_type": "wav",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as client:
            r = await client.get(f"{config.SOVITS_URL.rstrip('/')}/tts", params=params)
            if r.status_code >= 400:
                # 워커의 실제 원인("3~10초 범위" 등)을 사용자에게 그대로 전달
                try:
                    detail = r.json().get("Exception") or r.json().get("message")
                except Exception:
                    detail = r.text[:200]
                raise RuntimeError(f"GPT-SoVITS: {detail}")
            return r.content, "audio/wav"
