"""에너지 기반 발화 감지 (조용한 실내 1:1 통화 가정).

접속 직후 노이즈 플로어를 캘리브레이션하고, RMS가 플로어의 배수를 넘는
구간을 발화로 본다. 기본 감지기는 청취(idle/listening) 구간용이고,
재생 중 끼어들기(barge-in)는 make_barge_detector()의 보수적 파라미터
(높은 임계값 + 긴 지속 요구)로 에코·잡음 오탐을 걸러낸다 — 1차 방어는
클라이언트 AEC(웹 echoCancellation / iOS voiceChat).
"""
import math
import struct
from collections import deque

RATE = 16000
FRAME_MS = 20
FRAME_BYTES = RATE * 2 * FRAME_MS // 1000  # PCM16 mono 20ms = 640B


def _rms(frame: bytes) -> float:
    n = len(frame) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", frame[:n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


class UtteranceDetector:
    def __init__(self, calib_ms=800, start_ratio=3.0, min_start_rms=120.0,
                 start_ms=120, end_ms=1000, min_utt_ms=300, max_utt_s=60,
                 preroll_ms=300):
        # end_ms: 문장 사이 숨·생각하는 멈춤에 발화가 끊기지 않을 만큼.
        # 응답 지연에 그대로 더해지지만, 파이프라인이 멈춤 구간에 STT를
        # 미리 돌려(투기적 STT) 체감 지연을 상쇄한다.
        # min_start_rms/start_ratio: 폰의 노이즈 억제+AGC를 거친 신호는 레벨이
        # 낮게 들어온다 — 실기기(iOS Safari) 무반응 이슈로 하향 조정 (2026-07-10)
        self._calib_frames = calib_ms // FRAME_MS
        self._start_ratio = start_ratio
        self._min_start_rms = min_start_rms
        self._start_need = max(1, start_ms // FRAME_MS)
        self._end_need = max(1, end_ms // FRAME_MS)
        self._min_utt_frames = min_utt_ms // FRAME_MS
        self._max_utt_frames = max_utt_s * 1000 // FRAME_MS
        self._preroll = deque(maxlen=preroll_ms // FRAME_MS)

        self._pending = bytearray()   # 프레임 미만 잔여 바이트
        self._calib: list[float] = []
        self._floor = 0.0
        self.speaking = False
        self._above = 0
        self._below = 0
        self._utt = bytearray()
        # 발화 중 유성(有聲) 프레임 누적 카운터 — reset해도 유지되는 단조 증가값.
        # 투기적 STT가 "그 멈춤 이후 새 말이 없었는지"를 이 값 비교로 판정한다.
        self.voiced_total = 0

    def make_barge_detector(self) -> "UtteranceDetector":
        """재생 중 끼어들기 감지용 파생 감지기 — 캘리브레이션을 물려받되
        시작 판정만 훨씬 보수적으로 (에코가 AEC를 뚫고 남긴 잔향 무시)."""
        d = UtteranceDetector(start_ratio=self._start_ratio * 1.6,
                              min_start_rms=self._min_start_rms * 2.0,
                              start_ms=300)
        d._calib = [0.0] * self._calib_frames   # 캘리브레이션 건너뛰기
        d._floor = self._floor
        return d

    @property
    def pause_ms(self) -> int:
        """발화 중 현재 이어지고 있는 침묵의 길이 (비발화 중엔 0)."""
        return self._below * FRAME_MS if self.speaking else 0

    def snapshot(self) -> bytes:
        """지금까지 누적된 발화 PCM (투기적 STT 입력용)."""
        return bytes(self._utt)

    @property
    def start_threshold(self) -> float:
        return max(self._floor * self._start_ratio, self._min_start_rms)

    @property
    def end_threshold(self) -> float:
        return self.start_threshold * 0.6

    def reset(self) -> None:
        """턴 종료/인터럽트 후 청취 상태 초기화 (캘리브레이션은 유지)."""
        self._pending.clear()
        self._preroll.clear()
        self._utt.clear()
        self.speaking = False
        self._above = self._below = 0

    def feed(self, chunk: bytes) -> bytes | None:
        """PCM16 청크 투입. 발화가 끝났으면 발화 전체 PCM을 반환."""
        self._pending += chunk
        result = None
        while len(self._pending) >= FRAME_BYTES:
            frame = bytes(self._pending[:FRAME_BYTES])
            del self._pending[:FRAME_BYTES]
            done = self._feed_frame(frame)
            if done is not None:
                result = done  # 청크 하나에 발화 종료가 걸치면 마지막 것 사용
        return result

    def _feed_frame(self, frame: bytes) -> bytes | None:
        rms = _rms(frame)

        # 캘리브레이션: 첫 N프레임의 '중앙값'을 노이즈 플로어로
        # (평균은 캘리브레이션 중 말을 하면 부풀어 임계가 발화 위로 올라간다)
        if len(self._calib) < self._calib_frames:
            self._calib.append(rms)
            if len(self._calib) == self._calib_frames:
                s = sorted(self._calib)
                self._floor = s[len(s) // 2]
            return None

        # 비발화 구간에서 플로어를 천천히 적응 (환경 변화·AEC 감쇠 대응)
        if not self.speaking and rms < self.start_threshold:
            self._floor = 0.98 * self._floor + 0.02 * rms

        if not self.speaking:
            self._preroll.append(frame)
            if rms >= self.start_threshold:
                self._above += 1
                if self._above >= self._start_need:
                    self.speaking = True
                    self._utt = bytearray(b"".join(self._preroll))
                    self._above = 0
                    self._below = 0
            else:
                self._above = 0
            return None

        # speaking 중
        self._utt += frame
        if rms < self.end_threshold:
            self._below += 1
        else:
            self._below = 0
            self.voiced_total += 1

        too_long = len(self._utt) // FRAME_BYTES >= self._max_utt_frames
        if self._below >= self._end_need or too_long:
            utt = bytes(self._utt)
            frames = len(utt) // FRAME_BYTES
            self.reset()
            if frames >= self._min_utt_frames:
                return utt
        return None
