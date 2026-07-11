"""실시간 음성 대화 세션 — 상태머신, STT→LLM→TTS 파이프라인, 인터럽트.

프로토콜 스펙: docs/voice-protocol.md (P4 네이티브 앱이 재사용하는 계약)
상태: idle → listening → thinking → speaking → idle (서버 권위)
half-duplex: thinking/speaking 중 수신 오디오는 폐기한다 (클라이언트도 송신 중단).
"""
import asyncio
import json
import re
import threading
import time

from fastapi import WebSocket

from .. import config
from ..chat import orchestrator
from ..companion.schema import Companion
from ..memory import db
from ..tts import get_engine
from ..tts.base import clean_for_tts, strip_audio_tags
from . import stt
from .vad import UtteranceDetector

VOICE_HINT = (
    "지금은 음성 통화 중이다. 글이 아니라 말로 들린다 — 짧은 문장 위주로 말하고, "
    "첫 문장은 특히 짧게 먼저 반응해라. 이모티콘이나 ㅋㅋ 같은 문자 웃음 대신 "
    "말로 웃어라 (하하, 헤헤 같은)."
)
# 감정 연기 지원 음성(ElevenLabs v3)일 때만 추가 — LLM이 직접 오디오 태그로 연기
V3_TAG_HINT = (
    " 네 말은 감정을 연기하는 음성으로 합성된다. 대괄호 오디오 태그를 문장 속 "
    "자연스러운 위치에 넣으면 실제 소리로 연기된다: [laughs] [giggles] [sighs] "
    "[whispers] [excited] [curious] [playful] 등. 태그는 영어로, 아껴서 써라 "
    "(턴당 0~2개, 감정이 실릴 때만). 태그는 소리로만 표현되고 상대에게 글로 "
    "보이지 않는다."
)

_SENT_BOUNDARY = re.compile(r"[.!?…~\n]+[\"')\]]*\s*")


def pop_sentences(buf: str) -> tuple[list[str], str]:
    """완결된 문장들과 잔여 버퍼를 분리."""
    out, start = [], 0
    for m in _SENT_BOUNDARY.finditer(buf):
        seg = buf[start:m.end()].strip()
        if len(seg) >= 2:
            out.append(seg)
        start = m.end()
    return out, buf[start:]


class VoiceSession:
    def __init__(self, ws: WebSocket, user_id: str, companion: Companion):
        self.ws = ws
        self.user_id = user_id
        self.companion = companion
        self.session_id, _ = orchestrator.ensure_session(user_id, companion)
        self.detector = UtteranceDetector()
        self.state = "idle"
        self.turn_task: asyncio.Task | None = None
        self.audio_seq = 0
        self._engine = get_engine(companion.voice.engine) if companion.voice.engine else None
        # 병렬 합성 상한 — 클라우드 엔진만 동시 요청 (sovits는 CPU라 순차가 빠름)
        self._tts_sem = asyncio.Semaphore(
            getattr(self._engine, "concurrency", 1) if self._engine else 1)
        # 진단용 — 실기기 이슈(마이크 레벨/VAD 미트리거)를 로그로 확인
        self._diag_frames = 0
        self._diag_rms_sum = 0.0
        self._diag_dropped = 0
        # playback_end 유실(클라 디코드 실패 등)로 speaking에 고착되는 것 방지
        self._speak_watchdog: asyncio.Task | None = None
        # 투기적 STT — 발화 중 침묵이 시작되면 종료 확정(end_ms) 전에 미리
        # 인식을 돌려, 침묵 대기와 STT를 겹친다 (응답 지연 단축)
        self._spec_task: asyncio.Task | None = None
        self._spec_voiced = -1

    # ---------- 송신 ----------

    async def send_event(self, **obj) -> None:
        await self.ws.send_text(json.dumps(obj, ensure_ascii=False))

    async def set_state(self, value: str) -> None:
        self.state = value
        await self.send_event(type="state", value=value)

    # ---------- 메인 루프 ----------

    async def _warmup(self) -> None:
        """SoVITS 콜드 스타트 완화 — 통화 시작 직후 더미 합성으로 모델 캐시 예열."""
        try:
            await self._engine.synthesize("음, 그래.", self.companion.voice)
        except Exception:
            pass

    async def run(self) -> None:
        await self.send_event(
            type="ready", session_id=self.session_id,
            voice_engine=self.companion.voice.engine,
        )
        if self.companion.voice.engine == "sovits":
            asyncio.create_task(self._warmup())
        await self.set_state("idle")
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await self._on_audio(msg["bytes"])
                elif msg.get("text"):
                    await self._on_event(json.loads(msg["text"]))
        finally:
            await self._cancel_turn(notify=False)

    def _diag(self, chunk: bytes, dropped: bool) -> None:
        from .vad import _rms
        self._diag_frames += 1
        if dropped:
            self._diag_dropped += 1
        else:
            self._diag_rms_sum += _rms(chunk)
        if self._diag_frames >= 50:  # 100ms 청크 기준 ~5초 창
            fed = self._diag_frames - self._diag_dropped
            avg = self._diag_rms_sum / max(fed, 1)
            print(f"[voice {self.companion.id}] state={self.state} "
                  f"recv={self._diag_frames}f dropped={self._diag_dropped} "
                  f"rms_avg={avg:.0f} floor={self.detector._floor:.0f} "
                  f"thr={self.detector.start_threshold:.0f} "
                  f"speaking={self.detector.speaking}", flush=True)
            self._diag_frames = self._diag_dropped = 0
            self._diag_rms_sum = 0.0

    async def _on_audio(self, chunk: bytes) -> None:
        if self.state not in ("idle", "listening"):
            self._diag(chunk, dropped=True)
            return  # half-duplex 서버측 게이트
        self._diag(chunk, dropped=False)
        utterance = self.detector.feed(chunk)
        if self.detector.speaking and self.state == "idle":
            await self.set_state("listening")
        elif not self.detector.speaking and self.state == "listening" and utterance is None:
            # 짧은 잡음으로 시작됐다 취소된 경우
            await self.set_state("idle")
        if utterance is None:
            if self.detector.speaking:
                self._maybe_spec_stt()
            return
        # 이 멈춤에서 미리 돌린 STT가 있고 이후 새 말이 없었으면 그 결과를 쓴다
        spec, self._spec_task = self._spec_task, None
        if spec is not None and self._spec_voiced != self.detector.voiced_total:
            spec.cancel()  # 멈춤 뒤에 말이 이어졌다 — 무효
            spec = None
        # 상태 전환을 태스크 시작 전에 동기적으로 — 안 그러면 태스크가 뜨기 전
        # 도착한 청크가 VAD로 들어가 발화가 쪼개진다 (half-duplex 게이트 무력화)
        await self.set_state("thinking")
        self.turn_task = asyncio.create_task(self._handle_utterance(utterance, spec))

    def _maybe_spec_stt(self) -> None:
        d = self.detector
        if d.pause_ms < 300:
            return
        if self._spec_task is not None and self._spec_voiced == d.voiced_total:
            return  # 이 멈춤에 대해선 이미 시작함
        if self._spec_task is not None and not self._spec_task.done():
            self._spec_task.cancel()  # 이전 멈춤의 것 — 폐기
        self._spec_voiced = d.voiced_total
        self._spec_task = asyncio.create_task(stt.transcribe(d.snapshot()))

    def _arm_watchdog(self, seconds: float = 60.0) -> None:
        self._disarm_watchdog()

        async def watch():
            await asyncio.sleep(seconds)
            if self.state == "speaking":
                print(f"[voice {self.companion.id}] watchdog: playback_end 미수신 → idle 복귀",
                      flush=True)
                self.detector.reset()
                await self.set_state("idle")

        self._speak_watchdog = asyncio.create_task(watch())

    def _disarm_watchdog(self) -> None:
        if self._speak_watchdog and not self._speak_watchdog.done():
            self._speak_watchdog.cancel()
        self._speak_watchdog = None

    async def _on_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "interrupt":
            await self._cancel_turn(notify=True)
        elif etype == "playback_end":
            self._disarm_watchdog()
            if self.state == "speaking":
                await self.set_state("idle")
        elif etype == "client_log":
            # 폰 브라우저 콘솔을 볼 수 없어 클라이언트가 보내는 원격 진단
            print(f"[voice {self.companion.id}] client: {event.get('message', '')}",
                  flush=True)

    async def _cancel_turn(self, notify: bool) -> None:
        self._disarm_watchdog()
        if self._spec_task and not self._spec_task.done():
            self._spec_task.cancel()
        self._spec_task = None
        task, self.turn_task = self.turn_task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.detector.reset()
        if notify:
            await self.send_event(type="interrupted")
            await self.set_state("idle")

    # ---------- 턴 처리 ----------

    async def _handle_utterance(self, pcm: bytes,
                                spec: asyncio.Task | None = None) -> None:
        try:
            text = None
            if spec is not None:
                try:
                    text = await spec  # 침묵 대기 동안 이미 (거의) 끝나 있다
                except asyncio.CancelledError:
                    raise
                except Exception:
                    spec = None  # 투기 실패 — 전체 오디오로 폴백
            if text is None:
                text = await stt.transcribe(pcm)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self.send_event(type="error", message=f"음성 인식 실패: {e}")
            await self.set_state("idle")
            return
        print(f"[voice {self.companion.id}] utterance {len(pcm) / 32000:.1f}s "
              f"spec={'hit' if spec else 'miss'} → stt: {text!r}", flush=True)
        if not stt.is_valid(text):
            await self.set_state("idle")
            return
        await self.send_event(type="stt", text=text)
        await self._respond(text)

    async def _respond(self, user_text: str) -> None:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()
        acc: list[str] = []
        completed = False

        hint = VOICE_HINT
        voice = self.companion.voice
        if voice.engine == "elevenlabs" and "v3" in (voice.model or config.ELEVENLABS_MODEL):
            hint += V3_TAG_HINT

        def worker():
            try:
                gen = orchestrator.chat_stream(
                    self.user_id, self.companion, self.session_id,
                    user_text, extra_context=hint,
                )
                for delta in gen:
                    if stop.is_set():
                        gen.close()  # 응답 저장 생략됨 — 호출측에서 부분 저장
                        return
                    loop.call_soon_threadsafe(queue.put_nowait, delta)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
                return
            loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        pending = ""
        speak_buf = ""    # 엔진별 최소 길이까지 문장을 묶는 버퍼 (톤 튐 방지)
        spoken = ""       # 이번 턴에서 이미 말한 텍스트 — 운율 맥락(prev_text)
        min_chars = getattr(self._engine, "chunk_min_chars", 0) if self._engine else 0
        n_chunks = 0

        # 병렬 합성 + 순서 보장 송신 — prev_text는 '텍스트'라 청크 N의 합성이
        # 끝나기 전에도 N+1 합성을 시작할 수 있다. 청크가 확정되는 즉시 합성
        # 태스크를 띄우고, 송신 루프가 완성 순서와 무관하게 원래 순서로 보낸다.
        # (문장 사이 공백의 주범이던 '재생 끝난 뒤에야 다음 합성 시작'을 제거)
        send_q: asyncio.Queue = asyncio.Queue()
        synth_tasks: list[asyncio.Task] = []
        sent_audio = False

        async def send_loop() -> None:
            nonlocal sent_audio
            while True:
                task = await send_q.get()
                if task is None:
                    return
                audio, mime, text = await task
                if not audio:
                    continue
                if self.state != "speaking":
                    await self.set_state("speaking")
                self.audio_seq += 1
                await self.send_event(type="audio", seq=self.audio_seq,
                                      mime=mime, text=text)
                await self.ws.send_bytes(audio)
                sent_audio = True

        sender = asyncio.create_task(send_loop())

        def flush_speak(force: bool = False) -> None:
            nonlocal speak_buf, spoken, n_chunks
            if not speak_buf.strip():
                return
            # 묶음 크기 램프: 첫 청크(최소 6자 — "어?" 솔로 방지) → 절반 → 전체.
            # 첫 오디오가 짧아서 다음 청크의 LLM 스트리밍+합성을 못 가리는
            # 공백을 줄인다. (톤 연속성은 prev_text stitching이 담당)
            need = (6, min_chars // 2)[n_chunks] if n_chunks < 2 else min_chars
            if not force and len(speak_buf) < need:
                return
            chunk = speak_buf.strip()
            speak_buf = ""
            n_chunks += 1
            task = asyncio.create_task(self._synth(chunk, prev_text=spoken))
            synth_tasks.append(task)
            send_q.put_nowait(task)
            spoken = (spoken + " " + chunk).strip()

        try:
            while True:
                item = await queue.get()
                if item is None:
                    completed = True
                    break
                if isinstance(item, Exception):
                    raise item
                acc.append(item)
                await self.send_event(type="text", delta=item)
                pending += item
                sentences, pending = pop_sentences(pending)
                for sentence in sentences:
                    speak_buf = (speak_buf + " " + sentence).strip() if speak_buf else sentence
                    flush_speak()
            # 잔여 플러시
            if pending.strip():
                speak_buf = (speak_buf + " " + pending.strip()).strip()
            flush_speak(force=True)
            send_q.put_nowait(None)
            await sender  # 마지막 청크까지 송신 완료
            await self.send_event(type="turn_end")
            if sent_audio:
                self._arm_watchdog()
            else:
                # 낼 오디오가 없으면 재생 대기 없이 바로 청취 복귀
                await self.set_state("idle")
        except asyncio.CancelledError:
            stop.set()
            if not completed:
                partial = strip_audio_tags("".join(acc).strip())
                if partial:
                    db.add_message(self.session_id, "assistant", partial)
            raise
        except Exception as e:
            stop.set()
            await self.send_event(type="error", message=str(e))
            await self.set_state("idle")
        finally:
            if not sender.done():
                sender.cancel()
            for task in synth_tasks:
                if not task.done():
                    task.cancel()

    async def _synth(self, sentence: str, prev_text: str = "") -> tuple[bytes, str, str]:
        """문장(묶음) 하나 합성. (오디오, MIME, 원문) — 실패/스킵이면 오디오 b""."""
        if self._engine is None or not clean_for_tts(sentence):
            return b"", "", sentence  # ㅋㅋ만 있는 문장 등 — 자막은 이미 나갔다
        try:
            t0 = time.monotonic()
            async with self._tts_sem:
                audio, mime = await self._engine.synthesize(
                    sentence, self.companion.voice, prev_text=prev_text)
            print(f"[voice {self.companion.id}] tts {len(sentence)}자 → "
                  f"{len(audio) // 1024}KB {time.monotonic() - t0:.1f}s", flush=True)
            db.add_usage(self.user_id, self.companion.id, "tts",
                         provider=self._engine.name,
                         model=self.companion.voice.model or "",
                         tts_chars=len(sentence), audio_bytes=len(audio))
            return audio, mime, sentence
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self.send_event(type="error", message=f"음성 합성 실패: {e}")
            return b"", "", sentence
