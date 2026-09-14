#!/usr/bin/env python3
"""Agnes AI 资产生成器（游戏美术管线）

用途：为《求真档案局·看山失踪夜》生成角色立绘、场景图与开场视频。
API：Agnes AI（OpenAI 兼容）—— agnes-image-2.5-flash / agnes-video-2.5-flash
密钥：从 game/tools/.env 读取（AGNES_API_KEY），严禁硬编码进仓库。

用法：
  python asset_gen.py --manifest asset_manifest.json           # 按清单批量生成
  python asset_gen.py --image "提示词" --out ../content/assets/images/x.png
  python asset_gen.py --video "提示词" --out ../content/assets/videos/x.mp4 --seconds 4
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import subprocess
from pathlib import Path

import urllib.request

TOOLS_DIR = Path(__file__).resolve().parent
GAME_DIR = TOOLS_DIR.parent

# 统一美术方向（所有素材共用，保证风格一致性）
STYLE_PREFIX = (
    "现代都市悬疑喜剧插画风格，扁平厚涂质感，深蓝紫赛博夜景主调，"
    "知乎蓝色霓虹点缀，电影感构图，高质量细节，"
    "画面中不出现任何文字、字母、水印、HUD边框或界面装饰"
)


def load_env():
    # 环境变量优先：便于切换国际站 / 测试账号，无需改动 .env 明文
    if "AGNES_API_KEY" in os.environ and "AGNES_BASE_URL" in os.environ:
        return {
            "AGNES_BASE_URL": os.environ["AGNES_BASE_URL"],
            "AGNES_API_KEY": os.environ["AGNES_API_KEY"],
            "AGNES_IMAGE_MODEL": os.environ.get("AGNES_IMAGE_MODEL", "agnes-image-2.5-flash"),
            "AGNES_VIDEO_MODEL": os.environ.get("AGNES_VIDEO_MODEL", "agnes-video-2.5-flash"),
        }
    env = {}
    env_path = None
    game_root = TOOLS_DIR.parent
    for cand in (TOOLS_DIR / ".env",
                 game_root.parent / ".workbuddy" / "secrets" / "agnes.env"):
        if cand.exists():
            env_path = cand
            break
    if env_path is None:
        raise FileNotFoundError("未找到密钥文件 tools/.env（或 .workbuddy/secrets/agnes.env）")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = load_env()
BASE = ENV["AGNES_BASE_URL"].rstrip("/")
KEY = ENV["AGNES_API_KEY"]
IMG_MODEL = ENV.get("AGNES_IMAGE_MODEL", "agnes-image-2.5-flash")
VID_MODEL = ENV.get("AGNES_VIDEO_MODEL", "agnes-video-2.5-flash")


def _post(path: str, payload: dict, timeout: int = 180, retry: int = 0) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code == 429 and retry < 3:  # 免费档速率限制：指数退避
            wait = 30 * (2 ** retry)
            print(f"[429] rate limited, retry in {wait}s ...", file=sys.stderr)
            time.sleep(wait)
            return _post(path, payload, timeout, retry + 1)
        raise RuntimeError(f"HTTP {exc.code} {path}: {body}") from exc


def _get(url: str, timeout: int = 60, retry: int = 0) -> dict:
    """带 429 退避的 GET。

    轮询端点同速率限制，免费档每隔几秒打一次极易 429；此处做与 _post 对称的
    指数退避 + 熔断，保证「任务还在服务端跑」不会被一次限流打成整单失败。
    """
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        if exc.code in (429, 500, 502, 503, 504) and retry < 6:
            wait = 5 * (2 ** retry)          # 5/10/20/40/80/160s
            print(f"[{exc.code}] GET rate limited, backoff {wait}s ...", file=sys.stderr)
            time.sleep(wait)
            return _get(url, timeout, retry + 1)
        raise RuntimeError(f"HTTP {exc.code} GET {url[:80]}: {body}") from exc


def _strip_audio(path: Path) -> None:
    """剥离音轨并加 faststart：Agnes 返回自带 AAC 音轨，带音轨会被浏览器
    autoplay 策略拦截（尤其是 <video autoplay> 无 muted 时），且增大体积。
    就地重编码 h264，规格保持 720p/24fps。ffmpeg 不存在时跳过（不阻断主流程）。"""
    try:
        tmp = path.with_suffix(".tmp.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(path),
             "-c:v", "copy", "-an", "-movflags", "+faststart",
             str(tmp)],
            check=True,
        )
        tmp.replace(path)
    except FileNotFoundError:
        print("[warn] ffmpeg 不可用，跳过音轨剥离", file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        print(f"[warn] 音轨剥离失败(exit={exc.returncode})，保留原始文件", file=sys.stderr)


def poll_video(video_id: str, out_path: str, poll_interval: int = 6,
               max_wait: int = 900) -> str:
    """按 video_id 轮询 → 下载 mp4。可独立用于续拉已完成/进行中的任务，不重复计费。"""
    poll_url = f"{BASE.split('/v1')[0]}/agnesapi?video_id={video_id}&model_name={VID_MODEL}"
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(poll_interval)
        st = _get(poll_url)
        status = st.get("status")
        if status in ("completed", "succeeded", "success"):
            url = st.get("url") or (st.get("metadata") or {}).get("url")
            if not url:
                raise RuntimeError(f"completed 但无 url: {str(st)[:400]}")
            out = GAME_DIR / out_path
            out.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, out)
            _strip_audio(out)   # 浏览器静音自动播放 + 体积
            print(f"[video] {out} ({out.stat().st_size // 1024} KB)")
            return str(out)
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(str(st.get("error", st))[:400])
        print(f"[video] {status} ...")
    raise TimeoutError(f"polling timeout after {max_wait}s (video_id={video_id} 仍在服务端，可用 --resume 续拉)")


def gen_image(prompt: str, out_path: str, size: str = "1440x720") -> str:
    """文生图，返回保存路径。size 用像素串（横 1440x720 / 竖 720x1440 已验证）。"""
    data = _post(
        "/images/generations",
        {"model": IMG_MODEL, "prompt": f"{STYLE_PREFIX}：{prompt}", "size": size, "n": 1},
    )
    item = data["data"][0]
    out = GAME_DIR / out_path
    out.parent.mkdir(parents=True, exist_ok=True)
    if "url" in item and item["url"]:
        urllib.request.urlretrieve(item["url"], out)
    elif "b64_json" in item and item["b64_json"]:
        out.write_bytes(base64.b64decode(item["b64_json"]))
    else:
        raise RuntimeError(f"响应中无图像数据: {list(item)}")
    print(f"[image] {out} ({out.stat().st_size // 1024} KB)")
    return str(out)


def gen_video(prompt: str, out_path: str, seconds: int = 4, size: str = "720P",
              aspect_ratio: str = "16:9", first_frame_url: str | None = None,
              max_wait: int = 900, poll_interval: int = 6) -> str:
    """文生视频（或首帧图生视频）。创建任务→轮询→下载 mp4。"""
    payload = {
        "model": VID_MODEL,
        "prompt": prompt,
        "mode": "keyframe" if first_frame_url else "text",
        "seconds": str(seconds),
        "size": size,
        "aspect_ratio": aspect_ratio,
        "n": 1,
    }
    if first_frame_url:
        payload["first_frame"] = first_frame_url
    created = _post("/videos", payload, timeout=300)
    video_id = created.get("video_id") or created.get("id")
    # 任务已计费并在服务端排队；即便本地后续失败也可用 --resume 续拉，务必回显 id。
    print(f"[video] task created: {video_id}")
    print(f"[video] 若本地中断，用 --resume {video_id} --out {out_path} 续拉")
    try:
        return poll_video(video_id, out_path,
                          poll_interval=poll_interval, max_wait=max_wait)
    except Exception as exc:
        raise RuntimeError(f"{exc} | video_id={video_id}") from exc


def run_manifest(manifest_path: str) -> None:
    for job in json.loads(Path(manifest_path).read_text(encoding="utf-8")):
        kind = job["type"]
        out = GAME_DIR / job["out"]
        # 幂等：image 与 video 均跳过已有成品（video 原先不跳过，重跑会覆盖已付费产出）
        if out.exists() and not job.get("overwrite"):
            print(f"[skip] exists: {job['out']}")
            continue
        try:
            if kind == "image":
                gen_image(job["prompt"], job["out"], job.get("size", "1440x720"))
            elif kind == "video":
                gen_video(job["prompt"], job["out"], job.get("seconds", 4),
                          job.get("size", "720P"), job.get("aspect_ratio", "16:9"),
                          poll_interval=job.get("poll", 6), max_wait=job.get("wait", 900))
            else:
                print(f"[skip] unknown type {kind}")
        except Exception as exc:  # 单项失败不中断批次
            print(f"[FAIL] {job.get('out')}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--image")
    ap.add_argument("--video")
    ap.add_argument("--first-frame")
    ap.add_argument("--out")
    ap.add_argument("--size", default="1440x720")
    ap.add_argument("--seconds", type=int, default=4)
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--resume", help="已有 video_id，续拉下载，不重复提交任务")
    ap.add_argument("--poll", type=int, default=6, help="轮询间隔秒（默认6，过小易触发429）")
    ap.add_argument("--wait", type=int, default=900, help="轮询最长等待秒")
    args = ap.parse_args()
    if args.resume:
        if not args.out:
            ap.error("--resume 需配合 --out 指定保存路径")
        poll_video(args.resume, args.out, poll_interval=args.poll, max_wait=args.wait)
    elif args.manifest:
        run_manifest(args.manifest)
    elif args.image:
        gen_image(args.image, args.out, args.size)
    elif args.video:
        gen_video(args.video, args.out, args.seconds, args.size, args.aspect, args.first_frame)
    else:
        ap.error("need --manifest / --image / --video")
