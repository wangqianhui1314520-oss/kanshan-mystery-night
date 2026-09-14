#!/usr/bin/env python3
"""录一条给评委看的演示片：首页 → 进局 → 搜证 → 评委线五步 → 画像。"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
ROOT = GAME.parent
OUT = GAME / "data" / "_judge_demo"
BASE = "http://127.0.0.1:8912"
FFMPEG = "C:/ProgramData/chocolatey/bin/ffmpeg.exe"
FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe.exe"
DEMO_URL = "https://qiuzhen-archive-game.app.workbuddy.host/"
W, H = 1920, 1080


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def wait_idle(page, timeout=20000):
    page.wait_for_function(
        "() => window.Store && window.Store.state && !window.Store.state.busy",
        timeout=timeout,
    )


def js(page, code: str, arg=None):
    return page.evaluate(code, arg)


def mark(marks: list, name: str, t0: float):
    marks.append({"name": name, "t": round(time.time() - t0, 2)})
    print(f"  [{marks[-1]['t']:6.1f}s] {name}", flush=True)


def cap(page, n, tag, line):
    page.evaluate(
        """([n, tag, line]) => {
      if (!document.getElementById('jd-style')) {
        const s = document.createElement('style');
        s.id = 'jd-style';
        s.textContent = `
          #jd-cap{position:fixed;left:40px;right:40px;bottom:28px;z-index:2147483000;
            display:flex;align-items:flex-end;gap:14px;pointer-events:none;
            font-family:"Microsoft YaHei","PingFang SC",sans-serif}
          #jd-cap .n{width:54px;height:54px;border-radius:12px;flex:0 0 54px;
            background:linear-gradient(180deg,#0084ff,#4da8ff);color:#fff;
            font-weight:800;font-size:22px;display:grid;place-items:center;
            box-shadow:0 10px 28px rgba(0,132,255,.38)}
          #jd-cap .box{max-width:860px;padding:12px 18px;border-radius:12px;
            background:rgba(7,11,20,.84);border:1px solid rgba(0,132,255,.38);
            backdrop-filter:blur(12px)}
          #jd-cap b{display:block;color:#f5c451;font-size:13px;letter-spacing:.12em}
          #jd-cap p{margin:4px 0 0;color:#dbe6fa;font-size:20px;font-weight:700;line-height:1.35}
        `;
        document.head.appendChild(s);
      }
      let el = document.getElementById('jd-cap');
      if (!el) { el = document.createElement('div'); el.id = 'jd-cap'; document.body.appendChild(el); }
      if (!n) { el.innerHTML = ''; return; }
      el.innerHTML = '<i class="n">'+n+'</i><div class="box"><b>'+tag+'</b><p>'+line+'</p></div>';
    }""",
        [n, tag, line],
    )


def force_mock(page):
    page.evaluate(
        """() => {
      if (window.Store && window.Store.state) window.Store.state.netKind = 'mock';
    }"""
    )


def click_text(page, text: str, timeout=8000) -> bool:
    loc = page.get_by_text(text, exact=False)
    try:
        loc.first.wait_for(state="visible", timeout=timeout)
        loc.first.click(timeout=timeout)
        return True
    except PWTimeout:
        return False


def dismiss_overlays(page):
    page.evaluate(
        """() => {
      const S = window.Store && window.Store.state;
      if (!S) return;
      if (S.showtime && S.showtime.cut) S.showtime.cut = null;
      if (S.recap) S.recap = null;
      if (S.elevator) S.elevator = null;
      const skip = document.querySelector('.st-ac-skip, .st-actcut, .recap-mask .btn');
      if (skip) skip.click();
    }"""
    )


def record() -> tuple[Path, list]:
    OUT.mkdir(parents=True, exist_ok=True)
    marks: list = []
    t0 = time.time()

    with sync_playwright() as p:
        browser = None
        for ch in ("chrome", "msedge"):
            try:
                browser = p.chromium.launch(
                    channel=ch,
                    args=[
                        "--autoplay-policy=no-user-gesture-required",
                        "--disk-cache-size=1",
                    ],
                    headless=False,
                )
                print(f"browser={ch}", flush=True)
                break
            except Exception as e:
                print(f"{ch} skip: {e}", flush=True)
        if browser is None:
            browser = p.chromium.launch(headless=False)

        context = browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=1,
            record_video_dir=str(OUT / "raw"),
            record_video_size={"width": W, "height": H},
        )
        context.add_init_script(
            """
            localStorage.removeItem('kanshan_save_v1');
            localStorage.setItem('kanshan_onboarded_v1', '1');
            """
        )
        page = context.new_page()
        page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_function(
            "() => window.Store && document.querySelector('.card.menu, .btn-start')",
            timeout=30000,
        )
        page.wait_for_timeout(800)
        force_mock(page)
        mark(marks, "menu", t0)
        cap(page, "00", "知乎黑客松 2026 · 跨次元游乐场", "刘看山失踪了。大门写着：不出真相，不出此门。")
        page.wait_for_timeout(3800)

        if not click_text(page, "开 始 调 查"):
            js(page, "() => window.Store.chooseMode('solo')")
        page.wait_for_timeout(1600)
        mark(marks, "seat", t0)
        page.wait_for_timeout(1400)
        if not click_text(page, "确 认 · 进 入 序 章"):
            js(page, "() => window.Store.startVideo()")
        page.wait_for_timeout(4200)
        mark(marks, "opening", t0)
        if not click_text(page, "跳过序章"):
            js(page, "() => window.Store.startGame()")
        page.wait_for_function("() => window.Store.state.phase === 'play'", timeout=20000)
        force_mock(page)
        page.wait_for_timeout(800)
        if page.locator(".st-casefile").count():
            mark(marks, "casefile", t0)
            page.wait_for_timeout(2800)
            click_text(page, "翻开卷宗") or js(page, "() => window.Store.showtimeNext()")
        page.wait_for_timeout(900)
        dismiss_overlays(page)
        page.wait_for_timeout(700)
        force_mock(page)
        mark(marks, "roundtable", t0)
        cap(page, "01", "圆桌 · AI 全员在场", "八个知乎生态拟人嫌疑人。口供会漏，心声漏得更多。")
        page.wait_for_timeout(3800)

        js(page, "() => { window.Store.state.view = 'map'; }")
        page.wait_for_timeout(900)
        mark(marks, "map", t0)
        cap(page, "02", "现场搜证", "别只信他们说的。去监控室，自己看被删掉的八分钟。")
        page.wait_for_timeout(1400)
        js(
            page,
            """() => {
          const btn = [...document.querySelectorAll('button.loc-node')]
            .find(b => (b.textContent || '').includes('监控室'));
          if (btn) btn.click();
        }""",
        )
        page.wait_for_selector(".search-panel, .scene-head", timeout=8000)
        page.wait_for_timeout(2400)
        js(
            page,
            """() => {
          const chip = [...document.querySelectorAll('.chip.pick, .kw-chips button')]
            .find(b => (b.textContent || '').includes('删除'));
          if (chip) chip.click();
        }""",
        )
        page.wait_for_timeout(700)
        click_text(page, "提交搜证") or js(
            page,
            """() => {
          const b = [...document.querySelectorAll('button')].find(x => (x.textContent||'').includes('提交搜证'));
          if (b) b.click();
        }""",
        )
        wait_idle(page)
        page.wait_for_timeout(3400)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        mark(marks, "judge_line", t0)
        force_mock(page)
        js(page, "() => { window.Store.state.netKind = 'mock'; window.Store.startJudgeLine(); }")
        page.wait_for_timeout(1200)
        wait_idle(page)
        page.wait_for_function(
            "() => window.Store.state.view === 'pollution' || document.querySelector('.pc-view')",
            timeout=15000,
        )
        cap(page, "03", "污染对照 · 原文 vs 水军改写", "同一篇知乎真实回答。圈出被植入的 3 处——看起来像操纵的，也可能是原句。")
        if not page.locator("button.pc-span").count():
            js(page, "() => window.Store.send('skill', { kind: 'pollution_open' })")
        page.wait_for_selector("button.pc-span", timeout=15000)
        page.wait_for_function(
            "() => window.Store.state.pollution && window.Store.state.pollution.case && (window.Store.state.pollution.case.spans||[]).length >= 5",
            timeout=12000,
        )
        page.wait_for_timeout(2200)
        idxs = page.evaluate(
            """() => {
          const cas = window.Store.state.pollution.case || {};
          const bank = (window.POLLUTION_CASES || [])
            .concat((window.MOCK && window.MOCK.pollutionCases) || []);
          const full = bank.find(c => c.id === cas.id) || bank[0] || {};
          const want = new Set((full.spans || []).filter(s => s.changed).map(s => s.id));
          const wantText = new Set((full.spans || []).filter(s => s.changed).map(s => (s.text || '').trim()));
          return (cas.spans || []).map((s, i) => {
            if (want.has(s.id) || wantText.has((s.text || '').trim())) return i;
            return -1;
          }).filter(i => i >= 0);
        }"""
        )
        if not idxs:
            idxs = [0, 1, 2]
        for i in idxs[:3]:
            loc = page.locator("button.pc-span").nth(int(i))
            loc.scroll_into_view_if_needed()
            loc.click(force=True)
            page.wait_for_timeout(480)
        if page.locator("button.pc-span.on").count() < 3:
            js(
                page,
                """() => {
              const cas = window.Store.state.pollution.case || {};
              const bank = (window.POLLUTION_CASES || [])
                .concat((window.MOCK && window.MOCK.pollutionCases) || []);
              const full = bank.find(c => c.id === cas.id) || bank[0] || {};
              const want = new Set((full.spans || []).filter(s => s.changed).map(s => s.id));
              (cas.spans || []).forEach((s, i) => {
                if (!want.has(s.id)) return;
                const btn = document.querySelectorAll('button.pc-span')[i];
                if (btn) btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
              });
            }""",
            )
            page.wait_for_timeout(500)
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('button.pc-span.on').length >= 3",
                timeout=6000,
            )
        except PWTimeout:
            pass
        page.wait_for_timeout(800)
        btn = page.locator("button.btn.primary").filter(has_text="提交对照")
        if btn.count() and btn.first.is_enabled():
            btn.first.click()
        else:
            js(
                page,
                """() => {
              const cas = window.Store.state.pollution.case || {};
              const bank = (window.POLLUTION_CASES || [])
                .concat((window.MOCK && window.MOCK.pollutionCases) || []);
              const full = bank.find(c => c.id === cas.id) || bank[0] || {};
              const picks = (full.spans || []).filter(s => s.changed).map(s => s.id);
              window.Store.send('skill', { kind: 'pollution_mark', case: cas.id, picks });
            }""",
            )
        wait_idle(page)
        page.wait_for_function(
            "() => window.Store.state.pollution && window.Store.state.pollution.result",
            timeout=10000,
        )
        page.wait_for_timeout(4800)
        mark(marks, "pollution_done", t0)

        js(page, "() => window.Store.goDemoRail('speak')")
        page.wait_for_timeout(800)
        mark(marks, "chat", t0)
        cap(page, "04", "圆桌留档", "你说的每一句，档案局都在静默记录。")
        page.wait_for_timeout(1400)
        js(
            page,
            """() => {
          const seat = document.querySelector('.cs-seat, .cs-rail-ava');
          if (seat) seat.click();
        }""",
        )
        page.wait_for_timeout(500)
        box = page.locator(".cs-compose input")
        if box.count():
            box.first.click()
            box.first.fill("今晚热搜的节奏，不像自然发酵。")
            page.wait_for_timeout(400)
            page.locator(".cs-compose button").first.click()
            wait_idle(page)
            page.wait_for_timeout(900)
            box.first.fill("可我刚才又觉得，流量酱也许只是被裹挟。")
            page.wait_for_timeout(350)
            page.locator(".cs-compose button").first.click()
            wait_idle(page)
        page.wait_for_timeout(1600)

        js(page, "() => { window.Store.state.heat = 72; window.Store.goDemoRail('echo'); }")
        page.wait_for_timeout(1200)
        wait_idle(page)
        mark(marks, "echo", t0)
        cap(page, "05", "回声自证", "看山把你前后矛盾的两句投影上墙：你连自己都不一，凭什么指认我？")
        page.wait_for_timeout(1800)
        if page.locator(".echo-line").count() < 2:
            click_text(page, "投影回声档案")
            wait_idle(page)
            page.wait_for_selector(".echo-line", timeout=8000)
        lines = page.locator(".echo-line")
        n = lines.count()
        picked = []
        for i in range(n):
            t = lines.nth(i).inner_text()
            if "清白" in t or "撒谎" in t:
                lines.nth(i).click()
                picked.append(i)
                page.wait_for_timeout(400)
        if len(picked) < 2 and n >= 2:
            lines.nth(0).click()
            page.wait_for_timeout(350)
            lines.nth(1).click()
        page.wait_for_timeout(800)
        page.locator("button").filter(has_text="引自证").first.click()
        wait_idle(page)
        page.wait_for_function(
            "() => window.Store.state.echo && (window.Store.state.echo.result || window.Store.state.echo.defended)",
            timeout=10000,
        )
        page.wait_for_timeout(3600)
        mark(marks, "echo_done", t0)

        js(page, "() => { window.Store.state.heat = 72; window.Store.goDemoRail('debate'); }")
        page.wait_for_timeout(800)
        mark(marks, "debate", t0)
        cap(page, "06", "AI 法官", "热度越高，法官越怀疑你。引用实证 + 知识卡，说服一个会被舆论带偏的裁判。")
        if page.locator("text=请法官入席").count():
            click_text(page, "请法官入席")
            wait_idle(page)
        page.wait_for_timeout(1800)
        cites = page.locator(".db-cites button")
        if cites.count() >= 1:
            cites.nth(0).click()
            page.wait_for_timeout(350)
        if cites.count() >= 2:
            cites.nth(1).click()
            page.wait_for_timeout(350)
        admit = page.locator(".db-cites button").filter(has_text="动摇")
        if admit.count():
            admit.first.click()
        ta = page.locator(".db-claim")
        if ta.count():
            ta.first.fill("这些证据说明 21:07 的监控空洞和热搜投放，不是自然发酵。")
        page.wait_for_timeout(800)
        page.locator("button").filter(has_text="提交陈词").first.click()
        wait_idle(page)
        page.wait_for_timeout(2800)
        if ta.count():
            ta.first.fill("本庭应当采信卷宗，而不是被热度带着走。")
        page.wait_for_timeout(500)
        page.locator("button").filter(has_text="提交陈词").first.click()
        wait_idle(page)
        page.wait_for_timeout(3800)
        mark(marks, "debate_done", t0)

        cap(page, "07", "求真画像", "通关不是结束——你拿到一份关于自己媒介素养的五维诊断。")
        js(page, "() => { window.Store.state.netKind = 'mock'; window.Store.goDemoRail('profile'); }")
        page.wait_for_function(
            "() => window.Store.state.ended || window.Store.state.view === 'ending'",
            timeout=15000,
        )
        page.wait_for_timeout(600)
        js(
            page,
            """() => {
          const br = document.querySelector('.boss-reveal');
          if (br) br.click();
          window.Store.state.view = 'ending';
        }""",
        )
        mark(marks, "ending", t0)
        page.wait_for_timeout(7000)
        mark(marks, "review", t0)
        cap(page, "", "", "")
        page.wait_for_timeout(800)

        raw_guess = page.video.path() if page.video else None
        context.close()
        browser.close()

    # Playwright 在 context.close 后才落盘
    raw_dir = OUT / "raw"
    vids = sorted(raw_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not vids:
        raise SystemExit("没有录到 webm")
    raw = OUT / "gameplay.webm"
    shutil.copy2(vids[0], raw)
    (OUT / "marks.json").write_text(json.dumps(marks, ensure_ascii=False, indent=2), encoding="utf-8")
    print("raw:", raw, "size", raw.stat().st_size, flush=True)
    return raw, marks


def render_cards():
    title_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;
  background:
    radial-gradient(1200px 520px at 82% -8%, rgba(0,132,255,.20), transparent 58%),
    radial-gradient(900px 420px at 8% 110%, rgba(245,196,81,.08), transparent 50%),
    #070b14;
  color:#dbe6fa;font-family:"Microsoft YaHei","PingFang SC",sans-serif}}
.wrap{{height:100%;display:flex;flex-direction:column;justify-content:center;padding:0 140px}}
.chip{{display:inline-block;padding:8px 16px;border:1px solid rgba(0,132,255,.45);
  border-radius:999px;color:#4da8ff;letter-spacing:.06em;font-size:18px;margin-bottom:28px}}
h1{{font-size:78px;margin:0;letter-spacing:.04em;font-weight:800}}
h1 span{{color:#0084ff}}
h2{{font-size:38px;margin:14px 0 32px;color:#f5c451;font-weight:700}}
p{{font-size:28px;max-width:1100px;line-height:1.55;color:#c5d4ef}}
.foot{{position:absolute;left:140px;bottom:72px;color:#7f93ba;font-size:20px}}
</style></head><body>
<div class="wrap">
  <div class="chip">知乎黑客松 2026 · 跨次元游乐场 · AI 游戏与互动叙事</div>
  <h1>求真档案局 · <span>看山失踪夜</span></h1>
  <h2>评委演示 · 90 秒看完主创新</h2>
  <p>在信息可以被篡改的时代，用专业与真相破局。<br>规则引擎裁决，AI 只负责演出——对照、回声、法官、画像。</p>
</div>
<div class="foot">首页「开始调查」→ 顶栏「评委线」 · 对照 → 回声 → 法官 → 画像</div>
</body></html>"""

    end_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;
  background:
    radial-gradient(1000px 480px at 70% 0%, rgba(0,132,255,.18), transparent 55%),
    #070b14;
  color:#dbe6fa;font-family:"Microsoft YaHei","PingFang SC",sans-serif}}
.wrap{{height:100%;display:flex;flex-direction:column;justify-content:center;padding:0 140px}}
.chip{{display:inline-block;padding:8px 16px;border:1px solid rgba(245,196,81,.5);
  border-radius:999px;color:#f5c451;font-size:18px;margin-bottom:22px}}
h1{{font-size:52px;margin:0 0 16px;font-weight:800}}
.url{{font-size:28px;color:#4da8ff;margin:10px 0 32px;padding:14px 18px;display:inline-block;
  border:1px solid rgba(0,132,255,.35);border-radius:10px;background:rgba(0,132,255,.08);
  letter-spacing:0;font-family:Consolas,"Microsoft YaHei",monospace}}
ul{{margin:0;padding:0;list-style:none;font-size:24px;line-height:1.9;color:#c5d4ef}}
ul b{{color:#f5c451}}
.foot{{position:absolute;left:140px;bottom:72px;color:#7f93ba;font-size:18px}}
</style></head><body>
<div class="wrap">
  <div class="chip">请评委亲手走一遍 · 约 20 分钟</div>
  <h1>线上 Demo</h1>
  <div class="url">{DEMO_URL}</div>
  <ul>
    <li><b>① 污染对照</b>　圈出知乎原文里被水军植入的 3 处</li>
    <li><b>② 回声自证</b>　指出自己哪两句互相矛盾</li>
    <li><b>③ AI 法官</b>　引用实证 + 知识卡，说服会被热度带偏的裁判</li>
    <li><b>④ 求真画像</b>　通关生成五维媒介素养诊断</li>
  </ul>
</div>
<div class="foot">规则引擎裁决 · AI 永不改判、永不捏造证据 · 求真档案局项目组</div>
</body></html>"""

    (OUT / "title.html").write_text(title_html, encoding="utf-8")
    (OUT / "end.html").write_text(end_html, encoding="utf-8")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.set_content(title_html)
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT / "title.png"), type="png")
        page.set_content(end_html)
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT / "end.png"), type="png")
        browser.close()


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def compose(raw: Path) -> Path:
    render_cards()
    gameplay = OUT / "gameplay.mp4"
    sh([
        FFMPEG, "-y", "-i", str(raw),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an",
        str(gameplay),
    ])
    gdur = probe_duration(gameplay)
    title_d, end_d = 4.6, 6.2
    total = title_d + gdur + end_d
    fade_out_at = max(0.2, gdur - 0.55)

    bgm = GAME / "content" / "assets" / "audio" / "bgm_opening.wav"
    bgm2 = GAME / "content" / "assets" / "audio" / "bgm_roundtable.wav"
    bgm_args = []
    bgm_filter = ""
    if bgm.exists() and bgm2.exists():
        bgm_args = ["-i", str(bgm), "-i", str(bgm2)]
        bgm_filter = (
            f"[2:a]volume=0.18,afade=t=in:st=0:d=0.8,afade=t=out:st=4.2:d=0.6,apad=whole_dur={total}[a1];"
            f"[3:a]aloop=loop=-1:size=20000000,volume=0.13,atrim=0:{total},afade=t=in:st=4.0:d=1.2,afade=t=out:st={total-1.6:.2f}:d=1.5[a2];"
            f"[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
    elif bgm.exists():
        bgm_args = ["-i", str(bgm)]
        bgm_filter = (
            f"[2:a]aloop=loop=-1:size=20000000,volume=0.16,atrim=0:{total},"
            f"afade=t=in:st=0:d=0.8,afade=t=out:st={total-1.6:.2f}:d=1.5[aout]"
        )

    vfilter = (
        f"[0:v]loop=loop=-1:size=1:start=0,trim=duration={title_d},fps=30,format=yuv420p,"
        f"fade=t=in:st=0:d=0.35,fade=t=out:st={title_d-0.45:.2f}:d=0.45,setpts=PTS-STARTPTS[v0];"
        f"[1:v]fps=30,format=yuv420p,fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out_at:.2f}:d=0.5,setpts=PTS-STARTPTS[v1];"
        f"[2:v]loop=loop=-1:size=1:start=0,trim=duration={end_d},fps=30,format=yuv420p,"
        f"fade=t=in:st=0:d=0.3,fade=t=out:st={end_d-0.5:.2f}:d=0.5,setpts=PTS-STARTPTS[v2];"
        f"[v0][v1][v2]concat=n=3:v=1:a=0[vout]"
    )
    # 上面 filter 里 [2:v] 与音频输入编号冲突。改成先做无声拼接，再混音。
    silent = OUT / "silent.mp4"
    sh([
        FFMPEG, "-y",
        "-loop", "1", "-t", str(title_d), "-i", str(OUT / "title.png"),
        "-i", str(gameplay),
        "-loop", "1", "-t", str(end_d), "-i", str(OUT / "end.png"),
        "-filter_complex",
        f"[0:v]fps=30,format=yuv420p,fade=t=in:st=0:d=0.35,fade=t=out:st={title_d-0.45:.2f}:d=0.45[v0];"
        f"[1:v]fps=30,format=yuv420p,fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out_at:.2f}:d=0.5[v1];"
        f"[2:v]fps=30,format=yuv420p,fade=t=in:st=0:d=0.3,fade=t=out:st={end_d-0.5:.2f}:d=0.5[v2];"
        f"[v0][v1][v2]concat=n=3:v=1:a=0[vout]",
        "-map", "[vout]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(silent),
    ])

    final = ROOT / "评委演示.mp4"
    docs = GAME / "docs" / "评委演示.mp4"
    if bgm_filter:
        # silent 是 0，bgm 从 1 起
        mix = bgm_filter.replace("[2:a]", "[1:a]").replace("[3:a]", "[2:a]")
        if bgm.exists() and bgm2.exists():
            mix = (
                f"[1:a]volume=0.18,afade=t=in:st=0:d=0.8,afade=t=out:st=4.2:d=0.6,apad=whole_dur={total}[a1];"
                f"[2:a]aloop=loop=-1:size=20000000,volume=0.13,atrim=0:{total},"
                f"afade=t=in:st=4.0:d=1.2,afade=t=out:st={total-1.6:.2f}:d=1.5[a2];"
                f"[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            cmd = [FFMPEG, "-y", "-i", str(silent), "-i", str(bgm), "-i", str(bgm2),
                   "-filter_complex", mix, "-map", "0:v", "-map", "[aout]",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                   "-movflags", "+faststart", str(final)]
        else:
            mix = (
                f"[1:a]aloop=loop=-1:size=20000000,volume=0.16,atrim=0:{total},"
                f"afade=t=in:st=0:d=0.8,afade=t=out:st={total-1.6:.2f}:d=1.5[aout]"
            )
            cmd = [FFMPEG, "-y", "-i", str(silent), "-i", str(bgm),
                   "-filter_complex", mix, "-map", "0:v", "-map", "[aout]",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                   "-movflags", "+faststart", str(final)]
        sh(cmd)
    else:
        shutil.copy2(silent, final)

    shutil.copy2(final, docs)
    print("FINAL", final, "bytes", final.stat().st_size, "sec", probe_duration(final), flush=True)
    return final


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 等服务起来
    import urllib.request
    for i in range(40):
        try:
            urllib.request.urlopen(BASE, timeout=1)
            break
        except Exception:
            time.sleep(0.4)
    else:
        raise SystemExit(f"服务未就绪：{BASE}")

    raw, marks = record()
    final = compose(raw)
    print(json.dumps({"ok": True, "final": str(final), "marks": marks}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
