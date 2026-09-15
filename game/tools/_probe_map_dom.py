#!/usr/bin/env python3
"""快速探针：进 investigate 阶段后 dump 地图视图 DOM，定位 autoplay 搜证失配。"""
import os
import time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("PLAY_AUDIT_BASE", "http://127.0.0.1:8911")

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 1600, "height": 900}, locale="zh-CN").new_page()
    page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_function("() => window.Store && window.Store.state", timeout=30000)
    page.evaluate("() => window.Store.chooseMode('solo')")
    time.sleep(1.5)
    page.evaluate("() => window.Store.startVideo && window.Store.startVideo()")
    time.sleep(1.5)
    page.evaluate("() => window.Store.startGame && window.Store.startGame()")
    page.wait_for_function("() => window.Store.state.phase === 'play'", timeout=20000)
    time.sleep(3)
    page.evaluate("() => window.Store.send('advance', {})")
    page.wait_for_function("() => window.Store.state.stage === 'investigate'", timeout=15000)
    page.evaluate("() => { window.Store.state.view = 'map'; }")
    time.sleep(2.5)
    info = page.evaluate(
        """() => {
          const S = window.Store.state;
          const nodes = [...document.querySelectorAll('.loc-node')];
          const M = window.Store.M || {};
          return {
            view: S.view, stage: S.stage, ap: S.ap, act: S.act, round: S.round,
            mLocs: (M.locations || []).map(l => l.id + ':' + l.name + (l.hidden ? ':hidden' : '')),
            locNodeCount: nodes.length,
            locNodes: nodes.map(n => ({cls: n.className, disabled: n.disabled,
                                       visible: n.offsetParent !== null,
                                       text: n.textContent.trim().slice(0, 20)})),
            kwInputs: [...document.querySelectorAll('.kw-input input')].map(i => ({
                                       visible: i.offsetParent !== null, maxLength: i.maxLength,
                                       placeholder: i.placeholder})),
            submitBtns: [...document.querySelectorAll('button')].filter(b => b.textContent.includes('提交搜证'))
                                       .map(b => ({visible: b.offsetParent !== null, disabled: b.disabled,
                                                   text: b.textContent.trim()})),
            mapViewExists: !!document.querySelector('.map-view'),
            bodyClasses: document.body.className,
          };
        }""")
    import json
    print(json.dumps(info, ensure_ascii=False, indent=2))
    # 尝试完整一次搜证
    r = page.evaluate(
        """() => {
          const n = [...document.querySelectorAll('.loc-node.hot')].find(x => x.offsetParent !== null);
          if (!n) return 'no-hot-node';
          n.click();
          return 'clicked:' + n.textContent.trim().slice(0, 12);
        }""")
    print("node click:", r)
    time.sleep(1.5)
    r2 = page.evaluate(
        """() => {
          const ins = [...document.querySelectorAll('.kw-input input')].filter(i => i.offsetParent !== null && i.maxLength > 4);
          if (!ins.length) return 'no-kw-input';
          const i = ins[0]; i.value = '监控';
          i.dispatchEvent(new Event('input', {bubbles: true}));
          const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.includes('提交搜证') && b.offsetParent !== null);
          if (!btns.length) return 'no-submit-btn';
          btns[0].click();
          return 'submitted';
        }""")
    print("search submit:", r2)
    time.sleep(3)
    st = page.evaluate(
        """() => { const S = window.Store.state;
             return { ap: S.ap, clues: Object.keys(S.clues||{}), searched: S.searched,
                      lastToast: (window.Store.state.toasts||[]).slice(-2) }; }""")
    print(json.dumps(st, ensure_ascii=False, indent=2))
    b.close()
