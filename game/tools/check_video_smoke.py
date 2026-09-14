#!/usr/bin/env python3
"""浏览器真机冒烟：验证「搜证场景层」视频/图片是否真的渲染并可播放。

走通 主菜单 → 房间 → 人物 → 序章 → 地图 → 点击地点，检查 .scene-head 内的
<video>/<img> 实际加载状态（videoWidth / readyState / complete / naturalWidth），
而不只是标签存在。结果打印 + 截图落 data/_smoke_*.png。

用法：python tools/check_video_smoke.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8899"
SHOT = GAME / "data"

# 想验证的地点（地图上的热点文本）
TARGETS = ["快递柜", "档案室", "空调机房", "心晴自习室"]


def dump_buttons(page, tag=""):
    btns = page.eval_on_selector_all(
        "button",
        "els => els.filter(e => e.offsetParent !== null).map(e => e.innerText.trim().replace(/\\s+/g,' ').slice(0,28))",
    )
    print(f"  {tag}可见按钮({len(btns)}): {btns[:14]}")


def main() -> int:
    result = {"steps": [], "scenes": [], "errors": []}
    with sync_playwright() as p:
        # 用系统 Chrome/Edge，避免 playwright 自带 chromium 未安装
        launcher = None
        for ch in ("chrome", "msedge"):
            try:
                launcher = p.chromium.launch(channel=ch, args=["--autoplay-policy=no-user-gesture-required"])
                print(f"[browser] 使用系统 {ch}")
                break
            except Exception as e:
                print(f"[browser] {ch} 不可用: {str(e)[:90]}")
        if launcher is None:
            launcher = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        browser = launcher
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        msgs = []
        failed = []
        page.on("console", lambda m: msgs.append(m.text[:160]) if m.type == "error" else None)
        page.on("pageerror", lambda e: msgs.append(f"PAGEERROR {e}"))
        page.on("response", lambda r: failed.append((r.status, r.url)) if r.status >= 400 else None)

        print("[1] 打开首页")
        page.goto(BASE, wait_until="networkidle", timeout=30000)
        time.sleep(2)
        dump_buttons(page, "首页")
        page.screenshot(path=str(SHOT / "_smoke_01_home.png"))

        # 逐步点击推进：主菜单 → 房间 → 人物 → 序章 → 游戏
        print("\n[2] 推进到游戏（自动点击）")
        for step in range(22):
            phase = page.evaluate("() => (window.Store && window.Store.state && window.Store.state.phase) || '?'")
            has_map = page.locator(".map-view, .loc-dot").count() > 0
            print(f"  step{step}  phase={phase}  map_elems={has_map}")
            if has_map:
                break
            # 跳过序章：<video> 直接触发 ended
            if phase == "video":
                print("     序章视频阶段 → 强制跳过")
                page.evaluate("() => { const v=document.querySelector('video'); if(v){v.pause(); v.dispatchEvent(new Event('ended'));} }")
                time.sleep(1)
                continue
            # 用 DOM click 派发。关键：offsetParent 判不出「被遮挡」，
            # 案件卷宗页(.st-casefile)会盖住后面的「进入下一章」造成死循环点空，
            # 故用 elementFromPoint 做真实命中测试，只点真正在最顶层的按钮。
            prefer = ("地图", "翻开", "搜证", "开始", "创建", "加入", "确认", "选择", "继续", "下一步", "进入")
            avoid = ("返回", "退出", "重置", "说明", "帮助", "设置", "成就", "关于")
            clicked = page.evaluate("""([prefer, avoid]) => {
                const hit = el => {
                    const r = el.getBoundingClientRect();
                    if (r.width < 2 || r.height < 2) return false;
                    const top = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                    return top && (el === top || el.contains(top));
                };
                const bs = Array.from(document.querySelectorAll('button')).filter(hit);
                for (const k of prefer) {
                    const b = bs.find(b => {
                        const t = b.innerText.trim();
                        return t && t.includes(k) && !avoid.some(a => t.includes(a));
                    });
                    if (b) { b.click(); return b.innerText.trim().slice(0, 30); }
                }
                if (bs.length) { bs[bs.length - 1].click(); return bs[bs.length - 1].innerText.trim().slice(0, 30); }
                return null;
            }""", [prefer, avoid])
            print(f"     点击: {clicked}")
            time.sleep(1.5)

        has_map = page.locator(".loc-dot").count() > 0
        print(f"\n  到达地图: {has_map}")
        page.screenshot(path=str(SHOT / "_smoke_02_map.png"))
        result["steps"].append({"reached_map": has_map})
        if not has_map:
            print("  ⚠️ 未进入地图，终止")
            seen, uniq = set(), []
            for st, u in failed:
                if u not in seen:
                    seen.add(u)
                    uniq.append((st, u))
            print("  加载失败资源：")
            for st, u in uniq:
                print(f"    {st}  {u.replace(BASE, '')}")
            if not uniq:
                print("    ✅ 无 404/5xx")
            if msgs:
                print("  console errors:", msgs[:8])
            browser.close()
            return 2

        # 逐个地点：点击 → 检查 scene-head 内的媒体
        print("\n[3] 逐地点检查搜证面板媒体")
        for name in TARGETS:
            hit = page.evaluate("""(name) => {
                const vis = el => el && el.offsetParent !== null;
                const cands = Array.from(document.querySelectorAll('button, .loc-btn, [class*=loc]')).filter(vis);
                const b = cands.find(e => (e.innerText||'').trim().includes(name));
                if (b) { b.click(); return true; }
                return false;
            }""", name)
            if not hit:
                result["scenes"].append({"loc": name, "found": False})
                print(f"  ❌ {name}: 找不到热点")
                continue
            time.sleep(2.2)
            info = page.evaluate("""() => {
                const head = document.querySelector('.scene-head');
                if (!head) return {head:false};
                const v = head.querySelector('video');
                const i = head.querySelector('img');
                return {
                  head: true,
                  video: v ? {
                      src: v.getAttribute('src'),
                      poster: v.getAttribute('poster'),
                      muted: v.muted, loop: v.loop, autoplay: v.autoplay,
                      readyState: v.readyState, networkState: v.networkState,
                      vw: v.videoWidth, vh: v.videoHeight,
                      paused: v.paused, t: +v.currentTime.toFixed(2)
                  } : null,
                  img: i ? {src: i.getAttribute('src'), nw: i.naturalWidth, complete: i.complete} : null,
                  svg: !!head.querySelector('svg')
                };
            }""")
            info["loc"] = name
            info["found"] = True
            result["scenes"].append(info)
            v = info.get("video")
            if v:
                ok = v["readyState"] >= 2 and v["vw"] > 0
                print(f"  {'✅' if ok else '❌'} {name}: video readyState={v['readyState']} {v['vw']}x{v['vh']} "
                      f"muted={v['muted']} loop={v['loop']} paused={v['paused']} t={v['t']}s")
                print(f"       src={v['src']}")
                print(f"       poster={v['poster']}")
            elif info.get("img"):
                print(f"  ⚠️ {name}: 降级为 img {info['img']['nw']}px  {info['img']['src']}")
            else:
                print(f"  ⚠️ {name}: 无 media（svg-scene? {info.get('svg')}）")
            page.screenshot(path=str(SHOT / f"_smoke_03_{name}.png"))
            # 关闭弹窗
            page.evaluate("""() => {
                const m = document.querySelector('.ui-modal');
                if (!m) return;
                const c = m.querySelector('.close')
                      || Array.from(m.querySelectorAll('button')).find(b => {
                             const t = b.innerText.trim();
                             return ['×', '✕', '关闭', 'close'].some(k => t === k || t.includes(k));
                         });
                if (c) c.click();
            }""")
            page.keyboard.press("Escape")
            time.sleep(0.8)

        # 检查招募所有静态资源是否 200
        print("\n[4] 关键资源 HTTP 状态")
        for u in ["/assets/videos/loc_locker_new.mp4", "/assets/videos/loc_ac_new.mp4",
                  "/assets/videos/loc_server_new.mp4", "/assets/videos/loc_hotfeed_new.mp4",
                  "/assets/videos/clue_001_banner_new.mp4", "/assets/videos/clue_009_surveillance_new.mp4",
                  "/assets/images/scene_locker.png",
                  "/assets/images/scene_study_room.png", "/assets/images/card_back.png",
                  "/assets/videos/opening.mp4"]:
            r = page.request.get(BASE + u)
            print(f"  {r.status}  {u}")

        seen, uniq = set(), []
        for st, u in failed:
            if u not in seen:
                seen.add(u)
                uniq.append((st, u))
        print("\n[5] 加载失败的资源（去重后）")
        for st, u in uniq:
            print(f"  {st}  {u.replace(BASE, '')}")
        if not uniq:
            print("  ✅ 无 404/5xx")
        result["failed_requests"] = uniq
        result["errors"] = msgs[:20]
        browser.close()

    out = SHOT / "_smoke_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n结果: {out.relative_to(GAME).as_posix()}")

    bad = [s for s in result["scenes"] if not s.get("found") or
           (s.get("video") and not (s["video"]["readyState"] >= 2 and s["video"]["vw"] > 0))]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
