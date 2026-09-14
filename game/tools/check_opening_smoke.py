#!/usr/bin/env python3
"""临时验证脚本：核实「序章视频」实跑链路。

只读/零副作用（不修改任何游戏文件，仅驱动浏览器 UI 并截图到 data/_ 前缀）。

验证点：
  1. 进入 phase=video 后 <video> 实际加载并能够播放（readyState / currentTime 前进）
  2. 视频自然播完后是否 @ended 触发 → 自动进入 phase=play（不卡黑屏）
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8899"
OUT = GAME / "data" / "_opening_verify.json"


def main() -> int:
    res: dict = {"steps": [], "video": {}, "errors": []}
    with sync_playwright() as p:
        launcher = None
        for ch in ("chrome", "msedge"):
            try:
                # 禁用磁盘缓存：静态资源被覆盖后，浏览器缓存会给出旧时长/旧内容的假通过
                launcher = p.chromium.launch(
                    channel=ch,
                    args=["--disk-cache-size=1", "--media-cache-size=1",
                          "--autoplay-policy=no-user-gesture-required"],
                )
                res["steps"].append(f"browser={ch}")
                break
            except Exception as e:
                res["steps"].append(f"{ch} unavailable: {str(e)[:80]}")
        if launcher is None:
            launcher = p.chromium.launch()
        browser = launcher
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        msgs = []
        page.on("console", lambda m: msgs.append(m.text[:200]) if m.type == "error" else None)
        page.on("pageerror", lambda e: msgs.append(f"PAGEERROR {e}"))
        failed = []
        page.on("response", lambda r: failed.append((r.status, r.url)) if r.status >= 400 else None)

        page.goto(BASE, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 单人模式
        page.get_by_text("单 人 模 式", exact=False).first.click()
        time.sleep(1.5)
        res["steps"].append(f"phase after solo: {page.evaluate('() => window.Store.state.phase')}")

        # 进入序章视频
        btn = page.get_by_text("确 认 · 进 入 序 章", exact=False)
        if btn.count() == 0:
            btn = page.get_by_text("确 认 · 进 入 序 章 ▸", exact=False)
        btn.first.click()
        time.sleep(2.5)
        phase = page.evaluate("() => window.Store.state.phase")
        res["steps"].append(f"phase after startVideo: {phase}")

        info = page.evaluate("""() => {
            const v = document.querySelector('.video-phase video');
            if (!v) return { found: false };
            return {
              found: true,
              src: v.getAttribute('src'),
              currentSrc: v.currentSrc,
              readyState: v.readyState,
              videoWidth: v.videoWidth,
              videoHeight: v.videoHeight,
              duration: v.duration,
              paused: v.paused,
              muted: v.muted,
              currentTime: v.currentTime,
              networkState: v.networkState,
              error: v.error ? v.error.code : null,
            };
        }""")
        res["video"] = info
        page.screenshot(path=str(GAME / "data" / "_opening_frame.png"))

        # 等待 3s，确认 currentTime 真的在前进（自动播放未被 autoplay policy 拦截）
        time.sleep(3)
        info2 = page.evaluate("""() => {
            const v = document.querySelector('.video-phase video');
            if (!v) return null;
            return { t: v.currentTime, paused: v.paused, ended: v.ended, src: v.getAttribute('src') };
        }""")
        res["video_after_3s"] = info2

        # 等自然播完（duration + 缓冲余量）
        dur = info.get("duration") or 15
        page.wait_for_function("() => window.Store.state.phase === 'play'",
                               timeout=int(dur * 1000) + 15000)
        res["auto_entered_play"] = True
        res["steps"].append("video ended -> auto enter phase=play OK")
        page.screenshot(path=str(GAME / "data" / "_opening_after.png"))

        # ---- 断言（回归守护）：主源必须是 opening.mp4 且为完整 14.4s 版本 ----
        assert info["src"] == "/assets/videos/opening.mp4", f"主源错误: {info['src']}"
        assert abs((info.get("duration") or 0) - 14.375) < 0.5, f"时长异常: {info.get('duration')}"
        assert info["videoWidth"] == 1280 and info["videoHeight"] == 720, "分辨率非 1280x720"
        assert info["readyState"] == 4, f"未加载完成 readyState={info['readyState']}"
        assert info2 and info2["t"] > info["currentTime"], "视频未推进（autoplay 被拦截？）"
        res["assertions"] = "ALL PASS: src=opening.mp4 / duration≈14.375 / 1280x720 / readyState=4 / playing"

        res["console_errors"] = msgs[-10:]
        res["http_failures"] = [f for f in failed if "videos/" in f[1]][:10]
        browser.close()

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
