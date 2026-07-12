# Inanna 서버 — 호스티드 배포용 (셀프호스팅은 그냥 uvicorn으로 충분)
# 데이터는 /data 볼륨: DB(SQLite), 컴패니언 YAML, 참조 오디오.
# TTS 워커(GPT-SoVITS/whisper)는 별도 서비스 — INANNA_SOVITS_URL/_WHISPER_URL로 연결.
FROM python:3.12-slim

# ffmpeg: 참조 오디오 업로드 보정(트림·리샘플)에 필요
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY server ./server
COPY web ./web
COPY templates ./templates

# -e: 소스를 /app에 둔 채 의존성만 설치 (config.ROOT가 /app을 가리키게)
RUN pip install --no-cache-dir -e .

ENV INANNA_DB=/data/inanna.db \
    INANNA_COMPANIONS_DIR=/data/companions \
    INANNA_VOICES_DIR=/data/voices

# 비특권 실행 (보안 M4) — /data는 앱 사용자 소유
RUN useradd --system --create-home app \
    && mkdir -p /data && chown -R app:app /data /app
USER app
VOLUME /data
EXPOSE 8787

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8787"]
