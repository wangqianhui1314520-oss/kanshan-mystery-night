#!/usr/bin/env python3
"""临时探测：主菜单「单人模式」→ 序章视频阶段是否可用。

背景：frontend/js/main.js:219 的序章 <video> 依赖
  src=/assets/videos/opening.mp4（主源），onerror 回退 /assets/videos/prologue.mp4，
  @ended 才调 Store.startGame()。两个源若都 404，@ended 永不触发 → 流程卡死。
本脚本实测该路径真实状态（只读探测，不改代码）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8899"
SHOT = GAME / "data"


def main() -> int:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
        page = br.new_page(viewport={"width": 1280, "height": 900})
        reqs = []
        page.on("response", lambda r: reqs.append((r.status, r.url)) if "/assets/videos/" in r.url else None)
        page.on("pageerror", lambda e: print("  PAGEERROR:", str(e)[:120]))

        page.goto(BASE, wait_until="networkidle", timeout=30000)
        time.sleep(1.5)

        print("[单人模式] 点击")
        page.evaluate("""() => {
            const b = Array.from(document.querySelectorAll('button'))
                .find(x => x.innerText.replace(/\\s/g,'').includes('单人模式'));
            if (b) b.click();
        }""")
        time.sleep(2.5)

        # 若出现中间步骤（房间/人物）继续点主 CTA
        for i in range(6):
            st = page.evaluate("() => (window.Store && window.Store.state && window.Store.state.phase) || '?'")
            vin = page.evaluate("""() => {
                const v = document.querySelector('video');
                if (!v) return null;
                return {src: v.getAttribute('src'), readyState: v.readyState,
                        networkState: v.networkState, error: v.error ? v.error.code : null,
                        paused: v.paused, t: v.currentTime};
            }""")
            print(f"  step{i} phase={st} video={json.dumps(vin, ensure_ascii=False) if vin else None}")
            if st == "video" and vin:
                break
            page.evaluate("""() => {
                const hit = el => {
                    const r = el.getBoundingClientRect();
                    if (r.width < 2 || r.height < 2) return false;
                    const t = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                    return t && (el === t || el.contains(t));
                };
                const pref = ['翻开','进入','开始','单人','确认','选择','继续','下一'];
                const bs = Array.from(document.querySelectorAll('button')).filter(hit);
                for (const k of pref) {
                    const b = bs.find(b => b.innerText.includes(k));
                    if (b) { b.click(); return; }
                }
                if (bs.length) bs[bs.length-1].click();
            }""")
            time.sleep(2)

        time.sleep(4)
        st = page.evaluate("() => (window.Store && window.Store.state && window.Store.state.phase) || '?'")
        vin = page.evaluate("""() => {
            const v = document.querySelector('video');
            if (!v) return null;
            return {src: v.getAttribute('src'), readyState: v.readyState,
                    networkState: v.networkState, error: v.error ? v.error.code : null,
                    paused: v.paused, t: v.currentTime,
                    errMsg: v.error ? v.error.message : null};
        }""")
        print(f"\n最终 phase={st}")
        print(f"最终 video={json.dumps(vin, ensure_ascii=False)}")
        print("\n视频请求记录：")
        for s, u in reqs:
            print(f"  {s}  {u.replace(BASE,'')}")
        page.screenshot(path=str(SHOT / "_probe_intro.png"))
        print(f"\n截图: data/_probe_intro.png")
        br.close()

        stuck = (st == "video")
        return 1 if stuck else 0


if __name__ == "__main__":
    raise SystemExit(main())
