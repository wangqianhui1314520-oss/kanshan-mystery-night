#!/usr/bin/env python3
"""宣传片探测 2：工作室生成流程 + 双窗口联机 + WS 通道诊断。只读。"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8912"
OUT = Path(__file__).resolve().parent.parent / "data" / "_promo_probe"
W, H = 1920, 1080
REPORT: list = []


def note(tag, **kw):
    REPORT.append({"tag": tag, **kw})
    print(json.dumps({"tag": tag, **kw}, ensure_ascii=False)[:1400], flush=True)


def boot(browser, tag):
    ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
    ctx.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
    page = ctx.new_page()
    page.on("console", lambda m: (m.type in ("error", "warning"))
            and note("console_" + tag, type=m.type, text=m.text[:220]))
    page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => window.Store && document.querySelector('.card.menu')", timeout=30000)
    page.wait_for_timeout(1500)
    return ctx, page


def probe_studio(browser):
    ctx, page = boot(browser, "studio")
    try:
        note("net", kind=page.evaluate("() => window.Net.kind()"),
             storeNet=page.evaluate("() => window.Store.state.netKind"))
        page.evaluate("() => window.Store.openStudio()")
        page.wait_for_function("() => window.Store.state.phase === 'studio'", timeout=8000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / "10_studio_step1.png"))

        # 步骤 2：选本型
        page.locator("button.sw-step", has_text="02本型").first.click()
        page.wait_for_timeout(900)
        picks = page.locator("button.sw-pick")
        note("studio_type_opts", n=picks.count(),
             labels=[picks.nth(i).inner_text().strip()[:20] for i in range(min(picks.count(), 8))])
        picks.nth(2).click()
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "11_studio_type.png"))

        # 回钩子确认文案
        page.locator("button.sw-step", has_text="01钩子").first.click()
        page.wait_for_timeout(700)
        page.locator("textarea").first.fill("全员被锁在 24 小时热榜机房里，热搜日志缺了七分钟")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "12_studio_filled.png"))

        # 生成
        page.locator("button.sw-run").first.click()
        note("studio_gen_start", t="now")
        page.wait_for_function(
            "() => window.Store.state.studioJob && window.Store.state.studioJob.status",
            timeout=240000,
        )
        page.wait_for_timeout(2500)
        job = page.evaluate("""() => {
          const j = window.Store.state.studioJob || {};
          return {status: j.status, gateOk: (j.gate||{}).ok, gate: (j.gate||{}),
                  title: (j.world||{}).title, locs: ((j.world||{}).locations||[]).length,
                  chars: (((j.detail||{}).characters)||[]).length,
                  clues: (((j.detail||{}).clues)||[]).length,
                  nodes: (((j.detail||{}).truth_nodes)||[]).length,
                  culprit: (((j.detail||{}).culprit)||{}).name,
                  books: (((j.detail||{}).player_books)||[]).map(b=>b.name),
                  acts: ((j.acts)||[]).length, id: window.Store.state.studioId};
        }""")
        note("studio_job", **job)
        page.screenshot(path=str(OUT / "13_studio_result.png"))
        tabs = page.evaluate("""() => [...document.querySelectorAll('.sw-tab, .sw-result button')]
            .filter(e => e.offsetParent).map(e => (e.textContent||'').trim().slice(0,14))""")
        note("studio_result_tabs", tabs=tabs)
    except Exception as e:
        note("studio_FAIL", err=f"{type(e).__name__}: {e}")
        try:
            page.screenshot(path=str(OUT / "13_studio_FAIL.png"))
        except Exception:
            pass
    ctx.close()


def probe_party(browser):
    ctx1 = None
    ctx2 = None
    try:
        ctx1, p1 = boot(browser, "party1")
        p1.locator("details.menu-more summary").click()
        p1.wait_for_timeout(400)
        p1.locator("button", has_text="房间模式").first.click()
        p1.wait_for_function("() => window.Store.state.phase === 'party'", timeout=8000)
        p1.wait_for_timeout(800)
        p1.locator("button", has_text="创 建 房 间").first.click()
        p1.wait_for_timeout(3000)
        st1 = p1.evaluate("""() => ({code: window.Store.state.roomCode, sid: window.Store.state.sessionId,
            host: window.Store.state.isHost, net: window.Store.state.netKind,
            seat: window.Store.state.phase, url: window.Store.state.shareUrl})""")
        note("party_host", **st1)
        p1.screenshot(path=str(OUT / "20_party_host.png"))

        code = st1.get("code")
        if code:
            ctx2 = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
            ctx2.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
            p2 = ctx2.new_page()
            p2.on("console", lambda m: (m.type == "error")
                  and note("console_party2", text=m.text[:200]))
            p2.goto(f"{BASE}/?room={code}", wait_until="domcontentloaded", timeout=45000)
            p2.wait_for_function("() => window.Store && window.Store.state.phase !== 'boot'", timeout=30000)
            p2.wait_for_timeout(3000)
            note("party_guest", phase=p2.evaluate("() => window.Store.state.phase"),
                 code=p2.evaluate("() => window.Store.state.roomCode"),
                 mode=p2.evaluate("() => window.Store.state.mode"),
                 net=p2.evaluate("() => window.Store.state.netKind"),
                 sid=p2.evaluate("() => window.Store.state.sessionId"))
            p2.screenshot(path=str(OUT / "21_party_guest.png"))

            # 房主侧是否出现队友 / 席位变化
            p1.wait_for_timeout(2000)
            note("party_host_after", seats=p1.evaluate(
                """() => [...document.querySelectorAll('.g-card')].map(e => (e.textContent||'').trim().slice(0,10))"""),
                head=p1.evaluate("() => (document.querySelector('.card h1')||{}).textContent"))
            p1.screenshot(path=str(OUT / "22_party_host_after.png"))
    except Exception as e:
        note("party_FAIL", err=f"{type(e).__name__}: {e}")
    finally:
        for c in (ctx1, ctx2):
            try:
                c and c.close()
            except Exception:
                pass


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--autoplay-policy=no-user-gesture-required"])
        probe_studio(browser)
        probe_party(browser)
        browser.close()
    (OUT / "report2.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
