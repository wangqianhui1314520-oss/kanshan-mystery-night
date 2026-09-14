#!/usr/bin/env python3
"""诊断 guest 进房流程。"""
from __future__ import annotations

import json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8899"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
    ctx.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
    h = ctx.new_page()
    h.on("console", lambda m: m.type == "error" and print("[h]", m.text[:160], flush=True))
    h.goto(BASE, wait_until="domcontentloaded", timeout=45000)
    h.wait_for_function("() => window.Store && document.querySelector('.card.menu')", timeout=30000)
    h.evaluate("() => { window.Store.chooseMode('party'); }")
    h.wait_for_timeout(1200)
    h.locator("button", has_text="创 建 房 间").first.click()
    h.wait_for_timeout(4000)
    st = h.evaluate("() => ({code: window.Store.state.roomCode, phase: window.Store.state.phase, net: window.Store.state.netKind})")
    print("host:", json.dumps(st, ensure_ascii=False), flush=True)

    ctx2 = browser.new_context(viewport={"width": 1920, "height": 1080})
    ctx2.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
    g = ctx2.new_page()
    g.on("console", lambda m: print("[g]", m.type, m.text[:200], flush=True))
    g.on("pageerror", lambda e: print("[g-pageerror]", str(e)[:250], flush=True))
    g.goto(f"{BASE}/?room={st['code']}", wait_until="domcontentloaded", timeout=45000)
    g.wait_for_timeout(9000)
    print("guest:", json.dumps(g.evaluate(
        "() => ({phase: window.Store.state.phase, code: window.Store.state.roomCode,"
        " mode: window.Store.state.mode, net: window.Store.state.netKind,"
        " sid: window.Store.state.sessionId, busy: window.Store.state.busy})"), ensure_ascii=False), flush=True)
    g.screenshot(path="data/_promo/diag_guest.png")
    browser.close()
