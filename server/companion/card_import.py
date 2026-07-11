"""CCv2/CCv3 캐릭터 카드 임포트 — PNG(tEXt 청크) 또는 raw JSON."""
import base64
import json
import re
import struct

from .schema import Companion, LoreEntry, Persona, Relationship

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_text_chunks(data: bytes) -> dict[str, str]:
    """PNG의 tEXt 청크를 {keyword: text}로 추출."""
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG file")
    out: dict[str, str] = {}
    pos = len(PNG_SIG)
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"tEXt" and b"\x00" in chunk:
            key, _, text = chunk.partition(b"\x00")
            out[key.decode("latin-1")] = text.decode("latin-1")
        if ctype == b"IEND":
            break
        pos += 8 + length + 4  # length + type/data + crc
    return out


def parse_card(data: bytes) -> dict:
    """PNG 또는 JSON 바이트에서 카드 JSON 객체를 꺼낸다."""
    if data.startswith(PNG_SIG):
        chunks = _png_text_chunks(data)
        raw = chunks.get("ccv3") or chunks.get("chara")
        if not raw:
            raise ValueError("no character card found in PNG (missing chara/ccv3 tEXt chunk)")
        return json.loads(base64.b64decode(raw))
    return json.loads(data.decode("utf-8"))


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
    return slug or "imported"


def to_companion(card: dict) -> Companion:
    """CCv2/CCv3 카드 → Companion 매핑. spec 필드가 없으면 v1 평면 구조로 취급."""
    node = card.get("data", card)

    name = node.get("name") or "이름없음"
    description = node.get("description") or ""
    personality = node.get("personality") or ""
    scenario = node.get("scenario") or ""
    system_prompt = node.get("system_prompt") or ""

    desc_parts = [p for p in [description, personality and f"성격 요약: {personality}",
                              scenario and f"시나리오: {scenario}",
                              system_prompt and f"카드 시스템 프롬프트: {system_prompt}"] if p]

    lorebook: list[LoreEntry] = []
    book = node.get("character_book") or {}
    for entry in book.get("entries", []):
        keys = entry.get("keys") or []
        content = entry.get("content") or ""
        if content:
            lorebook.append(LoreEntry(keys=[str(k) for k in keys], content=content))

    return Companion(
        id=_slugify(name),
        name=name,
        relationship=Relationship(template="friend"),  # 관계는 Inanna의 축 — 임포트 후 사용자가 고른다
        persona=Persona(
            description="\n\n".join(desc_parts),
            example_dialogue=node.get("mes_example") or "",
            first_message=node.get("first_mes") or "",
            lorebook=lorebook,
        ),
    )
