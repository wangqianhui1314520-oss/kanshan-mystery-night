#!/usr/bin/env python3
"""临时验证：新接入的两条视频是否真的在 UI 里渲染并播放。

验证点：
  A. 第一幕转场（st-actcut act=1）→ .st-ac-vid 视频加载且播放（失败会降级 img）
  B. 线索详情（clue_007「被擦掉的监控片段」）→ .cd-media video 加载且播放

驱动方式：直接操作 Store 状态（不模拟长时间序章播放），只读游戏文件、零副作用。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8899"


def probe_video(page, selector: str) -> dict:
    return page.evaluate(
        """(sel) => {
            const v = document.querySelector(sel);
            if (!v) return { found: false };
            return {
              found: true, tag: v.tagName,
              src: v.currentSrc || v.getAttribute('src'),
              readyState: v.readyState, paused: v.paused,
              videoWidth: v.videoWidth, duration: v.duration,
              t: v.currentTime, muted: v.muted,
              error: v.error ? v.error.code : null,
            };
        }""",
        selector,
    )


def main() -> int:
    res: dict = {"actcut": {}, "clue_detail": {}, "errors": []}
    with sync_playwright() as p:
        launcher = None
        for ch in ("chrome", "msedge"):
            try:
                # 注意：不要加 --disk-cache-size=1，禁缓存会让媒体加载不稳定触发 @error 降级，
                # 造成「功能正常但验证假失败」；此处每次新开 context 无历史缓存，不依赖该参数。
                launcher = p.chromium.launch(
                    channel=ch,
                    args=["--autoplay-policy=no-user-gesture-required"],
                )
                break
            except Exception:
                launcher = None
        if launcher is None:
            launcher = p.chromium.launch()
        page = launcher.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: res["errors"].append(f"PAGEERROR {e}"))
        page.on("console", lambda m: res["errors"].append(m.text[:160]) if m.type == "error" else None)

        page.goto(BASE, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 注入卷宗页状态（跳过序章），再推进到第一幕转场 cut={act:1}
        page.evaluate("""() => {
            const St = window.Store.state;
            St.showtime = { step: 'case_file' };
            St.phase = 'play';
            St.view = 'chat';
            window.Store.showtimeNext();
        }""")
        # 转场页 2.5s 自动关闭：等「视频真正开始播放」（readyState>=2 且 t>0），
        # 超时预算与真实转场窗口一致（2.3s）——真实用户也只有这窗口，播不起来就是缺陷
        try:
            page.wait_for_function(
                "() => { const v = document.querySelector('.st-actcut video.st-ac-vid');"
                " return v && v.readyState >= 2 && v.currentTime > 0; }",
                timeout=2300,
            )
        except Exception:
            pass
        res["actcut"] = probe_video(page, ".st-actcut video.st-ac-vid")
        res["actcut_t2"] = (probe_video(page, ".st-actcut video.st-ac-vid") or {}).get("t")
        res["actcut_fallback_img"] = page.evaluate(
            "() => !!document.querySelector('.st-actcut img.st-ac-img')")
        page.screenshot(path=str(GAME / "data" / "_qc" / "verify_actcut.png"))
        page.evaluate("() => window.Store.cutDismiss()")
        time.sleep(0.5)

        # ---- 断言 A（转场视频在存活窗口内推进） ----
        a = res["actcut"]
        assert a.get("found") and a["readyState"] >= 2, f"第一幕转场视频未加载: {a}"
        assert (res["actcut_t2"] or 0) > a["t"], f"转场视频未推进: {a['t']} -> {res['actcut_t2']}"
        assert abs((a.get("duration") or 0) - 5.167) < 0.5, f"转场视频时长异常: {a.get('duration')}"

        # ---- B. 线索详情视频（clue_007） ----
        page.evaluate("""() => {
            const St = window.Store.state;
            St.clues = { clue_007: { at: 1 } };   // 直接持有该线索
        }""")
        # 切到证物袋视图并打开详情
        page.evaluate("""() => {
            const St = window.Store.state;
            St.view = 'bag';
            const c = window.MOCK.clues.find(x => x.id === 'clue_007');
            window.dispatchEvent(new CustomEvent('noop'));  // 触发一次响应式刷新（无害）
        }""")
        time.sleep(1)
        # bag 视图用 <clue-card>（根元素 button.clue-card）emit open；owned 只塞了 clue_007，第一张即目标
        n_cards = page.evaluate("() => document.querySelectorAll('button.clue-card').length")
        clicked = page.evaluate(
            "() => { const c = document.querySelector('button.clue-card'); if (c) { c.click(); return true; } return false; }")
        try:
            page.wait_for_function(
                "() => { const v = document.querySelector('.clue-detail .cd-media video');"
                " return v && v.readyState >= 2 && v.currentTime > 0; }",
                timeout=8000,
            )
        except Exception:
            pass
        res["clue_cards_found"] = n_cards
        res["clue_card_clicked"] = clicked
        res["clue_detail"] = probe_video(page, ".clue-detail .cd-media video")
        time.sleep(1.2)  # loop 视频，二次探测确认推进
        res["clue_detail_t2"] = (probe_video(page, ".clue-detail .cd-media video") or {}).get("t")
        res["clue_detail_visible"] = page.evaluate(
            "() => { const m = document.querySelector('.clue-detail'); return !!m; }")
        page.screenshot(path=str(GAME / "data" / "_qc" / "verify_clue.png"))

        # ---- 断言 B（线索详情视频加载且推进） ----
        b = res["clue_detail"]
        assert b.get("found") and b["readyState"] >= 2, f"线索详情视频未加载: {b}"
        assert (res["clue_detail_t2"] or 0) > b["t"], f"线索视频未推进: {b['t']} -> {res['clue_detail_t2']}"
        res["verdict"] = "ALL PASS: 第一幕转场 banner 视频 + clue_007 监控视频均加载且播放推进"
        launcher.close()
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
