import re

import yaml

from .. import config
from .schema import Companion

_ID_RE = re.compile(r"[a-zA-Z0-9_-]{1,64}")


def _user_dir(user_id: str):
    if not _ID_RE.fullmatch(user_id):
        raise ValueError(f"invalid user id: {user_id!r}")
    return config.COMPANIONS_DIR / user_id


def _path(user_id: str, companion_id: str):
    if not _ID_RE.fullmatch(companion_id):
        raise ValueError(f"invalid companion id: {companion_id!r}")
    return _user_dir(user_id) / f"{companion_id}.yaml"


def list_companions(user_id: str) -> list[Companion]:
    d = _user_dir(user_id)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.yaml")):
        try:
            out.append(load(user_id, p.stem))
        except Exception:
            continue
    return out


def load(user_id: str, companion_id: str) -> Companion:
    p = _path(user_id, companion_id)
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("id", companion_id)
    return Companion.model_validate(data)


def save(user_id: str, companion: Companion) -> None:
    p = _path(user_id, companion.id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            companion.model_dump(), f,
            allow_unicode=True, sort_keys=False, default_flow_style=False,
        )


def delete(user_id: str, companion_id: str) -> None:
    _path(user_id, companion_id).unlink(missing_ok=True)


def exists(user_id: str, companion_id: str) -> bool:
    return _path(user_id, companion_id).exists()
