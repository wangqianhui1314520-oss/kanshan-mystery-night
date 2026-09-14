#!/usr/bin/env python3
"""诊断：studio 生成在 8899 上为何失败。"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8899"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    ctx.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
    page = ctx.new_page()
    page.on("console", lambda m: print("[console]", m.type, m.text[:200], flush=True))
    page.on("response", lambda r: r.url.find("studio") >= 0
            and print("[resp]", r.status, r.url[-60:], flush=True))
    page.on("requestfailed", lambda r: print("[reqfail]", r.url[-60:], r.failure, flush=True))
    page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => window.Store && document.querySelector('.card.menu')", timeout=30000)
    page.wait_for_timeout(1000)
    page.evaluate("() => window.Store.openStudio()")
    page.wait_for_function("() => window.Store.state.phase === 'studio'", timeout=8000)
    page.wait_for_timeout(1500)

    page.locator("button.sw-preset").nth(1).click()
    page.wait_for_timeout(800)
    page.locator("button.sw-step", has_text="02本型").first.click()
    page.wait_for_timeout(800)
    page.locator("button.sw-pick").nth(2).click()
    page.wait_for_timeout(700)
    page.locator("button.sw-step", has_text="01钩子").first.click()
    page.wait_for_timeout(700)
    print("hook:", page.evaluate("() => document.querySelector('textarea') ? document.querySelector('textarea').value.slice(0,40) : ''"), flush=True)
    page.locator("button.sw-run").first.click()
    page.wait_for_timeout(4000)
    print("generating toast/err:", page.evaluate(
        "() => [...document.querySelectorAll('.toast,.st-toast,[class*=toast]')].map(e=>e.textContent.trim().slice(0,60))"), flush=True)
    print("job:", page.evaluate("() => window.Store.state.studioJob && window.Store.state.studioJob.status"), flush=True)
    page.wait_for_timeout(6000)
    print("job2:", page.evaluate("() => window.Store.state.studioJob && window.Store.state.studioJob.status"), flush=True)
    page.screenshot(path="data/_promo/diag_studio.png")
    browser.close()
