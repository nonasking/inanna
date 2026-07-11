#!/bin/bash
# GPT-SoVITS api_v2 워커 실행 (보이스 클로닝 TTS)
# 사용: bash scripts/start-sovits.sh  → http://127.0.0.1:9880
set -e
SOVITS_DIR="${SOVITS_DIR:-$HOME/dev/GPT-SoVITS}"
# 주의: miniconda는 x86_64(Rosetta)라 사용 불가 — 네이티브 arm64 venv를 쓴다
PY="$SOVITS_DIR/.venv-mac/bin/python"
cd "$SOVITS_DIR"
# MPS 미지원 연산(대형 출력 채널)은 CPU로 폴백
export PYTORCH_ENABLE_MPS_FALLBACK=1
exec "$PY" api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/inanna_tts_infer.yaml
