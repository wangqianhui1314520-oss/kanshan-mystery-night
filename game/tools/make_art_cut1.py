#!/usr/bin/env python3
"""Cut-1 美术切片：全身立绘 → 胸像；地点视频 → 暗拍静帧。零生图、零副作用以外的写盘。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
IMG = GAME / "content" / "assets" / "images"
VID = GAME / "content" / "assets" / "videos"
BUST = IMG / "bust"
STILL = IMG / "still"

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

# 地点 id → 视频文件（中段抽帧作暗拍底图）
LOC_VIDEOS = {
    "loc_reception": "loc_reception_new.mp4",
    "loc_desk": "loc_desk_new.mp4",
    "loc_teahouse": "loc_teahouse_new.mp4",
    "loc_locker": "loc_locker_new.mp4",
    "loc_monitor": "loc_monitor_new.mp4",
    "loc_server": "loc_server_new.mp4",
    "loc_archive": "loc_archive.mp4",
    "loc_hotfeed": "loc_hotfeed_new.mp4",
    "loc_ac": "loc_ac_new.mp4",
    "loc_roof": "loc_roof_new.mp4",
    "loc_clinic": "loc_clinic.mp4",
}


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def try_pil():
    try:
        from PIL import Image  # type: ignore
        return Image
    except Exception:
        return None


def bust_box(w: int, h: int) -> tuple[int, int, int, int]:
    """避开四角 HUD 残字，取上半身正方形。"""
    top = int(h * 0.09)
    side = min(int(w * 0.72), int(h * 0.40))
    x0 = max(0, (w - side) // 2)
    y0 = top
    if y0 + side > h:
        y0 = max(0, h - side)
    return x0, y0, side, side


def crop_bust_pil(Image, src: Path, dst: Path) -> None:
    im = Image.open(src).convert("RGBA")
    x0, y0, side, _ = bust_box(im.width, im.height)
    crop = im.crop((x0, y0, x0 + side, y0 + side))
    if side > 512:
        crop = crop.resize((512, 512), Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    crop.save(dst, "PNG", optimize=True)


def crop_bust_ffmpeg(src: Path, dst: Path) -> None:
    # 先探尺寸
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, check=True,
    )
    w, h = [int(x) for x in probe.stdout.strip().split(",")]
    x0, y0, side, _ = bust_box(w, h)
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vf", f"crop={side}:{side}:{x0}:{y0},scale=512:512",
         str(dst)],
        check=True,
    )


def extract_still(src: Path, dst: Path, sec: float = 5.0) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuvj420p"
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(sec), "-i", str(src),
           "-frames:v", "1", "-vf", vf, "-q:v", "4", str(dst)]
    r = subprocess.run(cmd)
    if r.returncode != 0 or not dst.exists() or dst.stat().st_size < 1024:
        cmd[cmd.index(str(sec))] = "1"
        subprocess.run(cmd, check=True)


def main() -> int:
    Image = try_pil()
    if Image is None and not have_ffmpeg():
        print("需要 Pillow 或 ffmpeg", file=sys.stderr)
        return 1

    BUST.mkdir(parents=True, exist_ok=True)
    STILL.mkdir(parents=True, exist_ok=True)

    for name in CHARS:
        src = IMG / name
        dst = BUST / name
        if not src.exists():
            print(f"[skip] missing {src}")
            continue
        if Image is not None:
            crop_bust_pil(Image, src, dst)
        else:
            crop_bust_ffmpeg(src, dst)
        print(f"[bust] {dst.relative_to(GAME)}  ({dst.stat().st_size // 1024} KB)")

    if not have_ffmpeg():
        print("[warn] 无 ffmpeg，跳过暗拍抽帧", file=sys.stderr)
        return 0

    for loc, fname in LOC_VIDEOS.items():
        src = VID / fname
        dst = STILL / f"{loc}.jpg"
        if not src.exists():
            print(f"[skip] missing {src}")
            continue
        extract_still(src, dst)
        print(f"[still] {dst.relative_to(GAME)}  ({dst.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
