#!/bin/bash
# QA 스모크 — 상용화 준비 기간의 회귀 방지 게이트.
#
# 사용:
#   bash scripts/qa.sh          # 유닛(무료·서버 불필요) + 음성 e2e(로컬 서비스)
#   bash scripts/qa.sh --llm    # + LLM 품질 게이트 (API 토큰 비용 발생)
#
# 토큰은 .env의 INANNA_AUTH_TOKEN을 읽는다.
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
TOKEN=$(grep '^INANNA_AUTH_TOKEN=' .env 2>/dev/null | cut -d= -f2)

echo "════ 1/3 유닛 스모크 (무료)"
$PY tests/unit.py

echo
echo "════ 2/3 음성 e2e (로컬 서버·whisper·sovits 필요)"
if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8787/; then
  $PY tests/voice_e2e.py --token "$TOKEN"
else
  echo "  ⏭ 서버(:8787)가 없어 건너뜀 — launchctl kickstart gui/$(id -u)/com.inanna.server"
fi

echo
if [[ "$1" == "--llm" ]]; then
  echo "════ 3/3 LLM 품질 게이트 (API 비용 발생)"
  $PY tests/quality_gates.py --token "$TOKEN"
else
  echo "════ 3/3 LLM 품질 게이트 — 건너뜀 (--llm 플래그로 실행)"
fi

echo
echo "QA 완료"
