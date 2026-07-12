"""통화 소크 테스트 — 한 WS 연결로 다턴 + 반복 barge에서 상태가 안 꼬이는지.

각 턴이 idle로 복귀하는지, barge 후에도 다음 턴이 정상인지, 서버가
행업 없이 N턴을 완주하는지 본다.

사용: .venv/bin/python tests/soak.py --token TOKEN [--turns 6]
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voice_e2e import SILENCE_1S, connect, make_pcm, send_pcm  # noqa: E402

UTTERANCES = [
    "유나야 오늘 뭐 했어?",
    "재밌었겠다, 나는 일하느라 바빴어.",
    "저녁은 뭐 먹을까 고민 중이야.",
    "주말에 같이 게임할까?",
    "요즘 날씨가 많이 더워졌지?",
    "이제 자야겠다, 내일 또 얘기하자.",
]


async def run_turn(ws, pcm, barge_pcm=None, timeout=180):
    """한 턴: 발화 → (선택) 재생 중 barge → idle 복귀까지. 이벤트 목록 반환."""
    await send_pcm(ws, pcm)
    await send_pcm(ws, SILENCE_1S)
    events, turn_ended, barged = [], False, False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
        if isinstance(msg, bytes):
            if barge_pcm is not None and not barged:
                barged = True
                await send_pcm(ws, barge_pcm, realtime=True)
                await send_pcm(ws, SILENCE_1S, realtime=True)
            continue
        ev = json.loads(msg)
        events.append(ev["type"])
        if ev["type"] == "error":
            raise AssertionError(f"서버 에러: {ev.get('message')}")
        if ev["type"] == "turn_end":
            turn_ended = True
            await ws.send(json.dumps({"type": "playback_end"}))
        if ev["type"] == "interrupted" and barge_pcm is not None:
            # barge 성공 — 이어지는 새 턴(끼어든 발화)의 완료를 기다린다
            barge_pcm = None
        if turn_ended and ev["type"] == "state" and ev["value"] == "idle":
            return events
    raise AssertionError(f"턴이 {timeout}s 안에 idle로 복귀하지 않음: {events[-8:]}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--companion", default="test-yuna")
    ap.add_argument("--host", default="127.0.0.1:8787")
    ap.add_argument("--turns", type=int, default=6)
    args = ap.parse_args()
    url = f"ws://{args.host}/api/ws/voice/{args.companion}"

    print(f"── 소크: 단일 연결 {args.turns}턴 (3번째 턴은 barge 포함)")
    barge = make_pcm("잠깐만, 그 얘기는 나중에 하자.")
    ws, ready = await connect(url, args.token)
    await asyncio.sleep(3)
    await send_pcm(ws, SILENCE_1S)

    t0 = time.monotonic()
    for i in range(args.turns):
        pcm = make_pcm(UTTERANCES[i % len(UTTERANCES)])
        events = await run_turn(ws, pcm, barge_pcm=barge if i == 2 else None)
        stt_n = events.count("stt")
        print(f"  턴 {i + 1}/{args.turns} ✅ (stt {stt_n}, "
              f"{'barge ' if i == 2 else ''}이벤트 {len(events)})")
    await ws.close()
    print(f"  ✅ {args.turns}턴 완주, 총 {time.monotonic() - t0:.0f}s — 상태 고착·행업 없음")


if __name__ == "__main__":
    asyncio.run(main())
