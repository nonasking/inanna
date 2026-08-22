#!/bin/bash
# Inanna 서버 데이터 백업 (리눅스판) — cron이 매일 04:30 실행.
# 대상: DB(온라인 정합 스냅샷) + companions/ + voices/ + .env
# 보관: 로컬 30일 로테이션. 오프사이트는 아래 rclone 블록 주석 해제 시.
# 복원: tar -xzf <백업> -C /tmp/restore 후 파일을 /home/inanna/data 로 되돌리고
#       sudo systemctl restart inanna
set -euo pipefail
DATA=/home/inanna/data
ENV=/home/inanna/inanna/.env
DEST=/home/inanna/backups
STAMP=$(date +%Y%m%d-%H%M%S)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DEST"

# 서버가 쓰는 중에도 정합성이 보장되는 SQLite 온라인 백업
sqlite3 "$DATA/inanna.db" ".backup '$TMP/inanna.db'"
cp -R "$DATA/companions" "$TMP/companions" 2>/dev/null || true
cp -R "$DATA/voices" "$TMP/voices" 2>/dev/null || true
cp "$ENV" "$TMP/env" 2>/dev/null || true

tar -czf "$DEST/inanna-$STAMP.tar.gz" -C "$TMP" .
ls -t "$DEST"/inanna-*.tar.gz | tail -n +31 | xargs -r rm -f

# ── 오프사이트 사본(권장) ── rclone 설정 후 주석 해제:
# rclone copy "$DEST/inanna-$STAMP.tar.gz" remote:inanna-backups/ 2>/dev/null || true

echo "[backup] $STAMP → $DEST ($(du -h "$DEST/inanna-$STAMP.tar.gz" | cut -f1))"
