#!/usr/bin/env python3
"""《求真档案局 · 看山失踪夜》宣传片录制 —— 单人 / 联机 / 生产工作台 三段。

与 record_judge_demo.py 同一套 playwright 管线（1920x1080 webm → ffmpeg）。
本脚本只负责"录"，剪辑交给 promo_compose.py。
只读游戏数据，不改任何游戏代码。
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
OUT = GAME / "data" / "_promo"
RAW = OUT / "raw"
BASE = "http://127.0.0.1:8899"
W, H = 1920, 1080
MARKS: dict[str, list] = {}


# ----------------------------------------------------------------- 通用小工具
def mark(tag: str, name: str, t0: float) -> None:
    MARKS.setdefault(tag, []).append({"name": name, "t": round(time.time() - t0, 2)})
    print(f"  [{tag}] {MARKS[tag][-1]['t']:6.1f}s  {name}", flush=True)


def wait_idle(page, timeout=20000) -> None:
    page.wait_for_function(
        "() => window.Store && window.Store.state && !window.Store.state.busy", timeout=timeout
    )


def click_text(page, text: str, timeout=6000) -> bool:
    try:
        loc = page.get_by_text(text, exact=False).first
        loc.wait_for(state="visible", timeout=timeout)
        loc.click(timeout=timeout)
        return True
    except (PWTimeout, Exception):
        return False


def click_btn(page, text: str, timeout=6000) -> bool:
    try:
        loc = page.locator("button").filter(has_text=text).first
        loc.wait_for(state="visible", timeout=timeout)
        loc.click(timeout=timeout)
        return True
    except (PWTimeout, Exception):
        return False


STYLE = """
#promo-layer{position:fixed;inset:0;z-index:2147483000;pointer-events:none;
  font-family:"Microsoft YaHei","PingFang SC",sans-serif}
#promo-chap{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:18px;
  background:radial-gradient(1200px 620px at 50% 40%,rgba(10,18,32,.94),rgba(4,7,14,.985));
  opacity:0;transition:opacity .38s ease}
#promo-chap.on{opacity:1}
#promo-chap .num{font-size:26px;letter-spacing:.42em;color:#4da8ff;font-weight:700}
#promo-chap .tt{font-size:96px;font-weight:800;color:#f2f6ff;letter-spacing:.03em;
  text-shadow:0 0 60px rgba(0,132,255,.55)}
#promo-chap .sb{font-size:30px;color:#f5c451;font-weight:700;letter-spacing:.04em}
#promo-chap .ln{width:220px;height:3px;border-radius:2px;
  background:linear-gradient(90deg,transparent,#0084ff,transparent)}
#promo-cap{position:absolute;left:50%;transform:translateX(-50%);bottom:54px;
  max-width:1380px;padding:15px 26px;border-radius:14px;
  background:rgba(6,10,18,.86);border:1px solid rgba(0,132,255,.42);
  backdrop-filter:blur(12px);box-shadow:0 18px 50px rgba(0,0,0,.5);
  opacity:0;transition:opacity .3s ease}
#promo-cap.on{opacity:1}
#promo-cap p{margin:0;color:#e8f0ff;font-size:27px;font-weight:700;line-height:1.4;
  letter-spacing:.01em}
#promo-cap b{color:#f5c451}
#promo-tag{position:absolute;left:44px;top:38px;display:flex;align-items:center;gap:12px;
  padding:10px 20px;border-radius:999px;background:rgba(6,10,18,.8);
  border:1px solid rgba(0,132,255,.45);opacity:0;transition:opacity .3s ease}
#promo-tag.on{opacity:1}
#promo-tag i{width:10px;height:10px;border-radius:50%;background:#0084ff;
  box-shadow:0 0 14px #0084ff}
#promo-tag span{color:#cfe0ff;font-size:21px;font-weight:700;letter-spacing:.06em}
"""


def inject(page) -> None:
    page.evaluate(
        """(css) => {
      if (document.getElementById('promo-style')) return;
      const s = document.createElement('style');
      s.id = 'promo-style'; s.textContent = css;
      document.head.appendChild(s);
      const l = document.createElement('div');
      l.id = 'promo-layer';
      l.innerHTML = '<div id="promo-chap"><div class="num"></div>'
        + '<div class="tt"></div><div class="ln"></div><div class="sb"></div></div>'
        + '<div id="promo-tag"><i></i><span></span></div>'
        + '<div id="promo-cap"><p></p></div>';
      document.body.appendChild(l);
    }""",
        STYLE,
    )


def chapter(page, num: str, title: str, sub: str, hold: float = 2.7) -> None:
    """全屏居中章节卡。"""
    inject(page)
    page.evaluate(
        """(d) => {
      const c = document.getElementById('promo-chap');
      c.querySelector('.num').textContent = d.num;
      c.querySelector('.tt').textContent = d.title;
      c.querySelector('.sb').textContent = d.sub;
      c.classList.add('on');
    }""",
        {"num": num, "title": title, "sub": sub},
    )
    page.wait_for_timeout(int(hold * 1000))


def chapter_off(page) -> None:
    page.evaluate("() => { const c=document.getElementById('promo-chap'); c && c.classList.remove('on'); }")
    page.wait_for_timeout(420)


def caption(page, text: str, tag: str = "") -> None:
    inject(page)
    page.evaluate(
        """(d) => {
      const c = document.getElementById('promo-cap');
      c.querySelector('p').innerHTML = d.text;
      c.classList.add('on');
      const t = document.getElementById('promo-tag');
      const sp = t.querySelector('span');
      if (d.tag) { sp.textContent = d.tag; t.classList.add('on'); }
      else { t.classList.remove('on'); }
    }""",
        {"text": text, "tag": tag},
    )


def caption_off(page) -> None:
    page.evaluate("""() => {
      const c=document.getElementById('promo-cap'); c && c.classList.remove('on');
      const t=document.getElementById('promo-tag'); t && t.classList.remove('on');
    }""")


def shot(page, name: str) -> None:
    try:
        page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception:
        pass


def boot_page(browser, tag: str, url: str = BASE, record: bool = True):
    video_dir = RAW / tag
    if video_dir.exists():
        shutil.rmtree(video_dir, ignore_errors=True)
    ctx = browser.new_context(
        viewport={"width": W, "height": H}, device_scale_factor=1,
        **({"record_video_dir": str(video_dir),
            "record_video_size": {"width": W, "height": H}} if record else {}),
    )
    ctx.add_init_script("localStorage.clear();localStorage.setItem('kanshan_onboarded_v1','1');")
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => window.Store && document.querySelector('.card.menu')", timeout=30000)
    page.wait_for_timeout(900)
    inject(page)
    return ctx, page


def grab_video(tag: str) -> Path:
    d = RAW / tag
    vids = sorted(d.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not vids:
        raise SystemExit(f"{tag}: 没有录到 webm")
    dst = OUT / f"{tag}.webm"
    shutil.copy2(vids[0], dst)
    print(f"  -> {dst.name} {dst.stat().st_size/1e6:.1f}MB", flush=True)
    return dst


# ----------------------------------------------------------------- 段 1：单人
def rec_solo(browser) -> Path:
    tag = "solo"
    t0 = time.time()
    ctx, page = boot_page(browser, tag)
    page.wait_for_timeout(1200)

    chapter(page, "CHAPTER 01", "单 人 模 式", "八个 AI 当事人，一个隐藏的 DM", hold=2.9)
    caption(page, "周五盘点夜，首席荣誉侦探<b>刘看山</b>进档案室后失踪。", "单人模式")
    chapter_off(page)
    page.wait_for_timeout(700)
    mark(tag, "menu", t0)

    if not click_btn(page, "开 始 调 查"):
        page.evaluate("() => window.Store.chooseMode('solo')")
    page.wait_for_timeout(1800)
    mark(tag, "seat", t0)
    caption(page, "领取身份：<b>9 张嫌疑人卡</b>，一张只写给你看的故事本。", "单人模式")
    page.wait_for_timeout(3000)
    shot(page, "solo_1_seat")

    if not click_btn(page, "确 认"):
        page.evaluate("() => window.Store.startVideo()")
    page.wait_for_timeout(1500)
    mark(tag, "opening", t0)
    caption(page, "序章：档案室的门，从里面被反锁了。")
    page.wait_for_timeout(4200)
    shot(page, "solo_2_opening")

    if not click_btn(page, "跳过序章"):
        page.evaluate("() => window.Store.startGame()")
    page.wait_for_function("() => window.Store.state.phase === 'play'", timeout=20000)
    page.wait_for_timeout(1200)
    # 关掉开局自动弹出的故事本 / 重读遮罩，回到圆桌
    page.evaluate("""() => { const S = window.Store;
        try { S.bookletDismiss && S.bookletDismiss(); } catch (e) {}
        try { S.closeMyBook && S.closeMyBook(); } catch (e) {}
        try { S.state.bookOpen = false; } catch (e) {} }""")
    page.wait_for_timeout(900)
    if page.locator(".st-casefile").count():
        mark(tag, "casefile", t0)
        click_btn(page, "翻开卷宗") or page.evaluate("() => window.Store.showtimeNext()")
        page.wait_for_timeout(1600)
    page.evaluate("""() => { const S=window.Store.state;
        if (S.showtime && S.showtime.cut) S.showtime.cut=null;
        if (S.recap) S.recap=null; }""")
    page.wait_for_timeout(900)
    mark(tag, "roundtable", t0)

    # 圆桌：和 AI 说一句话
    caption(page, "圆桌：<b>八个立场不同的当事人</b>。口供会漏，心声漏得更多。", "单人模式")
    page.wait_for_timeout(2200)
    shot(page, "solo_3_roundtable")
    box = page.locator(".cs-compose input")
    if box.count():
        box.first.click()
        box.first.type("刘看山最后出现在档案室，是谁删了那七分钟监控？", delay=26)
        page.wait_for_timeout(400)
        page.locator(".cs-compose button").first.click()
        page.wait_for_timeout(1200)
        try:
            wait_idle(page, timeout=25000)
        except PWTimeout:
            pass
        page.wait_for_timeout(2600)
    mark(tag, "chat", t0)
    shot(page, "solo_4_chat")

    # 搜证
    caption(page, "搜证：去现场自己看。关键词一提交，线索当场入袋。", "单人模式")
    page.evaluate("""() => { const S = window.Store;
        try { S.bookletDismiss && S.bookletDismiss(); } catch (e) {}
        try { S.closeMyBook && S.closeMyBook(); } catch (e) {}
        S.state.bookOpen = false; S.state.skipIce = true; }""")
    page.wait_for_timeout(600)
    try:
        page.locator("button.nav-item", has_text="现场搜证").first.click(timeout=5000)
    except (PWTimeout, Exception):
        page.evaluate("() => { window.Store.state.view = 'map'; }")
    page.wait_for_timeout(1400)
    ok_map = page.evaluate("() => window.Store.state.view === 'map'")
    if not ok_map:
        page.evaluate("() => { window.Store.state.skipIce = true; window.Store.state.view = 'map'; }")
        page.wait_for_timeout(1200)
    mark(tag, "map", t0)
    shot(page, "solo_5_map")
    clicked = page.evaluate(
        """() => {
      const b = [...document.querySelectorAll('button.loc-node')]
        .find(x => (x.textContent||'').includes('监控室'));
      if (b) { b.click(); return true; }
      return false;
    }"""
    )
    print(f"    monitor clicked={clicked}", flush=True)
    try:
        page.wait_for_selector(".search-panel, .scene-head", timeout=10000)
    except PWTimeout:
        shot(page, "solo_5b_map_fail")
        raise SystemExit("搜证面板未出现 —— 见 solo_5b_map_fail.png")
    page.wait_for_timeout(2600)
    # 选关键词（等 AI 回复结束、按钮可用后再提交）
    page.evaluate(
        """() => {
      const chip = [...document.querySelectorAll('.chip.pick, .kw-chips button')]
        .find(x => (x.textContent||'').includes('删除'));
      if (chip) chip.click();
    }"""
    )
    page.wait_for_timeout(900)
    try:
        wait_idle(page, timeout=25000)
    except PWTimeout:
        pass
    page.wait_for_function(
        """() => {
      const b = [...document.querySelectorAll('button')]
        .find(x => (x.textContent||'').includes('提交搜证'));
      return b && !b.disabled;
    }""",
        timeout=20000,
    )
    click_btn(page, "提交搜证")
    try:
        page.wait_for_function("() => window.Store.state.ap < 3", timeout=20000)
    except PWTimeout:
        print("    warn: AP 未扣减，重试提交", flush=True)
        click_btn(page, "提交搜证")
        try:
            page.wait_for_function("() => window.Store.state.ap < 3", timeout=20000)
        except PWTimeout:
            pass
    try:
        wait_idle(page)
    except PWTimeout:
        pass
    page.wait_for_timeout(3200)
    mark(tag, "search", t0)
    shot(page, "solo_6_search")
    caption(page, "监控缺了 <b>21:07 - 21:14</b>。有人先动手，再报警。")
    page.wait_for_timeout(3000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    caption(page, "指认、对峙、AI 法官、求真画像 —— 结局由引擎裁决。", "单人模式")
    page.wait_for_timeout(2800)
    caption_off(page)
    page.wait_for_timeout(600)

    ctx.close()
    v = grab_video(tag)
    return v


# ----------------------------------------------------------------- 段 2：联机
def rec_party(browser) -> tuple[Path, Path]:
    tag_h, tag_g = "party_host", "party_guest"
    t0 = time.time()
    ctx_h, host = boot_page(browser, tag_h)
    host.wait_for_timeout(1000)

    chapter(host, "CHAPTER 02", "联 机 模 式", "房间码一贴，真人队友即刻入座", hold=2.9)
    caption(host, "房主建房 → 队友输 <b>6 位房间码</b> → 空白席位由 AI 补齐。", "联机模式")
    chapter_off(host)
    host.wait_for_timeout(900)
    mark(tag_h, "menu", t0)

    host.locator("details.menu-more summary").click()
    host.wait_for_timeout(500)
    host.locator("button", has_text="房间模式").first.click()
    host.wait_for_function("() => window.Store.state.phase === 'party'", timeout=8000)
    host.wait_for_timeout(1500)
    shot(host, "party_1_lobby")
    host.locator("button", has_text="创 建 房 间").first.click()
    host.wait_for_timeout(3600)
    code = host.evaluate("() => window.Store.state.roomCode")
    mark(tag_h, "room_created", t0)
    print(f"    room={code}", flush=True)
    shot(host, "party_2_host_seat")
    caption(host, f"房间码 <b>{code}</b> · 同一 WiFi 的好友打开链接即可进房。", "联机模式 · 房主视角")
    host.wait_for_timeout(1800)

    ctx_g, guest = boot_page(browser, tag_g, url=f"{BASE}/?room={code}")
    guest.wait_for_function("() => window.Store && window.Store.state.roomCode", timeout=30000)
    guest.wait_for_timeout(3000)
    inject(guest)
    mark(tag_g, "joined", t0)
    shot(guest, "party_3_guest_seat")
    caption(guest, "队友进来了：<b>实时同步</b>，各自领取嫌疑人身份。", "联机模式 · 队友视角")
    guest.wait_for_timeout(2600)

    # 队友选人 → 房主端实时可见
    guest.evaluate(
        """() => {
      const c = [...document.querySelectorAll('.g-card')]
        .find(x => (x.textContent||'').includes('笔上仙'));
      if (c) c.click();
    }"""
    )
    guest.wait_for_timeout(1600)
    caption(host, "房主端同步显示：<b>笔上仙 已被领取</b>。", "联机模式 · 房主视角")
    host.wait_for_timeout(2600)
    shot(host, "party_4_taken")

    host.evaluate(
        """() => {
      const c = [...document.querySelectorAll('.g-card')]
        .find(x => (x.textContent||'').includes('知之者'));
      if (c) c.click();
    }"""
    )
    host.wait_for_timeout(1400)
    caption(guest, "九个席位，真人来了几个就补几个 AI。", "联机模式 · 队友视角")
    guest.wait_for_timeout(2400)

    # 双方进局
    caption(host, "队友就位，一起进序章。", "联机模式 · 房主视角")
    caption(guest, "队友就位，一起进序章。", "联机模式 · 队友视角")
    host.wait_for_timeout(1400)
    click_btn(host, "确 认")
    guest.wait_for_timeout(900)
    click_btn(guest, "确 认")
    host.wait_for_timeout(2200)
    click_btn(host, "跳过序章")
    guest.wait_for_timeout(700)
    click_btn(guest, "跳过序章")
    for pg in (host, guest):
        try:
            pg.wait_for_function("() => window.Store.state.phase === 'play'", timeout=25000)
        except PWTimeout:
            pass
    host.wait_for_timeout(1600)
    for pg in (host, guest):
        pg.evaluate("""() => { const S=window.Store.state;
            if (S.showtime && S.showtime.cut) S.showtime.cut=null;
            if (S.recap) S.recap=null;
            const c=document.querySelector('.st-casefile'); if (c) c.click(); }""")
        pg.wait_for_timeout(900)
        click_btn(pg, "翻开卷宗")
        pg.wait_for_timeout(1200)
    mark(tag_h, "play", t0)
    caption(host, "同一张圆桌：真人队友 + AI 当事人，发言全员可见。", "联机模式 · 房主视角")
    caption(guest, "同一张圆桌：真人队友 + AI 当事人，发言全员可见。", "联机模式 · 队友视角")
    host.wait_for_timeout(3400)
    shot(host, "party_5_play_host")
    shot(guest, "party_5_play_guest")

    box = host.locator(".cs-compose input")
    if box.count():
        box.first.click()
        box.first.type("我这边看到监控 21:07 断了一段，你们呢？", delay=24)
        host.wait_for_timeout(400)
        host.locator(".cs-compose button").first.click()
        host.wait_for_timeout(1500)
        try:
            wait_idle(host, timeout=25000)
        except PWTimeout:
            pass
    host.wait_for_timeout(2800)
    mark(tag_h, "chat", t0)
    shot(host, "party_6_chat_host")
    shot(guest, "party_6_chat_guest")
    caption(guest, "队友说的话，<b>同步上桌</b>。")
    guest.wait_for_timeout(2600)

    caption_off(host)
    caption_off(guest)
    host.wait_for_timeout(600)
    ctx_g.close()
    ctx_h.close()
    vh = grab_video(tag_h)
    vg = grab_video(tag_g)
    return vh, vg


# ------------------------------------------------------------- 段 3：生产工作台
def rec_studio(browser) -> Path:
    tag = "studio"
    t0 = time.time()
    ctx, page = boot_page(browser, tag)
    page.wait_for_timeout(1000)

    chapter(page, "CHAPTER 03", "生 产 工 作 台", "一句话，编译出一本可开玩的剧本", hold=2.9)
    caption(page, "不是表单，是<b>创作管线</b>：钩子 → 本型 → 锁局 → 入座 → 真相 → 过闸。", "开发工作台")
    chapter_off(page)
    page.wait_for_timeout(900)
    mark(tag, "menu", t0)

    if not click_btn(page, "创作一本新剧本"):
        page.evaluate("() => window.Store.openStudio()")
    page.wait_for_function("() => window.Store.state.phase === 'studio'", timeout=8000)
    page.wait_for_timeout(1800)
    shot(page, "studio_1_hook")
    mark(tag, "studio", t0)

    # 点预置钩子
    presets = page.locator("button.sw-preset")
    if presets.count():
        presets.nth(1).click()
        page.wait_for_timeout(1100)
    caption(page, "一句话钩子 —— 整本戏的地基。", "开发工作台")
    page.wait_for_timeout(1900)
    shot(page, "studio_2_hook_filled")

    # 本型
    page.locator("button.sw-step", has_text="02本型").first.click()
    page.wait_for_timeout(1200)
    picks = page.locator("button.sw-pick")
    if picks.count() > 2:
        picks.nth(2).click()
    page.wait_for_timeout(1400)
    caption(page, "七种本型：机制 / 硬核 / <b>阵营</b> / 情感 / 恐怖 / 综艺 / 沉浸。", "开发工作台")
    page.wait_for_timeout(2200)
    shot(page, "studio_3_type")
    mark(tag, "type", t0)

    # 生成
    page.locator("button.sw-step", has_text="01钩子").first.click()
    page.wait_for_timeout(900)
    caption(page, "点一下 —— 剩下的交给编译管线。", "开发工作台")
    page.wait_for_timeout(900)
    page.locator("button.sw-run").first.click()
    page.wait_for_timeout(1200)
    caption(page, "编译中：地点 / 人物 / 线索链 / 真相树 / 角色本。", "开发工作台")
    page.wait_for_function(
        "() => window.Store.state.studioJob && window.Store.state.studioJob.status", timeout=240000
    )
    page.wait_for_timeout(2200)
    mark(tag, "generated", t0)
    job = page.evaluate("""() => {
      const j = window.Store.state.studioJob || {};
      return {status: j.status, ok: (j.gate||{}).ok, title: (j.world||{}).title,
              locs: ((j.world||{}).locations||[]).length,
              chars: (((j.detail||{}).characters)||[]).length,
              clues: (((j.detail||{}).clues)||[]).length,
              nodes: (((j.detail||{}).truth_nodes)||[]).length};
    }""")
    print("    studio job:", json.dumps(job, ensure_ascii=False), flush=True)
    shot(page, "studio_4_generated")

    # 过闸
    page.locator("button.sw-step", has_text="12过闸").first.click()
    page.wait_for_timeout(1600)
    caption(page, "闸门绿：<b>4 人 / 6 地 / 12 条线索</b> —— 结构不达标，不给开玩。", "开发工作台")
    page.wait_for_timeout(2600)
    shot(page, "studio_5_gate")

    # 开局 + 结果 tabs
    page.locator("button.sw-step", has_text="13开局").first.click()
    page.wait_for_timeout(1800)
    caption(page, "产出的本：海报 / 角色 / 证据 / 导演视角。", "开发工作台")
    page.wait_for_timeout(1700)
    shot(page, "studio_6_poster")
    for label, name in (("角色", "studio_7_cast"), ("证据", "studio_8_evidence"), ("导演视角", "studio_9_director")):
        page.locator(".sw-result-tabs button", has_text=label).first.click()
        page.wait_for_timeout(1900)
        shot(page, name)
    mark(tag, "tabs", t0)

    caption(page, "写手写不动的量，管线几秒钟跑完。<b>点一下就开玩</b>。", "开发工作台")
    page.wait_for_timeout(1500)
    click_btn(page, "开这本新本")
    page.wait_for_timeout(3200)
    mark(tag, "play", t0)
    shot(page, "studio_10_play")
    caption(page, "新本已在桌上 —— 自己写的本，自己第一个玩。")
    page.wait_for_timeout(3200)
    caption_off(page)
    page.wait_for_timeout(600)

    ctx.close()
    v = grab_video(tag)
    return v


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = None
        for ch in ("chrome", "msedge"):
            try:
                browser = p.chromium.launch(
                    channel=ch, headless=True,
                    args=["--autoplay-policy=no-user-gesture-required", "--disk-cache-size=1",
                          "--force-device-scale-factor=1"],
                )
                print(f"browser={ch}", flush=True)
                break
            except Exception as e:
                print(f"{ch} skip: {e}", flush=True)
        if browser is None:
            browser = p.chromium.launch(headless=True)

        import sys
        which = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
        if which in ("all", "solo"):
            print("== 段1 单人模式 ==", flush=True)
            rec_solo(browser)
        if which in ("all", "party"):
            print("== 段2 联机模式 ==", flush=True)
            rec_party(browser)
        if which in ("all", "studio"):
            print("== 段3 生产工作台 ==", flush=True)
            rec_studio(browser)
        browser.close()

    (OUT / "marks.json").write_text(json.dumps(MARKS, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(OUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
