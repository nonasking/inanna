import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """ROOT/.env를 환경변수로 로드 (실제 환경변수가 우선).

    설정을 launchd plist에 두면 변경 시 bootout→bootstrap이 필요해서,
    .env 파일을 소스로 쓴다 — 편집 후 kickstart만으로 반영된다.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(ROOT / ".env")

COMPANIONS_DIR = Path(os.environ.get("INANNA_COMPANIONS_DIR", ROOT / "companions"))
TEMPLATES_DIR = ROOT / "templates"
WEB_DIR = ROOT / "web"
DB_PATH = Path(os.environ.get("INANNA_DB", ROOT / "inanna.db"))

# 설정 시 모든 /api 요청에 Authorization: Bearer <token> 요구
AUTH_TOKEN = os.environ.get("INANNA_AUTH_TOKEN", "")
# 클로즈베타: 설정 시 회원가입에 초대 코드 요구 (쉼표 구분 복수 가능)
INVITE_CODES = {c.strip() for c in os.environ.get("INANNA_INVITE_CODES", "").split(",")
                if c.strip()}
# 셀프호스팅 단일 유저 id — 제품 모드(P4)에서 계정 인증이 이 자리를 대체한다
DEFAULT_USER = "local"

# ---------- LLM 프로바이더 ----------
# 전역 기본. 컴패니언별 오버라이드(companion.model)가 우선한다.
PROVIDER = os.environ.get("INANNA_PROVIDER", "anthropic")  # anthropic | ollama | openai
ANTHROPIC_MODEL = os.environ.get("INANNA_MODEL", "claude-sonnet-5")
OLLAMA_MODEL = os.environ.get("INANNA_OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
# OpenAI 호환 엔드포인트 (OpenAI/OpenRouter/Groq/LM Studio/llama.cpp/vLLM …)
OPENAI_BASE_URL = os.environ.get("INANNA_OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.environ.get("INANNA_OPENAI_API_KEY",
                                os.environ.get("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.environ.get("INANNA_OPENAI_MODEL", "gpt-4o-mini")
# 기억 요약 전용 모델 분리 (비우면 대화 기본과 동일).
# 요약 품질이 나쁘면 기억이 오염되므로, 대화를 로컬로 돌려도 요약은 좋은 모델 권장.
SUMMARY_PROVIDER = os.environ.get("INANNA_SUMMARY_PROVIDER", "")
SUMMARY_MODEL = os.environ.get("INANNA_SUMMARY_MODEL", "")

# 대화 응답 상한 — 컴패니언 답변은 의도적으로 짧다
CHAT_MAX_TOKENS = int(os.environ.get("INANNA_CHAT_MAX_TOKENS", "2048"))
# 이 시간(초) 넘게 조용하면 다음 메시지는 새 세션으로 취급
SESSION_GAP_SECONDS = int(os.environ.get("INANNA_SESSION_GAP", str(4 * 3600)))
# 프롬프트에 넣는 현재 세션 최대 턴 수 / 주입할 기억 개수 (최근 + 관련)
HISTORY_LIMIT = 40
MEMORY_LIMIT = 10          # (하위호환) history 엔드포인트 등에서 사용
MEMORY_RECENT = 5          # 최근 기억 — 항상 주입
MEMORY_RELEVANT = 5        # 현재 발화와 관련 높은 기억 — BM25 검색

VOICES_DIR = Path(os.environ.get("INANNA_VOICES_DIR", ROOT / "voices"))
# GPT-SoVITS api_v2 서버 주소 (보이스 클로닝용 원격/로컬 TTS 워커)
SOVITS_URL = os.environ.get("INANNA_SOVITS_URL", "")
# whisper.cpp 상주 서버 (실시간 음성 대화 STT)
WHISPER_URL = os.environ.get("INANNA_WHISPER_URL", "http://127.0.0.1:9881")
# ElevenLabs (감정 표현 특화 TTS — 선택)
ELEVENLABS_API_KEY = os.environ.get("INANNA_ELEVENLABS_API_KEY",
                                    os.environ.get("ELEVENLABS_API_KEY", ""))
ELEVENLABS_MODEL = os.environ.get("INANNA_ELEVENLABS_MODEL", "eleven_multilingual_v2")
# 목록 API에 안 나오는 커스텀 보이스를 픽커에 추가 — "id:이름,id:이름" 형식
# (Voice Design 등으로 만든 보이스는 /v1/voices에 안 잡히는 경우가 있다)
ELEVENLABS_EXTRA_VOICES = [
    {"id": pair.split(":")[0].strip(),
     "name": (pair.split(":", 1)[1].strip() if ":" in pair else pair.strip()),
     "gender": "", "lang": "multi"}
    for pair in os.environ.get("INANNA_ELEVENLABS_EXTRA_VOICES", "").split(",")
    if pair.strip()
]

COMPANIONS_DIR.mkdir(parents=True, exist_ok=True)
VOICES_DIR.mkdir(parents=True, exist_ok=True)
