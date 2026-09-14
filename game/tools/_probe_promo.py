#!/usr/bin/env python3
"""宣传片探测：确认单人 / 联机 / 工作台三个入口的可达性与选择器。只读，不改游戏。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8912"
OUT = Path(__file__).resolve().parent.parent / "data" / "_promo_probe"
W, H = 1920, 1080


def dump_ui(page, tag: str) -> dict:
    data = page.evaluate(
        """() => {
      const vis = (el) => {
        const r = el.getBoundingClientRect();
        const st = getComputedStyle(el);
        return r.width > 2 && r.height > 2 && st.visibility !== 'hidden' && st.display !== 'none';
      };
      const btns = [...document.querySelectorAll('button')].filter(vis)
        .map(b => ({ t: (b.textContent || '').trim().slice(0, 40), cls: b.className }));
      const inputs = [...document.querySelectorAll('input,textarea')].filter(vis)
        .map(i => ({ tag: i.tagName, ph: i.placeholder || '', cls: i.className, v: (i.value || '').slice(0, 40) }));
      const phase = (window.Store && window.Store.state && window.Store.state.phase) || '?';
      const view = (window.Store && window.Store.state && window.Store.state.view) || '?';
      const heads = [...document.querySelectorAll('h1,h2,h3')].filter(vis).map(h => (h.textContent || '').trim().slice(0, 50));
      return { phase, view, btns, inputs, heads };
    }"""
    )
    data["tag"] = tag
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        ctx.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
        page = ctx.new_page()
        page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_function("() => window.Store && document.querySelector('.card.menu')", timeout=30000)
        page.wait_for_timeout(1200)

        d = dump_ui(page, "menu")
        report.append(d)
        page.screenshot(path=str(OUT / "01_menu.png"))

        # --- 联机：房间模式 ---
        try:
            page.locator("details.menu-more summary").click()
            page.wait_for_timeout(400)
            page.locator("button", has_text="房间模式").first.click()
            page.wait_for_function("() => window.Store.state.phase === 'party'", timeout=8000)
            page.wait_for_timeout(900)
            report.append(dump_ui(page, "party_lobby"))
            page.screenshot(path=str(OUT / "02_party_lobby.png"))
            page.locator("button", has_text="创 建 房 间").first.click()
            page.wait_for_timeout(2500)
            report.append(dump_ui(page, "party_created"))
            page.screenshot(path=str(OUT / "03_party_created.png"))
            report.append({"tag": "party_state", "state": page.evaluate(
                "() => ({code: window.Store.state.roomCode, url: window.Store.state.shareUrl,"
                " host: window.Store.state.isHost, sid: window.Store.state.sessionId,"
                " mode: window.Store.state.mode, net: window.Store.state.netKind})")})
        except Exception as e:
            report.append({"tag": "party_FAIL", "err": f"{type(e).__name__}: {e}"})
            page.screenshot(path=str(OUT / "02_party_FAIL.png"))

        # --- 生产工作台 ---
        try:
            page.evaluate("() => window.Store.openStudio()")
            page.wait_for_function("() => window.Store.state.phase === 'studio'", timeout=8000)
            page.wait_for_timeout(1500)
            report.append(dump_ui(page, "studio_hook"))
            page.screenshot(path=str(OUT / "04_studio_hook.png"), full_page=False)
            report.append({"tag": "studio_steps", "steps": page.evaluate(
                "() => (window.STUDIO && (window.STUDIO.STEPS||[]).map(s=>({id:s.id,name:s.name}))) || []"),
                "types": page.evaluate(
                "() => (window.STUDIO && (window.STUDIO.PACK_TYPES||[]).map(t=>({id:t.id,name:t.name}))) || []")})
        except Exception as e:
            report.append({"tag": "studio_FAIL", "err": f"{type(e).__name__}: {e}"})
            page.screenshot(path=str(OUT / "04_studio_FAIL.png"))

        ctx.close()
        browser.close()

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in report:
        print(json.dumps(r, ensure_ascii=False)[:2000], flush=True)


if __name__ == "__main__":
    sys.exit(main())
