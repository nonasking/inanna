"""아이콘 생성 — 통화 화면 오브의 시각 언어를 아이덴티티로.

전부 코드로 그리는 오리지널 그래픽 (저작권 안전). 8각 별 스파클은
이난나(수메르 금성 여신)의 고대 상징 — 퍼블릭 도메인.

사용: .venv/bin/python scripts/make-icons.py
출력: web/icon-{192,512}.png, web/apple-touch-icon.png,
      app/Inanna/Assets.xcassets/AppIcon.appiconset/AppIcon.png
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 2048  # 마스터 해상도 — 최종 크기로 다운샘플

BG_TOP = (16, 16, 24)
BG_BOT = (24, 18, 34)
HAZE = (110, 80, 180)
CORE = (226, 213, 255)
MID = (180, 140, 242)     # --accent
EDGE = (94, 68, 150)
RIM = (205, 180, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def radial_orb(size, cx, cy):
    """오프센터 하이라이트를 가진 구체 — 픽셀 단위 radial gradient."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    r = size / 2
    for y in range(size):
        for x in range(size):
            dx, dy = x - r, y - r
            d = math.hypot(dx, dy) / r
            if d > 1:
                continue
            # 하이라이트 중심(cx, cy) 기준 거리로 색 결정
            hd = math.hypot(x - cx * size, y - cy * size) / size
            t = min(hd * 1.7, 1.0)
            if t < 0.5:
                color = lerp(CORE, MID, t * 2)
            else:
                color = lerp(MID, EDGE, (t - 0.5) * 2)
            # 가장자리 어둡게 (구체감)
            shade = 1.0 - max(0.0, d - 0.72) * 1.6
            color = tuple(int(c * shade) for c in color)
            # 부드러운 가장자리 안티에일리어싱
            alpha = 255 if d < 0.985 else int(255 * (1 - d) / 0.015)
            px[x, y] = (*color, max(alpha, 0))
    return img


def star(draw, cx, cy, r, color):
    """8각 별 (이난나의 별) — 긴 4축 + 짧은 대각 4축."""
    for i in range(8):
        ang = math.pi / 4 * i
        length = r if i % 2 == 0 else r * 0.45
        w = r * 0.10 if i % 2 == 0 else r * 0.07
        tip = (cx + math.cos(ang) * length, cy + math.sin(ang) * length)
        left = (cx + math.cos(ang + math.pi / 2) * w, cy + math.sin(ang + math.pi / 2) * w)
        right = (cx + math.cos(ang - math.pi / 2) * w, cy + math.sin(ang - math.pi / 2) * w)
        draw.polygon([left, tip, right], fill=color)
    draw.ellipse([cx - r * 0.12, cy - r * 0.12, cx + r * 0.12, cy + r * 0.12], fill=color)


def make_master():
    img = Image.new("RGB", (S, S))
    px = img.load()
    for y in range(S):
        row = lerp(BG_TOP, BG_BOT, y / S)
        for x in range(S):
            px[x, y] = row

    # 오브 뒤 보라 안개 (radial haze)
    haze = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(haze)
    hd.ellipse([S * 0.14, S * 0.12, S * 0.86, S * 0.84], fill=(*HAZE, 90))
    haze = haze.filter(ImageFilter.GaussianBlur(S * 0.09))
    img.paste(haze, (0, 0), haze)

    # 글로우 (오브보다 큰 블러 원)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([S * 0.24, S * 0.22, S * 0.76, S * 0.74], fill=(*MID, 160))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.045))
    img.paste(glow, (0, 0), glow)

    # 오브 본체 (지름 46%)
    orb_size = int(S * 0.46)
    orb = radial_orb(orb_size, 0.38, 0.32)
    ox, oy = (S - orb_size) // 2, int(S * 0.48) - orb_size // 2
    img.paste(orb, (ox, oy), orb)

    # 하단 림 라이트 (반사광 초승달)
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    cx, cy, r = S / 2, S * 0.48, orb_size / 2
    rd.arc([cx - r, cy - r, cx + r, cy + r], start=35, end=145,
           fill=(*RIM, 150), width=int(S * 0.006))
    rim = rim.filter(ImageFilter.GaussianBlur(S * 0.004))
    img.paste(rim, (0, 0), rim)

    # 이난나의 8각 별 — 오브 우상단에 작게
    spark = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spark)
    star(sd, S * 0.685, S * 0.265, S * 0.052, (240, 232, 255, 235))
    sglow = spark.filter(ImageFilter.GaussianBlur(S * 0.012))
    img.paste(sglow, (0, 0), sglow)
    img.paste(spark, (0, 0), spark)
    return img


def main():
    master = make_master()
    out = {
        ROOT / "web/icon-512.png": 512,
        ROOT / "web/icon-192.png": 192,
        ROOT / "web/apple-touch-icon.png": 180,
        ROOT / "app/Inanna/Assets.xcassets/AppIcon.appiconset/AppIcon.png": 1024,
    }
    for path, size in out.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        master.resize((size, size), Image.LANCZOS).save(path)
        print(f"{path.relative_to(ROOT)} ({size})")


if __name__ == "__main__":
    main()
