#!/bin/bash
# Inanna 데이터 백업 — 관계 데이터의 내구성이 이 서비스의 신뢰 그 자체다.
#
# 대상: DB(온라인 정합 스냅샷) + companions/ + voices/ + .env
# 보관: 로컬($HOME/Backups/inanna) + iCloud Drive(오프머신) 이중, 각 30개 로테이션
# 주기: launchd(com.inanna.backup)가 매일 04:30 실행 (놓치면 다음 웨이크 때)
# 복원: tar -xzf <백업.tar.gz> -C <임시폴더> 후 inanna.db·companions·voices를
#       레포 루트에 되돌리고 서버 재시작. (env 파일은 .env로 이름 변경)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${INANNA_BACKUP_DIR:-$HOME/Backups/inanna}"
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs/InannaBackups"
STAMP=$(date +%Y%m%d-%H%M%S)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$DEST"
# 서버가 쓰는 중에도 정합성이 보장되는 SQLite 온라인 백업 (cp는 WAL 중간을 뜰 수 있다)
sqlite3 "$ROOT/inanna.db" ".backup '$TMP/inanna.db'"
cp -R "$ROOT/companions" "$TMP/companions" 2>/dev/null || true
cp -R "$ROOT/voices" "$TMP/voices" 2>/dev/null || true
cp "$ROOT/.env" "$TMP/env" 2>/dev/null || true   # 복원 시 .env로 되돌릴 것

tar -czf "$DEST/inanna-$STAMP.tar.gz" -C "$TMP" .

# 오프머신 사본 — 맥이 통째로 죽어도 iCloud에 남는다.
# launchd 컨텍스트에선 TCC가 iCloud 접근을 막을 수 있어 best-effort로:
# 실패해도 로컬 백업은 유효하므로 경고만 남기고 계속한다.
# (경고가 계속 보이면: 시스템 설정 → 개인정보 보호 → 전체 디스크 접근에 bash 추가)
if mkdir -p "$ICLOUD" 2>/dev/null && cp "$DEST/inanna-$STAMP.tar.gz" "$ICLOUD/" 2>/dev/null; then
  :
else
  echo "[backup] 경고: iCloud 사본 실패 — 로컬 백업만 남음"
fi

# 로테이션: 양쪽 모두 최신 30개만 (접근 불가한 쪽은 건너뜀)
for d in "$DEST" "$ICLOUD"; do
  [ -d "$d" ] || continue
  { ls -t "$d"/inanna-*.tar.gz 2>/dev/null || true; } | tail -n +31 | while IFS= read -r f; do
    rm -f "$f"
  done
done

echo "[backup] $STAMP → $DEST ($(du -h "$DEST/inanna-$STAMP.tar.gz" | cut -f1))"
