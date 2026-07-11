import re
from typing import Protocol

from ..companion.schema import Voice


class TTSEngine(Protocol):
    name: str
    # 문장 묶음 최소 길이 (통화 스트리밍) — 0이면 문장 단위 즉시 합성.
    # 요청 간 운율 연속성이 없는 클라우드 엔진은 크게 묶는 편이 자연스럽다.
    chunk_min_chars: int

    async def synthesize(self, text: str, voice: Voice,
                         prev_text: str = "") -> tuple[bytes, str]:
        """텍스트 → (오디오 바이트, MIME 타입). prev_text는 운율 맥락(지원 엔진만)."""
        ...

    def voices(self) -> list[dict]:
        """프리셋 보이스 목록 [{id, name, gender, lang}]. 클로닝 엔진은 빈 목록."""
        ...


_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF️]+"
)
_LAUGH = re.compile(r"[ㅋㅎㅠㅜ]{1,}")
_MD = re.compile(r"[*_`#>~]+")

# 오디오 태그 — v3급 TTS가 소리로 연기하는 지시어 ([laughs], [whispers] 등).
# LLM이 통화 중 직접 생성할 수 있고, 자막·DB·비지원 엔진에서는 제거한다.
AUDIO_TAG_RE = re.compile(r"\[[a-zA-Z][a-zA-Z ]{1,30}\]")


def strip_audio_tags(text: str) -> str:
    return re.sub(r" {2,}", " ", AUDIO_TAG_RE.sub(" ", text)).strip()


def clean_for_tts(text: str, keep_tags: bool = False) -> str:
    """메신저 말투를 음성용으로 정리 — 이모지·자음 웃음·마크다운 제거.

    ㅋㅋ/ㅎㅎ를 그대로 읽으면 어색해서 제거한다. keep_tags는 오디오 태그를
    소리로 연기하는 엔진(ElevenLabs v3)용 — 그 외엔 태그를 읽어버리므로 제거.
    """
    if not keep_tags:
        text = AUDIO_TAG_RE.sub(" ", text)
    text = _EMOJI.sub(" ", text)
    text = _LAUGH.sub(" ", text)
    text = _MD.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()
