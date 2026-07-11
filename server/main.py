import asyncio
import json
import secrets

import uvicorn
from fastapi import (Depends, FastAPI, Header, HTTPException, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config, tts
from .chat import orchestrator
from .companion import card_import, store, templates
from .companion.schema import Companion, Voice
from .llm import get_provider
from .memory import db

app = FastAPI(title="Inanna")
db.init()


@app.middleware("http")
async def static_no_cache(request, call_next):
    """폰 브라우저(PWA)가 옛 JS를 캐시해 신구 코드가 섞이는 사고 방지.
    no-cache = 매번 재검증 (ETag 304라 비용은 미미)."""
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
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

class Credentials(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
def auth_register(req: Credentials):
    try:
        token = auth.register(req.email, req.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"token": token}


@app.post("/api/auth/login")
def auth_login(req: Credentials):
    token = auth.login(req.email, req.password)
    if not token:
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다")
    return {"token": token}


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


def _sse(gen):
    def event_stream():
        try:
            for delta in gen:
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/chat/{companion_id}")
def chat(companion_id: str, req: ChatRequest, user: str = Depends(current_user)):
    try:
        companion = store.load(user, companion_id)
    except FileNotFoundError:
        raise HTTPException(404, "companion not found")
    session_id, _ = orchestrator.ensure_session(user, companion)
    return _sse(orchestrator.chat_stream(user, companion, session_id, req.message))


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
    return {"messages": rows}


class PreviewRequest(BaseModel):
    companion: Companion
    messages: list[dict]


@app.post("/api/preview")
def preview(req: PreviewRequest, user: str = Depends(current_user)):
    return _sse(orchestrator.preview_stream(req.companion, req.messages))


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
async def synthesize(companion_id: str, req: TTSRequest,
                     user: str = Depends(current_user)):
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
    return await _synthesize(req.voice, req.text)


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
