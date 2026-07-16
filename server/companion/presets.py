"""미리 설정된 체험용 컴패니언 (프리셋).

빈 목록 앞의 막막함을 덜어주는 오리지널 페르소나들 — 저작권 안전(IP 없음),
무형(성격·목소리만). 관계 유형별 대표 하나씩, 연인은 남주/여주 둘.

흐름: 목록에서 고름 → 무저장 체험 대화(preview) → 마음에 들면 '데려오기'(adopt)로
내 컴패니언에 새 id로 복사. 이후 편집·성장은 사용자의 것.
"""
from functools import lru_cache

import yaml

from .. import config
from .schema import Companion


@lru_cache(maxsize=1)
def load_presets() -> dict[str, Companion]:
    out: dict[str, Companion] = {}
    if not config.PRESETS_DIR.exists():
        return out
    for p in sorted(config.PRESETS_DIR.glob("*.yaml")):
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.setdefault("id", f"preset-{p.stem}")
        c = Companion.model_validate(data)
        out[c.id] = c
    return out


def get(preset_id: str) -> Companion | None:
    return load_presets().get(preset_id)


def summaries() -> list[dict]:
    """목록 카드용 — 전체 페르소나를 노출하지 않고 요약만."""
    return [
        {"id": c.id, "name": c.name, "template": c.relationship.template,
         "concept": (c.persona.description or "").split(".")[0].split("。")[0][:60],
         "voice_engine": c.voice.engine}
        for c in load_presets().values()
    ]
