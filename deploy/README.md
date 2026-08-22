# Inanna 서버 배포 런북

집 맥 → AWS Lightsail(서울) 이전. 2호기부터는 [4]만 반복하면 된다.

## 준비물
- Lightsail 서울 인스턴스: **2GB($12), Ubuntu 24.04 LTS**
- 도메인 하나 (서브도메인으로 프로젝트 분리 예정)

---

## [1] Lightsail 인스턴스 생성 (콘솔에서)
1. lightsail.aws.amazon.com → **인스턴스 생성**
2. 리전: **서울(ap-northeast-2)** · 플랫폼: Linux · 블루프린트: **Ubuntu 24.04 LTS**
3. 플랜: **$12 (2GB RAM)**
4. 생성 후 **네트워킹 탭 → 고정 IP 연결**(Static IP) — 재부팅해도 IP 유지
5. 방화벽(네트워킹 탭): HTTP(80), HTTPS(443)는 기본 열림. SSH(22)도 열림. 그대로 둔다.

## [2] 도메인 DNS 연결
- 도메인 등록처(가비아·Cloudflare 등)에서 A 레코드 추가:
  `inanna.내도메인.com  →  [1]의 고정 IP`
- 전파 확인: `dig inanna.내도메인.com +short` 가 그 IP를 반환하면 됨 (수 분~수십 분)

## [3] 서버 접속
- Lightsail 콘솔의 브라우저 SSH, 또는 키 내려받아 `ssh ubuntu@고정IP`

## [4] 부트스트랩 (핵심 — 한 줄)
```bash
curl -sL https://raw.githubusercontent.com/nonasking/inanna/main/deploy/setup.sh -o setup.sh
sudo DOMAIN=inanna.내도메인.com bash setup.sh
```
→ 유저·Caddy·방화벽·자동패치·fail2ban·systemd·백업까지 자동 설정.
   (내부적으로 레포를 클론하므로 setup.sh만 받으면 나머지 deploy 파일은 함께 온다)

## [5] 시크릿 채우기
```bash
sudo -u inanna nano /home/inanna/inanna/.env     # env.example 기반, 실제 키 입력
sudo systemctl start inanna
```

## [6] 데이터 이관 (맥 → 서버)
맥에서 최신 백업을 서버로 복사하고 푼다 (아래 [7]에 자동화 명령 있음).
데이터가 1MB 미만이라 수 초.

## [7] 검증
```bash
systemctl status inanna caddy          # 둘 다 active
curl -sI https://inanna.내도메인.com/   # 200 + 유효 TLS
journalctl -u inanna -f                 # 실시간 로그
```

## [8] 마무리
- 앱/심사의 서버 주소를 새 도메인으로 교체 (처리방침 URL, 심사 데모 접속)
- 맥의 launchd 서버는 이관·검증 완료 후 정지: `launchctl bootout ...`

---

## 2호기 이후 (다른 프로젝트)
- 새 Lightsail 인스턴스 → 그 프로젝트 레포로 setup.sh 실행 → 끝.
- 또는 같은 서버에 얹기: 다른 포트로 systemd 서비스 추가 + Caddyfile에 도메인 블록 한 줄.
