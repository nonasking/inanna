import asyncio
import json
import secrets

import uvicorn
from fastapi import (Depends, FastAPI, Header, HTTPException, Request, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, billing, config, safety, tts
from .chat import onboard, orchestrator
from .companion import card_import, presets, store, templates
from .companion.schema import Companion, Voice
from .llm import get_provider
from .memory import db

# 페일클로즈(보안 M3): 초대제(=외부 노출 의도)인데 오너 토큰이 비어 있으면
# 익명 요청이 오너('local')로 폴백해 전 API가 조용히 열린다 — 기동을 거부한다.
# (invites 테이블 기반 초대제도 동일 — 기동 시점에는 config만 확인 가능하므로
#  여기서는 env 설정을 본다. 운영 중 발급되는 1회용 코드는 아래 API로 관리한다.)
if config.INVITE_CODES and not config.AUTH_TOKEN:
    raise RuntimeError(
        "INANNA_INVITE_CODES가 설정됐는데 INANNA_AUTH_TOKEN이 비어 있습니다. "
        "외부 노출 구성에서는 오너 토큰이 필수입니다 (.env 확인).")

app = FastAPI(title="Inanna")
db.init()

# .env의 INANNA_INVITE_CODES는 '부트스트랩 시드'다 — 1회용 코드로 등록된다.
# (예전엔 무한 재사용이라 코드 1개 유출 = 계정 무한 생성이었다.)
for _code in config.INVITE_CODES:
    db.create_invite(_code, note="env seed")


@app.on_event("startup")
async def _warm_llm() -> None:
    """로컬 모델을 미리 올려둔다 — 첫 대화가 콜드 로드(수 초)를 맞지 않게."""
    provider = get_provider()
    if not hasattr(provider, "warmup"):
        return
    asyncio.get_running_loop().run_in_executor(None, provider.warmup)


@app.middleware("http")
async def static_no_cache(request, call_next):
    """폰 브라우저(PWA)가 옛 JS를 캐시해 신구 코드가 섞이는 사고 방지 +
    기본 보안 헤더(클릭재킹·MIME 스니핑 차단, 최소 CSP)."""
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    # inline 핸들러(onclick=)를 쓰는 현 구조라 unsafe-inline 허용 —
    # 외부 출처 로드는 전부 차단된다
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self' ws: wss:; frame-ancestors 'none'")
    return response


def _resolve_user(token: str) -> str | None:
    """토큰 → user_id. 셀프호스팅 단일 토큰과 계정 세션 토큰을 모두 받는다."""
    if config.AUTH_TOKEN and secrets.compare_digest(token, config.AUTH_TOKEN):
        return config.DEFAULT_USER          # 셀프호스팅 오너 (기존 동작)
    return auth.resolve_token(token)        # 계정 유저 ('u<id>') 또는 None


def current_user(authorization: str | None = Header(None)) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = _resolve_user(token)
    if user:
        return user
    if config.AUTH_TOKEN:
        raise HTTPException(401, "unauthorized")
    return config.DEFAULT_USER              # 토큰 미설정 셀프호스팅 = 열린 단일 유저


# ---------- 계정 (P4 멀티유저 — 셀프호스팅 단일 토큰과 공존) ----------

# 인증 엔드포인트 레이트리밋 — 공개 노출(클로즈베타 Funnel) 대비 브루트포스 방어.
# 단일 프로세스 인메모리로 충분한 규모 (창 10분, IP당 20회)
_auth_hits: dict[str, list[float]] = {}


def _rate_limit(request, limit: int = 20, window: float = 600.0,
                key: str = "") -> None:
    import time as _time
    bucket = key or (request.client.host if request.client else "?")
    now = _time.time()
    hits = [t for t in _auth_hits.get(bucket, []) if now - t < window]
    if len(hits) >= limit:
        raise HTTPException(429, "요청이 너무 많아요. 잠시 후 다시 시도해주세요.")
    hits.append(now)
    _auth_hits[bucket] = hits


def _llm_rate_limit(request, user: str) -> None:
    """LLM을 태우는 경로 공통 — 계정(과금) 유저만, 유저 단위 분당 상한.
    쿼터(총량)와 별개로 순간 폭주를 막는다 (보안 H1)."""
    if billing.is_metered(user):
        _rate_limit(request, limit=20, window=60.0, key=f"llm:{user}")


class Credentials(BaseModel):
    email: str
    password: str
    invite: str = ""    # 클로즈베타: INANNA_INVITE_CODES 설정 시 필수
    agreed: bool = False  # 이용약관 동의 (가입 시 필수)


@app.post("/api/auth/register")
def auth_register(req: Credentials, request: Request):
    _rate_limit(request)
    if not req.agreed:
        raise HTTPException(400, "이용약관에 동의해야 가입할 수 있어요")
    try:
        token = auth.register(req.email, req.password, invite=req.invite)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"token": token}


@app.post("/api/auth/login")
def auth_login(req: Credentials, request: Request):
    _rate_limit(request)
    token = auth.login(req.email, req.password)
    if not token:
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다")
    return {"token": token}


@app.get("/api/auth/config")
def auth_config():
    """가입 화면 구성용 — 초대제 여부 (무인증 공개)."""
    return {"invite_required": bool(config.INVITE_CODES) or bool(db.list_invites())}


class InviteRequest(BaseModel):
    count: int = 1
    note: str = ""      # 누구에게 줄 코드인지 (운영 메모)


@app.post("/api/admin/invites")
def admin_create_invites(req: InviteRequest, user: str = Depends(current_user)):
    """1회용 초대 코드 발급 — 셀프호스팅 오너(운영자)만."""
    if user != config.DEFAULT_USER:
        raise HTTPException(403, "권한이 없습니다")
    codes = []
    for _ in range(max(1, min(req.count, 50))):
        code = f"inanna-{secrets.token_hex(4)}"
        db.create_invite(code, req.note)
        codes.append(code)
    return {"codes": codes}


@app.get("/api/admin/invites")
def admin_list_invites(user: str = Depends(current_user)):
    if user != config.DEFAULT_USER:
        raise HTTPException(403, "권한이 없습니다")
    return db.list_invites()


@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = Header(None),
                user: str = Depends(current_user)):
    auth.logout((authorization or "").removeprefix("Bearer ").strip())
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(user: str = Depends(current_user)):
    info = auth.account_info(user)
    return {"user_id": user, "email": info["email"] if info else None}


@app.delete("/api/auth/account")
def auth_delete(user: str = Depends(current_user)):
    """계정+전체 데이터 완전 삭제 — App Store 5.1.1(v) 요건, 데이터 소유 원칙."""
    if not user.startswith("u"):
        raise HTTPException(400, "셀프호스팅 오너 계정은 API로 삭제할 수 없습니다")
    for c in store.list_companions(user):
        store.delete(user, c.id)
    auth.delete_account(user)
    return {"ok": True}


# ---------- companions ----------

@app.get("/api/companions")
def list_companions(user: str = Depends(current_user)):
    return [c.model_dump() for c in store.list_companions(user)]


@app.get("/api/companions/{companion_id}")
def get_companion(companion_id: str, user: str = Depends(current_user)):
    try:
        return store.load(user, companion_id).model_dump()
    except FileNotFoundError:
        raise HTTPException(404, "companion not found")


@app.post("/api/companions")
def save_companion(companion: Companion, user: str = Depends(current_user)):
    store.save(user, companion)
    return {"ok": True, "id": companion.id}


@app.delete("/api/companions/{companion_id}")
def delete_companion(companion_id: str, user: str = Depends(current_user)):
    store.delete(user, companion_id)
    db.delete_companion_data(user, companion_id)
    return {"ok": True}


@app.get("/api/templates")
def list_templates(user: str = Depends(current_user)):
    return [t.model_dump() for t in templates.load_templates().values()]


@app.post("/api/import-card")
async def import_card(file: UploadFile, user: str = Depends(current_user)):
    data = await file.read()
    try:
        card = card_import.parse_card(data)
        companion = card_import.to_companion(card)
    except Exception as e:
        raise HTTPException(400, f"카드를 읽을 수 없습니다: {e}")
    # 저장하지 않고 빌더 초기값으로 돌려준다 — 관계 선택은 사용자의 몫
    return companion.model_dump()


# ---------- chat ----------

class ChatRequest(BaseModel):
    message: str


def _sse(gen, events: dict | None = None):
    def event_stream():
        try:
            for delta in gen:
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
            if events and events.get("notice"):
                # 쿼터 임계(80%) 통과의 조용한 안내 — 응답이 끝난 뒤 한 줄
                yield f"data: {json.dumps({'notice': events['notice']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except billing.QuotaExceeded as e:
            yield f"data: {json.dumps({'error': str(e), 'kind': 'quota'}, ensure_ascii=False)}\n\n"
        except safety.Suspended as e:
            yield f"data: {json.dumps({'error': str(e), 'kind': 'quota'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            # 내부 예외 원문은 서버 로그에만 — 클라이언트엔 일반 문구 (보안 L6)
            print(f"[sse error] {type(e).__name__}: {e}", flush=True)
            yield f"data: {json.dumps({'error': '잠시 연결이 고르지 않았어요. 다시 한 번 말해줄래요?'}, ensure_ascii=False)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/chat/{companion_id}")
def chat(companion_id: str, req: ChatRequest, request: Request,
         user: str = Depends(current_user)):
    _llm_rate_limit(request, user)
    try:
        companion = store.load(user, companion_id)
    except FileNotFoundError:
        raise HTTPException(404, "companion not found")
    try:
        safety.check_suspended(user)
        billing.check_chat_quota(user)  # SSE 시작 전에 깔끔한 402로
    except safety.Suspended as e:
        raise HTTPException(403, str(e))
    except billing.QuotaExceeded as e:
        raise HTTPException(402, str(e))
    session_id, _ = orchestrator.ensure_session(user, companion)
    events: dict = {}
    return _sse(orchestrator.chat_stream(user, companion, session_id, req.message,
                                         events=events), events)


@app.get("/api/chat/{companion_id}/history")
def history(companion_id: str, limit: int = 50, user: str = Depends(current_user)):
    try:
        companion = store.load(user, companion_id)
    except FileNotFoundError:
        raise HTTPException(404, "companion not found")
    rows = db.recent_history(user, companion_id, limit)
    if not rows:
        session_id, is_new = orchestrator.ensure_session(user, companion)
        if is_new or not db.session_messages(session_id):
            greeting = orchestrator.greeting(companion, session_id)
            if greeting:
                rows = [{"role": "assistant", "content": greeting, "ts": 0}]
    else:
        # 재방문 선제 인사 (기획 #3): 오랜만(3일+)의 새 세션이면 먼저 말을 건다
        import time as _time
        gap_days = int((_time.time() - rows[-1]["ts"]) // 86400)
        if gap_days >= orchestrator.REVISIT_GAP_DAYS:
            session_id, is_new = orchestrator.ensure_session(user, companion)
            if is_new:
                hello = orchestrator.proactive_greeting(user, companion,
                                                        session_id, gap_days)
                if hello:
                    rows = rows + [{"role": "assistant", "content": hello,
                                    "ts": _time.time()}]
    return {"messages": rows}


# ---------- 프리셋 (체험용 미리 설정 컴패니언) ----------

class PreviewMessages(BaseModel):
    messages: list[dict] = []


@app.get("/api/presets")
def list_presets(user: str = Depends(current_user)):
    """목록 카드 — 요약만 (전체 페르소나는 체험/데려오기에서 서버가 다룬다)."""
    return presets.summaries()


@app.post("/api/presets/{preset_id}/preview")
def preview_preset(preset_id: str, req: PreviewMessages, request: Request,
                   user: str = Depends(current_user)):
    """무저장 체험 대화 — 서버가 프리셋을 로드해 스트리밍 (쿼터·티어·안전 적용)."""
    _llm_rate_limit(request, user)
    c = presets.get(preset_id)
    if not c:
        raise HTTPException(404, "preset not found")
    # 첫 턴(사용자 발화 없음)은 손으로 쓴 first_message를 바로 내준다 (LLM 비용 0).
    if not any(m.get("role") == "user" for m in req.messages):
        greeting = (c.persona.first_message or "").replace("{{char}}", c.name) \
            .replace("{{user}}", c.relationship.calls_me or "너")

        def _greet():
            if greeting:
                yield f"data: {json.dumps({'delta': greeting}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        return StreamingResponse(_greet(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})
    return _sse(orchestrator.preview_stream(user, c, req.messages))


@app.post("/api/presets/{preset_id}/adopt")
def adopt_preset(preset_id: str, user: str = Depends(current_user)):
    """프리셋을 내 컴패니언으로 데려온다 — 새 id로 복사 + '처음 만난 날' 기억 시드."""
    import datetime
    import secrets
    c = presets.get(preset_id)
    if not c:
        raise HTTPException(404, "preset not found")
    c = c.model_copy(deep=True)
    c.id = f"c-{secrets.token_hex(4)}"     # 사용자별 새 인스턴스 (프리셋 원본은 불변)
    store.save(user, c)
    sid = db.create_session(user, c.id)
    db.mark_summarized(sid)
    today = datetime.date.today().isoformat()
    db.add_memory(user, c.id, f"[{today}] {c.name}를 처음 만난 날 — 서로 알아가기 시작했다.",
                  source_session=sid)
    return {"ok": True, "id": c.id, "name": c.name}


# ---------- 첫 만남 온보딩 (대화로 컴패니언이 형성된다) ----------

class OnboardRequest(BaseModel):
    companion: Companion          # 원형 — 관계·이름만 채워진 상태
    messages: list[dict] = []
    first_memory: str = ""


@app.post("/api/onboard/chat")
def onboard_chat(req: OnboardRequest, request: Request,
                 user: str = Depends(current_user)):
    """첫 만남 대화 스트림 — 무저장, 완료 시 complete가 기록한다."""
    _llm_rate_limit(request, user)
    return _sse(onboard.onboard_stream(user, req.companion, req.messages))


@app.post("/api/onboard/extract")
def onboard_extract(req: OnboardRequest, request: Request,
                    user: str = Depends(current_user)):
    _llm_rate_limit(request, user)
    try:
        return onboard.extract(user, req.companion, req.messages)
    except billing.QuotaExceeded as e:
        raise HTTPException(402, str(e))
    except Exception:
        raise HTTPException(502, "대화에서 성격을 정리하지 못했어요. 한 번 더 시도해주세요.")


@app.post("/api/onboard/complete")
def onboard_complete(req: OnboardRequest, user: str = Depends(current_user)):
    onboard.complete(user, req.companion, req.messages, req.first_memory)
    return {"ok": True, "id": req.companion.id}


class PreviewRequest(BaseModel):
    companion: Companion
    messages: list[dict]


@app.post("/api/preview")
def preview(req: PreviewRequest, request: Request,
            user: str = Depends(current_user)):
    _llm_rate_limit(request, user)
    return _sse(orchestrator.preview_stream(user, req.companion, req.messages))


@app.get("/api/config")
def get_config(user: str = Depends(current_user)):
    p = get_provider()
    return {"provider": p.name, "model": p.model,
            "sovits_available": bool(config.SOVITS_URL)}


# ---------- voice (P1) ----------

@app.get("/api/voices")
def list_voices(engine: str = "edge", user: str = Depends(current_user)):
    try:
        return tts.get_engine(engine).voices()
    except ValueError as e:
        raise HTTPException(400, str(e))


async def _synthesize(voice: Voice, text: str, user: str = "",
                      companion_id: str | None = None) -> Response:
    if not voice.engine:
        raise HTTPException(400, "이 컴패니언에는 목소리가 설정되지 않았습니다")
    if user:
        try:
            billing.check_tts_quota(user, engine=voice.engine)
        except billing.QuotaExceeded as e:
            raise HTTPException(402, str(e))
    try:
        audio, mime = await tts.get_engine(voice.engine).synthesize(text, voice)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    if not audio:
        raise HTTPException(422, "합성할 텍스트가 없습니다")
    if user:
        db.add_usage(user, companion_id, "tts", provider=voice.engine,
                     model=voice.model or "", tts_chars=len(text),
                     audio_bytes=len(audio))
    return Response(content=audio, media_type=mime,
                    headers={"Cache-Control": "no-store"})


class TTSRequest(BaseModel):
    text: str


@app.post("/api/tts/{companion_id}")
async def synthesize(companion_id: str, req: TTSRequest, request: Request,
                     user: str = Depends(current_user)):
    _llm_rate_limit(request, user)
    try:
        companion = store.load(user, companion_id)
    except FileNotFoundError:
        raise HTTPException(404, "companion not found")
    return await _synthesize(companion.voice, req.text, user, companion_id)


# ---------- 기억 열람·정정 (데이터 소유 원칙의 실체화) ----------

@app.get("/api/companions/{companion_id}/memories")
def list_memories(companion_id: str, user: str = Depends(current_user)):
    return db.all_memories(user, companion_id)


class MemoryUpdate(BaseModel):
    content: str


@app.put("/api/memories/{memory_id}")
def edit_memory(memory_id: int, req: MemoryUpdate,
                user: str = Depends(current_user)):
    if not req.content.strip():
        raise HTTPException(400, "내용이 비어 있습니다 (삭제는 DELETE로)")
    if not db.update_memory(user, memory_id, req.content.strip()):
        raise HTTPException(404, "memory not found")
    return {"ok": True}


@app.delete("/api/memories/{memory_id}")
def remove_memory(memory_id: int, user: str = Depends(current_user)):
    if not db.delete_memory(user, memory_id):
        raise HTTPException(404, "memory not found")
    return {"ok": True}


# ---------- 과금 (티어·쿼터 — IAP 연동 전 골격) ----------

@app.get("/api/billing")
def billing_status(user: str = Depends(current_user)):
    return billing.status(user)


class TierChange(BaseModel):
    tier: str


@app.put("/api/billing/tier")
def billing_set_tier(req: TierChange, user: str = Depends(current_user)):
    """IAP 연동 전 개발용 — 제품 모드에서는 영수증 검증이 이 자리를 대체한다."""
    if not billing.is_metered(user):
        raise HTTPException(400, "셀프호스팅 오너는 과금 대상이 아닙니다")
    try:
        billing.set_tier(user, req.tier)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return billing.status(user)


@app.post("/api/admin/unsuspend/{account_id}")
def admin_unsuspend(account_id: int, user: str = Depends(current_user)):
    """정지 해제 — 셀프호스팅 오너(운영자)만. 자동 정지는 되돌릴 수 있어야 한다."""
    if user != config.DEFAULT_USER:
        raise HTTPException(403, "권한이 없습니다")
    safety.unsuspend(f"u{account_id}")
    return {"ok": True}


@app.get("/api/usage")
def usage(days: int = 30, user: str = Depends(current_user)):
    """기간 내 사용량 합계 — 단위 경제 계산용 (kind·provider·model별)."""
    return db.usage_summary(user, days=days)


class TTSPreviewRequest(BaseModel):
    voice: Voice
    text: str = "안녕, 내 목소리 어때? 마음에 들었으면 좋겠다."


@app.post("/api/tts-preview")
async def tts_preview(req: TTSPreviewRequest, user: str = Depends(current_user)):
    """빌더 미리듣기 — 저장 전 보이스 설정으로 합성."""
    return await _synthesize(req.voice, req.text, user)


@app.post("/api/companions/{companion_id}/voice-ref")
async def upload_voice_ref(companion_id: str, file: UploadFile,
                           user: str = Depends(current_user)):
    """보이스 클로닝용 참조 오디오 업로드.

    자동 보정: 32kHz mono WAV 표준화, 10초 초과분 잘라내기(GPT-SoVITS 제약 3~10초),
    참조 대사(ref_text)가 비어 있으면 whisper로 자동 인식해 채운다.
    """
    from . import audio_tools
    from .voice import stt as voice_stt

    try:
        companion = store.load(user, companion_id)
    except FileNotFoundError:
        raise HTTPException(404, "companion not found — 먼저 저장한 뒤 업로드하세요")
    ext = (file.filename or "ref.wav").rsplit(".", 1)[-1].lower()
    if ext not in ("wav", "mp3", "m4a", "flac", "ogg"):
        raise HTTPException(400, "wav/mp3/m4a/flac/ogg 파일만 지원합니다")
    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(400, "파일이 너무 큽니다 (30MB 제한)")

    user_dir = config.VOICES_DIR / user
    user_dir.mkdir(parents=True, exist_ok=True)
    raw = user_dir / f"{companion_id}.upload.{ext}"
    raw.write_bytes(data)

    trimmed = False
    duration = audio_tools.probe_duration(raw)
    if duration is not None and duration < 3.0:
        raw.unlink(missing_ok=True)
        raise HTTPException(400, f"참조 오디오가 너무 짧습니다 ({duration:.1f}초 — 3초 이상 필요)")

    rel = f"{user}/{companion_id}.wav"
    dest = config.VOICES_DIR / rel
    max_s = 9.5 if (duration is None or duration > 10.0) else None
    if audio_tools.convert_to_wav(raw, dest, max_seconds=max_s):
        trimmed = bool(max_s and duration and duration > 10.0)
        raw.unlink(missing_ok=True)
    else:
        # ffmpeg 부재 시 원본 그대로 (합성 시점에 워커가 검사)
        rel = f"{user}/{companion_id}.{ext}"
        raw.rename(config.VOICES_DIR / rel)
        dest = config.VOICES_DIR / rel

    # 참조 대사 자동 인식 (비어 있을 때만 — 사용자가 쓴 값은 존중)
    auto_ref_text = ""
    if not companion.voice.ref_text:
        pcm = audio_tools.to_pcm16k(dest)
        if pcm:
            try:
                auto_ref_text = await voice_stt.transcribe(pcm)
            except Exception:
                auto_ref_text = ""  # STT 실패는 업로드를 막지 않는다
            if auto_ref_text:
                companion.voice.ref_text = auto_ref_text

    companion.voice.reference_audio = rel
    store.save(user, companion)
    final_duration = audio_tools.probe_duration(dest)
    return {"ok": True, "reference_audio": rel, "trimmed": trimmed,
            "duration": final_duration, "ref_text": companion.voice.ref_text}


# ---------- voice call (P2) ----------
# 프로토콜: docs/voice-protocol.md — P4 네이티브 앱이 재사용하는 계약

@app.websocket("/api/ws/voice/{companion_id}")
async def voice_call(ws: WebSocket, companion_id: str):
    from .voice.pipeline import VoiceSession

    await ws.accept()
    # 브라우저 WS는 Authorization 헤더를 못 쓴다 → 첫 '텍스트' 메시지로 인증.
    # 마이크 워크릿이 auth보다 먼저 바이너리를 밀어 넣는 레이스가 있으므로,
    # 인증 전 도착한 바이너리 프레임은 버리고 텍스트를 기다린다.
    if config.AUTH_TOKEN:
        async def first_text(timeout: float = 5.0) -> str:
            loop_deadline = asyncio.get_running_loop().time() + timeout
            while True:
                remain = loop_deadline - asyncio.get_running_loop().time()
                msg = await asyncio.wait_for(ws.receive(), timeout=max(remain, 0.1))
                if msg["type"] == "websocket.disconnect":
                    raise ConnectionError()
                if msg.get("text"):
                    return msg["text"]
                # 바이너리(마이크 프레임)는 인증 전이므로 폐기

        user = None
        try:
            first = json.loads(await first_text())
            if first.get("type") == "auth":
                user = _resolve_user(str(first.get("token", "")))
        except Exception:
            user = None
        if not user:
            await ws.close(code=4401, reason="unauthorized")
            return
    else:
        user = config.DEFAULT_USER
    try:
        companion = store.load(user, companion_id)
    except FileNotFoundError:
        await ws.close(code=4404, reason="companion not found")
        return
    session = VoiceSession(ws, user, companion)
    try:
        await session.run()
    except WebSocketDisconnect:
        pass


# ---------- static web ----------

@app.get("/")
def index():
    return FileResponse(config.WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")


def run():
    uvicorn.run(app, host="0.0.0.0", port=8787)


if __name__ == "__main__":
    run()
