"""LLM 품질 게이트 — 품질 기준 #1(관계 파생)·#2(말투 유지) 자동 검증.

/api/preview 사용 → 대화·기억이 저장되지 않아 실컴패니언을 오염시키지 않는다.
API 토큰 비용이 들므로 scripts/qa.sh에서 --llm 플래그로만 실행.

사용: python tests/quality_gates.py --token <INANNA_AUTH_TOKEN> [--turns 5]
"""
import argparse
import json
import re
import sys

import httpx

HOST = "http://127.0.0.1:8787"

BASE_PERSONA = {
    "traits": {"밝음": 0.8, "장난기": 0.7},
    "speech_quirks": ["어미에 '~잖아' 자주"],
    "description": "게임을 좋아하고 티키타카를 즐긴다.",
}

TURN_PROMPTS = [
    "뭐해?", "오늘 하루 어땠어?", "요즘 재밌는 거 있어?",
    "너는 내가 왜 좋아?", "주말에 뭐 할까?", "피곤하다...",
    "밥 먹었어?", "심심해", "너 요즘 고민 있어?", "잘자",
]

# 존댓말 누출 감지 — 반말 컴패니언 응답에 나오면 안 되는 종결어미
_JONDAEMAL = re.compile(r"(습니다|세요|어요|아요|해요|예요|이에요|죠)[.!?~ ”\"']|(습니다|세요|어요|아요|해요|예요|이에요)$")


def preview(token: str, companion: dict, messages: list[dict]) -> str:
    r = httpx.post(f"{HOST}/api/preview",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"companion": companion, "messages": messages},
                   timeout=httpx.Timeout(120, connect=5))
    r.raise_for_status()
    out = []
    for line in r.text.splitlines():
        if line.startswith("data: "):
            d = json.loads(line[6:])
            if "delta" in d:
                out.append(d["delta"])
    return "".join(out)


def companion(template: str, calls_me: str, speech: str = "banmal") -> dict:
    return {"id": "qa-gate", "name": "큐나",
            "relationship": {"template": template, "calls_me": calls_me,
                             "i_call": "큐나", "speech_level": speech,
                             "intimacy": 0.7},
            "persona": BASE_PERSONA}


def gate_speech_consistency(token: str, turns: int) -> bool:
    """반말 컴패니언이 N턴 동안 존댓말로 새지 않고, 호칭을 유지하는가."""
    c = companion("friend", "민성")
    messages: list[dict] = []
    leaks, calls = 0, 0
    for i in range(turns):
        messages.append({"role": "user", "content": TURN_PROMPTS[i % len(TURN_PROMPTS)]})
        reply = preview(token, c, messages)
        messages.append({"role": "assistant", "content": reply})
        if _JONDAEMAL.search(reply):
            leaks += 1
            print(f"    ⚠ {i + 1}턴 존댓말 누출: {reply[:60]!r}")
        if "민성" in reply:
            calls += 1
    print(f"  존댓말 누출 {leaks}/{turns}턴 · 호칭 사용 {calls}/{turns}턴")
    return leaks == 0


def gate_relationship_swap(token: str) -> bool:
    """같은 페르소나에 관계만 바꿨을 때 호칭·말단계가 실제로 갈리는가."""
    lover = preview(token, companion("lover", "자기야"),
                    [{"role": "user", "content": "나 왔어! 보고싶었어?"}])
    formal = preview(token, companion("assistant", "선생님", "jondaemal"),
                     [{"role": "user", "content": "나 왔어. 오늘 일정 알려줘"}])
    ok_lover = "자기" in lover
    ok_formal = bool(_JONDAEMAL.search(formal))
    print(f"  연인 호칭('자기') {'✓' if ok_lover else '✗'}: {lover[:50]!r}")
    print(f"  비서 존댓말 {'✓' if ok_formal else '✗'}: {formal[:50]!r}")
    return ok_lover and ok_formal


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--turns", type=int, default=5)
    args = ap.parse_args()

    print("── 품질 게이트 #2: 말투 유지")
    ok1 = gate_speech_consistency(args.token, args.turns)
    print("── 품질 게이트 #1: 관계 파생")
    ok2 = gate_relationship_swap(args.token)
    if not (ok1 and ok2):
        sys.exit(1)
    print("\n품질 게이트 통과")


if __name__ == "__main__":
    main()
