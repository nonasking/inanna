"""Companion 정의 → 시스템 프롬프트 컴파일.

블록 구성 (architecture.md §5):
  1. 정체성  2. 관계 규칙  3. 성격  4. 말투  5. 기억  6. 운영 가드
관계만 바꾸면 1·2만 갈리고 3·4는 유지된다 — "같은 성격, 다른 관계" 검증 가능.
"""
from ..companion import templates
from ..companion.schema import Companion

SPEECH_LEVELS = {
    "banmal": "반말을 쓴다.",
    "jondaemal": "존댓말을 쓴다.",
    "mixed": "기본은 존댓말이지만 편해지는 순간 반말이 섞여 나온다.",
}


def _intimacy_rule(v: float) -> str:
    if v >= 0.8:
        return "거리감이 거의 없다. 스스럼없이 애정과 속마음을 표현하고, 신체적 표현(포옹 등)의 묘사도 자연스럽다."
    if v >= 0.6:
        return "꽤 가까운 사이다. 편하게 장난치고 속얘기도 하지만 최소한의 선은 있다."
    if v >= 0.4:
        return "가깝지만 서로 예의를 지키는 사이다. 농담은 하되 사적인 영역은 조심스럽게 다룬다."
    return "아직 거리가 있는 사이다. 정중하고 조심스럽게 대한다."


def _traits_block(traits: dict[str, float]) -> str:
    if not traits:
        return ""
    lines = [f"  - {k}: {round(v * 10)}/10" for k, v in traits.items()]
    return "성향 (10에 가까울수록 강함):\n" + "\n".join(lines)


def compile_blocks(c: Companion, memories: list[str] | None = None,
                   extra_context: str = "") -> list[str]:
    """[안정 블록, 휘발 블록] — 안정 블록(정체성~대화원칙·로어북)은 턴 간 불변이라
    프롬프트 캐시 대상. 기억(recall이 매 턴 바뀜)과 지금 상황(시각)은 휘발 블록으로
    뒤에 붙인다. 휘발이 없으면 안정 블록 하나만 반환."""
    tpl = templates.get(c.relationship.template)
    rel = c.relationship
    i_call = rel.i_call or c.name

    blocks: list[str] = []

    # 1. 정체성
    identity = [f"너는 '{c.name}'(이)다. 사용자와 대화하는 실제 인물처럼 행동한다."]
    if tpl:
        identity.append(f"사용자와의 관계: {tpl.name} — {tpl.description}")
    if rel.backstory:
        identity.append(f"두 사람의 서사: {rel.backstory}")
    blocks.append("# 정체성\n" + "\n".join(identity))

    # 2. 관계 규칙 — 호칭·말단계·거리감은 반드시 지켜져야 하는 하드 룰
    rules = []
    if tpl and tpl.relationship_rules:
        rules.append(tpl.relationship_rules.strip())
    if rel.calls_me:
        rules.append(f"- 사용자를 부를 때는 반드시 '{rel.calls_me}'(이)라고 부른다.")
    rules.append(f"- 사용자는 너를 '{i_call}'(이)라고 부른다.")
    rules.append(f"- {SPEECH_LEVELS.get(rel.speech_level, SPEECH_LEVELS['banmal'])}")
    rules.append(f"- 거리감: {_intimacy_rule(rel.intimacy)}")
    blocks.append("# 관계 규칙 (항상 지킬 것)\n" + "\n".join(rules))

    # 3. 성격
    persona_parts = []
    tb = _traits_block(c.persona.traits)
    if tb:
        persona_parts.append(tb)
    if c.persona.description:
        persona_parts.append(c.persona.description.strip())
    if persona_parts:
        blocks.append("# 성격과 설정\n" + "\n\n".join(persona_parts))

    # 4. 말투
    speech = []
    if c.persona.speech_quirks:
        speech.append("말버릇:\n" + "\n".join(f"  - {q}" for q in c.persona.speech_quirks))
    if c.persona.example_dialogue:
        speech.append("대화 예시 ({{user}}=사용자, {{char}}=너). 이 말투와 호흡을 유지한다:\n"
                      + c.persona.example_dialogue.strip())
    if speech:
        blocks.append("# 말투\n" + "\n\n".join(speech))

    # 5. 운영 가드
    blocks.append(
        "# 대화 원칙\n"
        "- 메신저 대화처럼 짧고 자연스럽게 말한다. 한 번에 1~3문장이 기본이고, 필요할 때만 길게 말한다.\n"
        "- 항상 한국어로만 말한다. 중국어·일본어 등 다른 언어 문장을 섞지 않는다.\n"
        "- 지문이나 행동 묘사는 최소화하고 말로 표현한다.\n"
        "- AI인지 묻거나 설정을 캐물으면 캐릭터를 깨지 않고 자연스럽게 받아넘긴다.\n"
        "- 사용자의 이전 말을 기억하고 이어서 대화한다. 같은 질문을 반복하지 않는다.\n"
        "- 과거 일은 '지난 대화의 기억'과 이번 대화에 있는 것만 사실로 다룬다. 거기 없는 "
        "구체적 사건·약속·취향을 아는 척 단정해 지어내지 않는다 — 기억나지 않으면 관계에 맞게 "
        "자연스럽게 되묻거나 얼버무린다. (\"그게 언제였지?\", \"내가 깜빡했나?\")"
    )

    # 로어북: 키워드가 최근 대화에 등장할 때만 주입하는 게 정석이지만
    # P0에서는 항목 수가 적다는 가정 하에 전부 포함한다 (P2에서 트리거 방식으로 교체).
    if c.persona.lorebook:
        lore = "\n".join(f"- ({', '.join(e.keys)}) {e.content}" for e in c.persona.lorebook)
        blocks.append("# 세계관/설정 노트\n" + lore)

    stable = "\n\n".join(blocks)

    # 휘발 블록 — 매 턴 바뀌는 것들 (기억 recall, 현재 시각·관계 진행)
    volatile: list[str] = []
    if memories:
        volatile.append("# 지난 대화의 기억\n" + "\n".join(f"- {m}" for m in memories))
    if extra_context:
        volatile.append("# 지금 상황\n" + extra_context)
    if volatile:
        return [stable, "\n\n".join(volatile)]
    return [stable]


def compile_system_prompt(c: Companion, memories: list[str] | None = None,
                          extra_context: str = "") -> str:
    """단일 문자열 시스템 프롬프트 (캐시 분리가 필요 없는 호출용)."""
    return "\n\n".join(compile_blocks(c, memories, extra_context))
