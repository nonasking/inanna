from pydantic import BaseModel, Field


class Relationship(BaseModel):
    template: str = "friend"
    calls_me: str = ""          # 컴패니언이 나를 부르는 호칭
    i_call: str = ""            # 내가 컴패니언을 부르는 이름 (비우면 name)
    speech_level: str = "banmal"  # banmal | jondaemal | mixed
    intimacy: float = 0.7       # 거리감 0(격식)~1(밀착)
    backstory: str = ""         # 어떻게 만난 사이인가


class LoreEntry(BaseModel):
    keys: list[str] = []
    content: str = ""


class Persona(BaseModel):
    traits: dict[str, float] = {}       # 성향 0~1 (밝음, 직설, 장난기 …)
    speech_quirks: list[str] = []       # 말버릇
    description: str = ""               # 자유 서술 (CCv2/v3 description 호환)
    example_dialogue: str = ""          # 말투 few-shot (CCv2 mes_example 호환)
    first_message: str = ""             # 첫 인사 (CCv2 first_mes 호환)
    lorebook: list[LoreEntry] = []


class ModelOverride(BaseModel):
    """컴패니언별 LLM 선택 — 비우면 전역 기본(config.PROVIDER)을 따른다.

    제품 모드에서는 이 자리가 과금 티어(라이트/스탠다드/딥)와 매핑된다.
    """
    provider: str = ""   # "" | anthropic | ollama | openai
    name: str = ""       # 모델 id (비우면 프로바이더 기본)


class Voice(BaseModel):
    engine: str = ""            # "" (없음) | edge | sovits | elevenlabs
    voice_id: str = ""          # 보이스 id (edge 프리셋, elevenlabs 보이스 등)
    model: str = ""             # 엔진 내 모델 등급 (elevenlabs: eleven_v3 등. 비우면 엔진 기본)
    reference_audio: str = ""   # 보이스 클로닝 참조 오디오 경로 (sovits)
    ref_text: str = ""          # 참조 오디오가 말하는 내용 (sovits 품질 향상용)
    speed: float = 1.0


class Companion(BaseModel):
    id: str
    name: str
    relationship: Relationship = Field(default_factory=Relationship)
    persona: Persona = Field(default_factory=Persona)
    voice: Voice = Field(default_factory=Voice)
    model: ModelOverride = Field(default_factory=ModelOverride)


class RelationshipTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    defaults: Relationship = Field(default_factory=Relationship)
    relationship_rules: str = ""   # 프롬프트 관계 규칙 블록의 뼈대
    backstory_hint: str = ""
