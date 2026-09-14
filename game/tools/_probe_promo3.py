#!/usr/bin/env python3
"""探测 3：8899 端口 WS 通道 + 联机同房可见性（只读）。"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8899"
OUT = Path(__file__).resolve().parent.parent / "data" / "_promo_probe"


def boot(browser, tag):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    ctx.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and print(f"[{tag}]", m.text[:180], flush=True))
    page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => window.Store && document.querySelector('.card.menu')", timeout=30000)
    page.wait_for_timeout(2500)
    return ctx, page


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--autoplay-policy=no-user-gesture-required"])
        ctx1, p1 = boot(browser, "host")
        print("host net:", p1.evaluate("() => [window.Net.kind(), window.Store.state.netKind]"), flush=True)
        p1.locator("details.menu-more summary").click()
        p1.wait_for_timeout(400)
        p1.locator("button", has_text="房间模式").first.click()
        p1.wait_for_function("() => window.Store.state.phase === 'party'", timeout=8000)
        p1.wait_for_timeout(600)
        p1.locator("button", has_text="创 建 房 间").first.click()
        p1.wait_for_timeout(4000)
        st = p1.evaluate("""() => ({code: window.Store.state.roomCode, sid: window.Store.state.sessionId,
            net: window.Store.state.netKind, phase: window.Store.state.phase, host: window.Store.state.isHost})""")
        print("host room:", json.dumps(st, ensure_ascii=False), flush=True)

        ctx2, p2 = boot(browser, "guest")
        p2.goto(f"{BASE}/?room={st['code']}", wait_until="domcontentloaded", timeout=45000)
        p2.wait_for_function("() => window.Store && window.Store.state.roomCode", timeout=30000)
        p2.wait_for_timeout(4500)
        print("guest:", json.dumps(p2.evaluate("""() => ({code: window.Store.state.roomCode,
            net: window.Store.state.netKind, phase: window.Store.state.phase,
            sid: window.Store.state.sessionId, mode: window.Store.state.mode})"""), ensure_ascii=False), flush=True)
        p2.screenshot(path=str(OUT / "30_ws_guest.png"))
        p1.wait_for_timeout(2500)
        print("host seats:", json.dumps(p1.evaluate(
            "() => [...document.querySelectorAll('.g-card')].map(e=>(e.textContent||'').trim().slice(0,12))"),
            ensure_ascii=False), flush=True)
        p1.screenshot(path=str(OUT / "31_ws_host.png"))
        ctx1.close(); ctx2.close(); browser.close()


if __name__ == "__main__":
    main()
