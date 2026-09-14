"""验证 net.js 的 ?ws= 显式地址建局路径（服务端返回嵌套 session 结构）。

修复的 bug：net.js 只读顶层 `j.session_id`，而 /api/session 返回
`{ok, session:{session_id,...}}`，导致 sessionId 变 undefined，WS 拼成
/ws/undefined → 连上但立刻 session_not_found。

判定：Net.id() 必须是以 s_ 开头的真实对局号，且 Net.kind() == 'ws'。
"""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899"
WS_PARAM = "%7Bsession_id%7D"          # {session_id} 占位符，交给 net.js 自己替换
URL = f"{BASE}/?ws={BASE.replace('http', 'ws')}/ws/{WS_PARAM}"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", args=["--disk-cache-size=1", "--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    print(f"[1] 打开 {URL}")
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(9000)

    sid = page.evaluate("() => (window.Net ? window.Net.id() : 'no-Net')")
    kind = page.evaluate("() => (window.Net ? window.Net.kind() : '-')")
    store_sid = page.evaluate("() => (window.Store ? window.Store.state.sessionId : '-')")
    print(f"[2] Net.id()        = {sid}")
    print(f"[3] Net.kind()      = {kind}")
    print(f"[4] Store.sessionId = {store_sid}")
    print(f"[5] pageerror 数    = {len(errors)}")
    for e in errors[:3]:
        print("    ", e)
    browser.close()

ok = isinstance(sid, str) and sid.startswith("s_") and kind == "ws"
print(f"PROBE RESULT: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
