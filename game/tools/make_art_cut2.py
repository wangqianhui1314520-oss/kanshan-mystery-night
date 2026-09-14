#!/usr/bin/env python3
"""Cut-2 美术切片：裁掉 AI 图四周 HUD 乱码框，再重裁胸像。

幂等：首次把原图拷到 images/_pre_hudcrop/，之后一律从备份重裁，
避免连跑两次把主体越裁越小。不碰 official/kanshan、卡背、成就、UI 底图。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
IMG = GAME / "content" / "assets" / "images"
BACKUP = IMG / "_pre_hudcrop"
BUST = IMG / "bust"
MARKER = IMG / ".hudcrop.json"

# 横图：左右 7.2% / 上下 12.5% —— 角上「知乎」比 HUD 线更靠里
LAND_X, LAND_Y = 0.072, 0.125
# 竖图：左右 7.8% / 上下 5.2% —— 够切掉顶栏 SSPIEIFUTENT
PORT_X, PORT_Y = 0.078, 0.052

CHARS = [
    "char_zhizhizhe.png",
    "char_liuliangjiang.png",
    "char_lurenjia.png",
    "char_chendijun.png",
    "char_bishangxian.png",
    "char_kanshanbot.png",
    "char_yanzhijun.png",
    "char_v587.png",
    "dm_kanshan_holo.png",
]


def try_pil():
    try:
        from PIL import Image  # type: ignore
        return Image
    except Exception:
        return None


def targets() -> list[Path]:
    names = []
    names += [p.name for p in sorted(IMG.glob("scene_*.png"))]
    names += [p.name for p in sorted(IMG.glob("act_t*.png"))]
    names += CHARS
    out = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        p = IMG / name
        if p.exists():
            out.append(p)
    return out


def insets(w: int, h: int) -> tuple[int, int, int, int]:
    if w >= h:
        dx, dy = int(w * LAND_X), int(h * LAND_Y)
    else:
        dx, dy = int(w * PORT_X), int(h * PORT_Y)
    x0, y0 = dx, dy
    x1, y1 = w - dx, h - dy
    if x1 - x0 < 64 or y1 - y0 < 64:
        raise ValueError(f"inset too large for {w}x{h}")
    return x0, y0, x1, y1


def bust_box(w: int, h: int) -> tuple[int, int, int, int]:
    """HUD 已裁掉，顶边少切一点，避免削到额头。"""
    top = int(h * 0.04)
    side = min(int(w * 0.78), int(h * 0.42))
    x0 = max(0, (w - side) // 2)
    y0 = top
    if y0 + side > h:
        y0 = max(0, h - side)
    return x0, y0, side, side


def crop_file(Image, src: Path, dst: Path) -> tuple[int, int]:
    im = Image.open(src).convert("RGBA")
    box = insets(im.width, im.height)
    cropped = im.crop(box)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(dst, "PNG", optimize=True)
    return cropped.size


def remake_busts(Image) -> None:
    BUST.mkdir(parents=True, exist_ok=True)
    for name in CHARS:
        src = IMG / name
        dst = BUST / name
        if not src.exists():
            print(f"[skip] missing {src.name}")
            continue
        im = Image.open(src).convert("RGBA")
        x0, y0, side, _ = bust_box(im.width, im.height)
        crop = im.crop((x0, y0, x0 + side, y0 + side))
        if side > 512:
            crop = crop.resize((512, 512), Image.Resampling.LANCZOS)
        crop.save(dst, "PNG", optimize=True)
        print(f"[bust] {dst.relative_to(GAME)}  ({dst.stat().st_size // 1024} KB)")


def circle_mask(Image, src: Path, dst: Path, keep: float = 0.78) -> None:
    """取中心圆形，切掉四角 HUD。keep=保留边长比例。"""
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    side = int(min(w, h) * keep)
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    im = im.crop((x0, y0, x0 + side, y0 + side))
    im = im.resize((512, 512), Image.Resampling.LANCZOS)
    mask = Image.new("L", (512, 512), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).ellipse((1, 1, 510, 510), fill=255)
    im.putalpha(mask)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "PNG", optimize=True)


def mask_emblems(Image) -> int:
    card = IMG / "card"
    if not card.exists():
        print("[skip] no card/ emblems yet")
        return 0
    full = card / "_full"
    full.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(card.glob("kc_*.png")):
        bak = full / src.name
        if not bak.exists():
            shutil.copy2(src, bak)
        circle_mask(Image, bak, src, keep=0.72)
        print(f"[emblem] masked {src.name}  ({src.stat().st_size // 1024} KB)")
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="无视标记，从备份重裁")
    ap.add_argument("--emblem-mask", action="store_true", help="只做纹章圆形遮罩")
    args = ap.parse_args()

    Image = try_pil()
    if Image is None:
        print("需要 Pillow", file=sys.stderr)
        return 1

    if args.emblem_mask:
        mask_emblems(Image)
        return 0

    files = targets()
    BACKUP.mkdir(parents=True, exist_ok=True)
    log = {"version": 2, "land": [LAND_X, LAND_Y], "port": [PORT_X, PORT_Y], "files": {}}

    for src in files:
        bak = BACKUP / src.name
        if not bak.exists():
            shutil.copy2(src, bak)
        w, h = crop_file(Image, bak, src)
        log["files"][src.name] = {"out": [w, h]}
        print(f"[hud] {src.name} -> {w}x{h}")

    remake_busts(Image)
    MARKER.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] cropped {len(files)} files, busts remade")
    return 0


if __name__ == "__main__":
    sys.exit(main())
