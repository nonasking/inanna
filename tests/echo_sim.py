"""barge-in 에코 오탐 시뮬레이션 — AEC 잔향이 끼어들기를 오발시키지 않는지.

실기기에서 AEC(echoCancellation/.voiceChat)가 스피커 출력을 지우고 남기는
잔향은 원음의 일부 수준이다. 컴패니언풍 목소리를 감쇠시켜 speaking 중에
되먹여 보고, interrupted가 발생하면 오탐이다.

사용: .venv/bin/python tests/echo_sim.py --token TOKEN [--level 0.3]
  --level: 잔향 진폭 배율 (실제 AEC 잔향 상한 ≈ 0.1 — 실측 근거는 vad.make_barge_detector 주석)
"""
import argparse
import array
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voice_e2e import CHUNK, SILENCE_1S, connect, make_pcm, send_pcm  # noqa: E402


def attenuate(pcm: bytes, factor: float) -> bytes:
    samples = array.array("h", pcm)
    for i in range(len(samples)):
        samples[i] = int(samples[i] * factor)
    return samples.tobytes()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--companion", default="test-yuna")
    ap.add_argument("--host", default="127.0.0.1:8787")
    ap.add_argument("--level", type=float, default=0.1)
    args = ap.parse_args()
    url = f"ws://{args.host}/api/ws/voice/{args.companion}"

    print(f"── 에코 오탐 시뮬레이션 (잔향 배율 {args.level})")
    utter = make_pcm("유나야 아무 얘기나 두 문장쯤 해줘.")
    # 컴패니언풍 목소리(여성 보이스)를 '에코'로 사용
    echo = attenuate(make_pcm("오빠 오늘 하루는 어땠어? 나는 게임하면서 기다렸지.",
                              voice="ko-KR-SunHiNeural"), args.level)

    ws, _ = await connect(url, args.token)
    await asyncio.sleep(3)
    await send_pcm(ws, SILENCE_1S)
    await send_pcm(ws, utter)
    await send_pcm(ws, SILENCE_1S)

    interrupted = False
    echo_sent = False
    turn_ended = False
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        msg = await asyncio.wait_for(ws.recv(), timeout=120)
        if isinstance(msg, bytes):
            if not echo_sent:  # 재생 시작 → 에코 되먹임
                echo_sent = True
                await send_pcm(ws, echo, realtime=True)
            continue
        ev = json.loads(msg)
        if ev["type"] == "interrupted":
            interrupted = True
            break
        if ev["type"] == "turn_end":
            turn_ended = True
            await ws.send(json.dumps({"type": "playback_end"}))
        if turn_ended and ev["type"] == "state" and ev["value"] == "idle":
            break
        if ev["type"] == "error":
            print(f"  ERROR: {ev['message']}")
            sys.exit(1)
    await ws.close()

    if interrupted:
        print(f"  ❌ 오탐 — 잔향(×{args.level})이 barge-in을 트리거함. 임계 상향 필요")
        sys.exit(1)
    assert echo_sent, "에코를 보내기 전에 턴이 끝남 — 시나리오 무효"
    print(f"  ✅ 잔향(×{args.level})에 끼어들지 않음 — 턴 정상 완료")


if __name__ == "__main__":
    asyncio.run(main())
