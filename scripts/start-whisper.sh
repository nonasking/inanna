#!/bin/bash
# whisper.cpp STT 상주 서버 (실시간 음성 대화용)
# 사용: bash scripts/start-whisper.sh  → http://127.0.0.1:9881/inference
set -e
MODEL="${WHISPER_MODEL:-$HOME/dev/models/ggml-large-v3-turbo-q5_0.bin}"
exec /opt/homebrew/bin/whisper-server \
  -m "$MODEL" -l ko --host 127.0.0.1 --port 9881 \
  --no-timestamps -sns
