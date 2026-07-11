from functools import lru_cache

import yaml

from .. import config
from .schema import RelationshipTemplate


@lru_cache(maxsize=1)
def load_templates() -> dict[str, RelationshipTemplate]:
    out: dict[str, RelationshipTemplate] = {}
    for p in sorted(config.TEMPLATES_DIR.glob("*.yaml")):
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.setdefault("id", p.stem)
        t = RelationshipTemplate.model_validate(data)
        out[t.id] = t
    return out


def get(template_id: str) -> RelationshipTemplate | None:
    return load_templates().get(template_id)
