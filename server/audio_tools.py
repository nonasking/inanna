"""ffmpeg/ffprobe 유틸 — launchd 등 최소 PATH 환경에서도 동작하도록 절대경로 해석."""
import shutil
import subprocess
from pathlib import Path

_CANDIDATES = ("/opt/homebrew/bin", "/usr/local/bin")


def _resolve(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for d in _CANDIDATES:
        p = Path(d) / name
        if p.exists():
            return str(p)
    return None


FFMPEG = _resolve("ffmpeg")
FFPROBE = _resolve("ffprobe")


def probe_duration(path: Path) -> float | None:
    if not FFPROBE:
        return None
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        return float(out)
    except (ValueError, subprocess.TimeoutExpired):
        return None


def convert_to_wav(src: Path, dest: Path, rate: int = 32000,
                   max_seconds: float | None = None) -> bool:
    """mono WAV로 표준화 (+선택적 길이 제한)."""
    if not FFMPEG:
        return False
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(src)]
    if max_seconds:
        cmd += ["-t", str(max_seconds)]
    cmd += ["-ar", str(rate), "-ac", "1", str(dest)]
    return subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0


def to_pcm16k(src: Path) -> bytes | None:
    """whisper 입력용 16kHz PCM16 raw."""
    if not FFMPEG:
        return None
    r = subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
         "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
        capture_output=True, timeout=60,
    )
    return r.stdout if r.returncode == 0 else None
