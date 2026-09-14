#!/usr/bin/env python3
"""Fix 刘看山 IP avatar portraits for seat phase.

Input (in content/assets/official/kanshan/):
  kanshan_portrait.png  -> already OK (235x290 RGBA)
  liubaba.png           -> sprite sheet 5000x2848 (10 cols x 4 rows)
  liumama.png           -> sprite sheet 6700x2010 (10 cols x 3 rows)
  yanou.png             -> sprite sheet 2100x720  (10 cols x 3 rows)
  beijixiong.png        -> corrupted placeholder -> regenerate polar bear
  qie.png               -> corrupted placeholder -> regenerate penguin-like qie

Output: all 6 files become 235x290 RGBA portrait avatars.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parents[1] / "content" / "assets" / "official" / "kanshan"
TARGET_W, TARGET_H = 235, 290


def trim_alpha(im: Image.Image) -> Image.Image:
    """Crop image to the bounding box of non-transparent pixels."""
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    alpha = im.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return im.crop((0, 0, 1, 1))
    return im.crop(bbox)


def center_on_canvas(src: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    """Scale src to fit inside canvas, preserving aspect ratio, and center it."""
    cw, ch = canvas_size
    src = trim_alpha(src)
    sw, sh = src.size
    scale = min(cw / sw, ch / sh, 1.0)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    src = src.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.paste(src, ((cw - nw) // 2, (ch - nh) // 2), src)
    return canvas


def extract_sprite_frame(path: Path, cols: int, rows: int, col: int = 0, row: int = 0) -> Image.Image:
    im = Image.open(path)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    w, h = im.size
    fw, fh = w // cols, h // rows
    x, y = col * fw, row * fh
    return im.crop((x, y, x + fw, y + fh))


def build_beijixiong(path: Path) -> None:
    """Minimalist polar bear avatar in Liu Kanshan black-and-white style."""
    im = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = TARGET_W // 2, TARGET_H // 2 + 8

    # White face circle
    face_r = 78
    d.ellipse((cx - face_r, cy - face_r, cx + face_r, cy + face_r), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=4)

    # Ears
    ear_r = 22
    d.ellipse((cx - face_r - ear_r + 8, cy - face_r - ear_r + 18, cx - face_r + ear_r + 8, cy - face_r + ear_r + 18), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=4)
    d.ellipse((cx + face_r - ear_r - 8, cy - face_r - ear_r + 18, cx + face_r + ear_r - 8, cy - face_r + ear_r + 18), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=4)

    # Inner ears
    inner_r = 10
    d.ellipse((cx - face_r - inner_r + 8, cy - face_r - inner_r + 18, cx - face_r + inner_r + 8, cy - face_r + inner_r + 18), fill=(0, 0, 0, 255))
    d.ellipse((cx + face_r - inner_r - 8, cy - face_r - inner_r + 18, cx + face_r + inner_r - 8, cy - face_r + inner_r + 18), fill=(0, 0, 0, 255))

    # Eyes
    eye_rx, eye_ry, eye_dy = 9, 12, -12
    d.ellipse((cx - 28 - eye_rx, cy + eye_dy - eye_ry, cx - 28 + eye_rx, cy + eye_dy + eye_ry), fill=(0, 0, 0, 255))
    d.ellipse((cx + 28 - eye_rx, cy + eye_dy - eye_ry, cx + 28 + eye_rx, cy + eye_dy + eye_ry), fill=(0, 0, 0, 255))

    # Nose
    d.ellipse((cx - 12, cy + 10, cx + 12, cy + 26), fill=(0, 0, 0, 255))

    # Mouth
    d.arc((cx - 22, cy + 18, cx + 22, cy + 58), start=0, end=180, fill=(0, 0, 0, 255), width=3)

    # Body hint (rounded shoulders)
    d.rounded_rectangle((cx - 55, cy + 58, cx + 55, cy + 138), radius=28, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=4)

    im.save(path, "PNG")
    print(f"[ok] generated {path.name} -> {im.size}")


def build_qie(path: Path) -> None:
    """Minimalist penguin/eggplant-ish character avatar in Kanshan style."""
    im = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = TARGET_W // 2, TARGET_H // 2 + 4

    # Body: black rounded shape
    body_w, body_h = 90, 130
    d.rounded_rectangle((cx - body_w // 2, cy - 20, cx + body_w // 2, cy + body_h - 20), radius=42, fill=(30, 30, 38, 255), outline=(0, 0, 0, 255), width=4)

    # White belly
    belly_w, belly_h = 58, 78
    d.rounded_rectangle((cx - belly_w // 2, cy + 10, cx + belly_w // 2, cy + 10 + belly_h), radius=26, fill=(255, 255, 255, 255))

    # Eyes
    d.ellipse((cx - 18, cy - 32, cx - 6, cy - 20), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=2)
    d.ellipse((cx + 6, cy - 32, cx + 18, cy - 20), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=2)
    d.ellipse((cx - 14, cy - 28, cx - 10, cy - 24), fill=(0, 0, 0, 255))
    d.ellipse((cx + 10, cy - 28, cx + 14, cy - 24), fill=(0, 0, 0, 255))

    # Beak
    d.polygon([(cx, cy - 18), (cx - 10, cy - 8), (cx + 10, cy - 8)], fill=(255, 160, 60, 255), outline=(0, 0, 0, 255))

    # Feet
    d.ellipse((cx - 30, cy + 104, cx - 8, cy + 124), fill=(255, 90, 80, 255), outline=(0, 0, 0, 255), width=2)
    d.ellipse((cx + 8, cy + 104, cx + 30, cy + 124), fill=(255, 90, 80, 255), outline=(0, 0, 0, 255), width=2)

    im.save(path, "PNG")
    print(f"[ok] generated {path.name} -> {im.size}")


def process_sprite(path: Path, cols: int, rows: int, col: int = 0, row: int = 0) -> None:
    frame = extract_sprite_frame(path, cols, rows, col, row)
    portrait = center_on_canvas(frame, (TARGET_W, TARGET_H))
    portrait.save(path, "PNG")
    print(f"[ok] extracted frame ({col},{row}) from {path.name} -> {portrait.size}")


def main() -> None:
    os.makedirs(BASE, exist_ok=True)

    process_sprite(BASE / "liubaba.png", cols=10, rows=4, col=0, row=0)
    process_sprite(BASE / "liumama.png", cols=10, rows=3, col=0, row=0)
    process_sprite(BASE / "yanou.png", cols=10, rows=3, col=0, row=0)
    build_beijixiong(BASE / "beijixiong.png")
    build_qie(BASE / "qie.png")

    print("\nFinal avatar report:")
    for name in ["kanshan_portrait.png", "beijixiong.png", "liubaba.png", "liumama.png", "qie.png", "yanou.png"]:
        p = BASE / name
        im = Image.open(p)
        print(f"  {name:22} size={im.size} mode={im.mode} bytes={p.stat().st_size}")


if __name__ == "__main__":
    main()
