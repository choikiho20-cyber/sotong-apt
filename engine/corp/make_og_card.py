# -*- coding: utf-8 -*-
"""카톡 링크 미리보기용 OG 카드 생성 (전자명함 대체).

config.json + (있으면) assets/hero.jpg -> assets/og-card.jpg (1200x630)
빌드 시 assets/ 전체가 dist/로 복사되므로, 한 번 생성해 두면 이후 build.py에서 그대로 배포됨.
사진 교체·정보 수정 후에는 다시 실행: python make_og_card.py
"""
import json
import re
import textwrap
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

import sys
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()   # 세대 폴더 (python make_og_card.py <세대 폴더>)
W, H = 1200, 630
BAR_H = 96

# 10/29 법인판 남색·은색 디자인에 맞춤 (이름은 옛 초록 테마 그대로 둔다)
INK = (255, 255, 255)
PINE = (199, 204, 212)
PINE_DEEP = (8, 14, 28)
TINT = (15, 23, 42)
PAPER = (255, 253, 247)
STONE = (203, 213, 225)
LINE = (224, 216, 195)
ON_PINE = (238, 241, 245)

SERIF = r"C:\Windows\Fonts\NotoSerifKR-VF.ttf"
SANS = r"C:\Windows\Fonts\malgun.ttf"
SANS_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"


def serif(size, weight=900):
    f = ImageFont.truetype(SERIF, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def photo_panel(cfg):
    px, pw = 760, W - 760
    hero = None
    for name in ("hero.webp", "hero.jpg", "hero.jpeg", "hero.png"):
        p = ROOT / "assets" / name
        if p.exists():
            hero = Image.open(p).convert("RGB")
            break
    if hero is None:
        panel = Image.new("RGB", (pw, H), (213, 205, 179))
        d = ImageDraw.Draw(panel)
        cx = pw // 2
        d.ellipse([cx - 90, 120, cx + 90, 300], fill=(171, 160, 128))
        d.rounded_rectangle([cx - 150, 300, cx + 150, 560], radius=60, fill=(171, 160, 128))
        return panel, px

    sw, sh = hero.size
    target_ratio = pw / H
    if sw / sh > target_ratio:
        new_w = int(sh * target_ratio)
        hero = hero.crop(((sw - new_w) // 2, 0, (sw - new_w) // 2 + new_w, sh))
    else:
        new_h = int(sw / target_ratio)
        hero = hero.crop((0, 0, sw, new_h))
    hero = hero.resize((pw, H), Image.LANCZOS)
    hero = ImageEnhance.Color(hero).enhance(0.75)
    hero = ImageEnhance.Contrast(hero).enhance(1.03)
    return hero, px


def blend_seam(canvas, seam_x, width=170):
    grad = Image.new("L", (width, H), 0)
    gd = ImageDraw.Draw(grad)
    for i in range(width):
        alpha = int(255 * (1 - i / width) ** 1.4)
        gd.line([(i, 0), (i, H)], fill=alpha)
    overlay = Image.new("RGBA", (width, H), TINT + (0,))
    overlay.putalpha(grad)
    canvas.paste(Image.new("RGB", (width, H), TINT), (seam_x, 0), overlay)


def wrap(draw, text, font, max_w):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_name_size(draw, text, max_w, start=118, floor=64):
    size = start
    while size > floor:
        f = serif(size, 900)
        if draw.textlength(text, font=f) <= max_w:
            return f, size
        size -= 4
    return serif(floor, 900), floor


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    canvas = Image.new("RGB", (W, H), TINT)
    photo, px = photo_panel(cfg)
    canvas.paste(photo, (px, 0))
    blend_seam(canvas, px)

    d = ImageDraw.Draw(canvas)
    pad = 64
    max_text_w = px - pad - 40

    d.text((pad, 66), f"법인 경영 컨설턴트 · {cfg['region']}", font=ImageFont.truetype(SANS_BOLD, 27), fill=PINE)

    name_font, name_size = fit_name_size(d, cfg["name"], max_text_w)
    name_y = 108
    d.text((pad, name_y), cfg["name"], font=name_font, fill=INK)

    tagline_font = ImageFont.truetype(SANS, 32)
    ty = name_y + name_size + 34
    for line in wrap(d, cfg["tagline"], tagline_font, max_text_w)[:2]:
        d.text((pad, ty), line, font=tagline_font, fill=STONE)
        ty += 44

    caption = " · ".join(cfg.get("chips", [])[:3])
    if caption:
        d.text((pad, ty + 14), caption, font=ImageFont.truetype(SANS, 22), fill=(148, 163, 184))

    d.rectangle([0, H - BAR_H, W, H], fill=PINE_DEEP)
    phone_font = ImageFont.truetype(SANS_BOLD, 40)
    label_font = ImageFont.truetype(SANS, 20)
    bar_cy = H - BAR_H / 2
    d.text((pad, bar_cy), cfg["phone"], font=phone_font, fill=ON_PINE, anchor="lm")

    host = urlparse(cfg.get("site_url", "")).netloc
    right_label = host if host and host != "example.com" else cfg["region"]
    d.text((W - pad, bar_cy), right_label, font=label_font, fill=(199, 204, 212), anchor="rm")

    out = ROOT / "assets" / "og-card.jpg"
    canvas.save(out, quality=90)
    print(f"생성 완료: {out} ({W}x{H})")


if __name__ == "__main__":
    main()
