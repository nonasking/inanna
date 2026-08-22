#!/bin/bash
# Inanna 서버 부트스트랩 — Ubuntu 24.04 LTS 새 인스턴스에서 한 번 실행.
# 실행 전: DOMAIN 값을 자기 도메인으로 바꾼다. (예: inanna.example.com)
#
#   sudo bash setup.sh
#
# 하는 일: 전용 유저 생성 → 패키지·Caddy 설치 → 방화벽 → 자동 보안패치 →
#          fail2ban → 레포 클론 → venv → systemd 서비스 → Caddy TLS → 백업 cron.
# 멱등(idempotent)하게 작성 — 다시 돌려도 안전. 2호기부터는 이 파일이 세팅의 전부.
set -euo pipefail

DOMAIN="${DOMAIN:-inanna.example.com}"   # ← 실행 시 DOMAIN=... 로 넘기거나 여기서 수정
REPO="https://github.com/nonasking/inanna.git"
USER=inanna
HOME_DIR=/home/$USER
APP=$HOME_DIR/inanna
DATA=$HOME_DIR/data

if [ "$DOMAIN" = "inanna.example.com" ]; then
  echo "먼저 DOMAIN을 실제 도메인으로 설정하세요:  sudo DOMAIN=inanna.내도메인.com bash setup.sh"; exit 1
fi

echo "== 1. 시스템 패키지 =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3-venv python3-pip git sqlite3 ufw fail2ban unattended-upgrades curl debian-keyring debian-archive-keyring apt-transport-https

echo "== 2. Caddy 설치 (공식 저장소) =="
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "== 3. 전용 유저 =="
id -u $USER &>/dev/null || useradd -m -s /bin/bash $USER

echo "== 4. 레포 클론 / 갱신 =="
if [ -d "$APP/.git" ]; then
  sudo -u $USER git -C "$APP" pull --ff-only
else
  sudo -u $USER git clone "$REPO" "$APP"
fi

echo "== 5. 가상환경 + 의존성 =="
sudo -u $USER python3 -m venv "$APP/.venv"
sudo -u $USER "$APP/.venv/bin/pip" install --upgrade pip -q
sudo -u $USER "$APP/.venv/bin/pip" install -r "$APP/requirements.txt" -q

echo "== 6. 데이터 디렉토리 (체크아웃 밖) =="
sudo -u $USER mkdir -p "$DATA/companions" "$DATA/voices" "$HOME_DIR/backups"
# 프리셋 컴패니언은 레포에 있으므로 그대로 쓰인다. .env 없으면 템플릿 복사(값은 직접 채움)
[ -f "$APP/.env" ] || { sudo -u $USER cp "$APP/deploy/env.example" "$APP/.env"; echo "  ⚠ $APP/.env 를 편집해 실제 키를 채우세요"; }

echo "== 7. systemd 서비스 =="
cp "$APP/deploy/inanna.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable inanna

echo "== 8. Caddy 설정 (도메인 치환) =="
sed "s/INANNA_DOMAIN/$DOMAIN/" "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
mkdir -p /var/log/caddy && chown caddy:caddy /var/log/caddy
systemctl reload caddy || systemctl restart caddy

echo "== 9. 방화벽 (SSH·HTTP·HTTPS만) =="
ufw allow OpenSSH
ufw allow 80,443/tcp
ufw --force enable

echo "== 10. 자동 보안 패치 + fail2ban =="
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now fail2ban

echo "== 11. 백업 cron (매일 04:30) =="
cp "$APP/deploy/backup.sh" "$HOME_DIR/backup.sh"; chmod +x "$HOME_DIR/backup.sh"; chown $USER:$USER "$HOME_DIR/backup.sh"
( crontab -u $USER -l 2>/dev/null | grep -v backup.sh; echo "30 4 * * * /home/$USER/backup.sh >> /home/$USER/backup.log 2>&1" ) | crontab -u $USER -

echo ""
echo "== 완료 =="
echo "  다음: 1) $APP/.env 편집 후  2) sudo systemctl start inanna"
echo "  DNS: $DOMAIN A레코드 → 이 서버 IP (전파 후 Caddy가 자동 TLS 발급)"
echo "  상태: systemctl status inanna caddy   로그: journalctl -u inanna -f"
