"""음성 대화 WS 루프 e2e 검증 (사용자 없이 실행 가능).

시나리오: ①정상 루프+지연 측정 ②DB 저장 ③인터럽트 ④무음 ⑤인증 실패
사용: .venv/bin/python tests/voice_e2e.py [--token TOKEN] [--companion test-yuna]
"""
import argparse
import asyncio
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
CHUNK = 3200  # 100ms @ 16kHz PCM16


def make_pcm(text: str, voice="ko-KR-InJoonNeural") -> bytes:
    """Edge TTS로 '사용자 발화' PCM 생성 (남성 보이스 = 사용자 역)."""
    mp3, raw = "/tmp/e2e-user.mp3", "/tmp/e2e-user.raw"
    subprocess.run([str(ROOT / ".venv/bin/python"), "-c", (
        "import asyncio, edge_tts, sys; "
        f"asyncio.run(edge_tts.Communicate({text!r}, {voice!r}).save({mp3!r}))"
    )], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
                    "-ar", "16000", "-ac", "1", "-f", "s16le", raw], check=True)
    return Path(raw).read_bytes()


SILENCE_1S = b"\x00" * 32000


async def send_pcm(ws, pcm: bytes, realtime=False):
    for i in range(0, len(pcm), CHUNK):
        await ws.send(pcm[i:i + CHUNK])
        if realtime:
            await asyncio.sleep(0.1)


async def connect(url, token):
    ws = await websockets.connect(url, max_size=32 * 1024 * 1024)
    if token:
        await ws.send(json.dumps({"type": "auth", "token": token}))
    ready = json.loads(await ws.recv())
    assert ready["type"] == "ready", ready
    return ws, ready


async def scenario_normal(url, token, db_path):
    print("── ① 정상 루프")
    # 쉼표로 잇는 한 문장 — 마침표의 긴 쉼(>1s)은 턴을 끊고, 이어지는 문장은
    # barge-in으로 승격되어 별개 발화가 된다 (실사용에선 자연스러운 동작)
    pcm = make_pcm("유나야 안녕, 오늘 하루 어땠는지 짧게 말해 줄래?")
    ws, ready = await connect(url, token)
    print(f"  ready: session={ready['session_id']} engine={ready['voice_engine']}")

    # 실사용 패턴: 통화 시작 후 몇 초 뒤 발화 (서버 SoVITS 워밍업이 이 사이에 완료됨)
    await asyncio.sleep(3)
    await send_pcm(ws, SILENCE_1S)          # 캘리브레이션용 무음
    await send_pcm(ws, pcm)                  # 발화
    utter_end = time.monotonic()
    await send_pcm(ws, SILENCE_1S)          # 발화 종료 유도 (hangover)

    events, first_audio_at, audio_frames, stt_text = [], None, 0, None
    turn_ended = False
    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=120)
        if isinstance(msg, bytes):
            audio_frames += 1
            if first_audio_at is None:
                first_audio_at = time.monotonic()
                magic = msg[:4]
                assert magic in (b"RIFF", b"ID3\x03", b"ID3\x04") or msg[0] == 0xFF, magic
            continue
        ev = json.loads(msg)
        events.append(ev["type"])
        if ev["type"] == "stt":
            if stt_text is None:
                stt_text = ev["text"]
            print(f"  stt: {ev['text']!r}")
        if ev["type"] == "error":
            print(f"  ERROR: {ev['message']}"); sys.exit(1)
        if ev["type"] == "turn_end":
            turn_ended = True
            await ws.send(json.dumps({"type": "playback_end"}))
        if turn_ended and ev["type"] == "state" and ev["value"] == "idle":
            break

    latency = first_audio_at - utter_end if first_audio_at else None
    assert "stt" in events and "text" in events and "audio" in events, events
    assert audio_frames >= 1
    assert stt_text and "유나" in stt_text.replace(" ", "")
    print(f"  ✅ audio {audio_frames}프레임, 발화종료→첫오디오 {latency:.1f}s (무음꼬리 1s 포함)")
    await ws.close()

    # ② DB 저장 확인
    print("── ② DB 저장")
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT 2").fetchall()
    con.close()
    roles = {r[0] for r in rows}
    assert roles == {"user", "assistant"}, rows
    print(f"  ✅ user/assistant 저장 확인: {rows[1][1][:30]!r} → {rows[0][1][:30]!r}")
    return latency


async def scenario_barge_in(url, token):
    print("── ③b barge-in (재생 중 말로 끼어들기)")
    pcm = make_pcm("유나야 네가 좋아하는 게임 이야기를 아주 길게 자세히 들려줘.")
    barge = make_pcm("잠깐만 유나야, 그 얘기 말고 다른 얘기 하자.")
    ws, _ = await connect(url, token)
    await send_pcm(ws, SILENCE_1S)
    await send_pcm(ws, pcm)
    await send_pcm(ws, SILENCE_1S)

    interrupted, barge_sent, barge_stt = False, False, None
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        msg = await asyncio.wait_for(ws.recv(), timeout=120)
        if isinstance(msg, bytes):
            if not barge_sent:  # 첫 오디오 = 재생 시작 → 그 위에 대고 말한다
                barge_sent = True
                await send_pcm(ws, barge, realtime=True)
                await send_pcm(ws, SILENCE_1S, realtime=True)
            continue
        ev = json.loads(msg)
        if ev["type"] == "error":
            print(f"  ERROR: {ev['message']}"); sys.exit(1)
        if ev["type"] == "interrupted":
            interrupted = True
        elif ev["type"] == "stt" and interrupted:
            barge_stt = ev["text"]
            break
    assert interrupted, "재생 중 지속 발화가 interrupted를 트리거해야 함"
    assert barge_stt, "끼어든 발화가 이어서 인식돼야 함"
    print(f"  ✅ 재생 중 발화 → 자동 인터럽트 + 이어서 인식: {barge_stt!r}")
    await ws.close()


async def scenario_interrupt(url, token):
    print("── ③ 인터럽트")
    pcm = make_pcm("유나야 네가 좋아하는 게임 이야기를 아주 길게 자세히 들려줘.")
    ws, _ = await connect(url, token)
    await send_pcm(ws, SILENCE_1S)
    await send_pcm(ws, pcm)
    await send_pcm(ws, SILENCE_1S)

    got_audio = False
    interrupted = False
    binaries_after_interrupt = 0
    sent_interrupt = False
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        msg = await asyncio.wait_for(ws.recv(), timeout=120)
        if isinstance(msg, bytes):
            if sent_interrupt and interrupted:
                binaries_after_interrupt += 1
            if not sent_interrupt:
                got_audio = True
                await ws.send(json.dumps({"type": "interrupt"}))
                sent_interrupt = True
            continue
        ev = json.loads(msg)
        if ev["type"] == "interrupted":
            interrupted = True
        if interrupted and ev["type"] == "state" and ev["value"] == "idle":
            # 취소 후 잔여 바이너리 확인을 위해 잠깐 대기
            try:
                extra = await asyncio.wait_for(ws.recv(), timeout=3)
                if isinstance(extra, bytes):
                    binaries_after_interrupt += 1
            except asyncio.TimeoutError:
                pass
            break
    assert got_audio and interrupted
    assert binaries_after_interrupt == 0, f"취소 후 바이너리 {binaries_after_interrupt}개"
    print("  ✅ 첫 오디오 후 인터럽트 → interrupted 수신, 잔여 바이너리 0")
    await ws.close()


async def scenario_silence(url, token):
    print("── ④ 무음 (트리거 없어야 함)")
    ws, _ = await connect(url, token)
    await send_pcm(ws, SILENCE_1S * 3)
    triggered = []
    try:
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            if not isinstance(msg, bytes):
                ev = json.loads(msg)
                if ev["type"] in ("stt", "text"):
                    triggered.append(ev)
    except asyncio.TimeoutError:
        pass
    assert not triggered, triggered
    print("  ✅ STT/응답 트리거 없음")
    await ws.close()


async def scenario_auth(url):
    print("── ⑤ 인증")
    for token in (None, "wrong-token"):
        try:
            ws = await websockets.connect(url)
            if token:
                await ws.send(json.dumps({"type": "auth", "token": token}))
            await asyncio.wait_for(ws.recv(), timeout=8)
            print("  ❌ 인증 없이 통과됨"); sys.exit(1)
        except websockets.exceptions.ConnectionClosed as e:
            assert e.rcvd and e.rcvd.code == 4401, e
    print("  ✅ 무토큰/오토큰 → 4401 종료")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default="")
    ap.add_argument("--companion", default="test-yuna")
    ap.add_argument("--host", default="127.0.0.1:8787")
    ap.add_argument("--db", default=str(ROOT / "inanna.db"))
    args = ap.parse_args()
    url = f"ws://{args.host}/api/ws/voice/{args.companion}"

    latency = await scenario_normal(url, args.token, args.db)
    await scenario_interrupt(url, args.token)
    await scenario_barge_in(url, args.token)
    await scenario_silence(url, args.token)
    if args.token:
        await scenario_auth(url)
    print(f"\n전체 통과 · 첫 오디오 지연 {latency:.1f}s (목표 <4s + 무음꼬리 보정)")


if __name__ == "__main__":
    asyncio.run(main())
