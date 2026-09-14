#!/usr/bin/env python3
"""定向验证：进地图 → 打开带视频的地点 → 检查 <video> 真实播放。

绕过 check_video_smoke.py 的脆弱自动点击，用 get_by_text 自动等待点击，
专门确认『场景层视频』在真实浏览器里能渲染、能 autoplay(muted)、readyState>=2、videoWidth>0。
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8899"
SHOT = GAME / "data"
TARGETS = ["快递柜", "空调机房", "服务器机房", "热搜后台", "前台", "看山工位", "茶水间", "监控室", "天台"]


def click_text(pg, text, timeout=6000):
    el = pg.get_by_text(text, exact=False).first
    el.click(timeout=timeout)
    return True


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome",
                               args=["--autoplay-policy=no-user-gesture-required"])
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(BASE, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 跳过登录
        click_text(pg, "跳过登录")
        time.sleep(1.5)
        # 进入卷宗 / 圆桌
        click_text(pg, "翻开卷宗")
        time.sleep(1.5)

        # 推进过序章/转场，直到 phase=play
        for _ in range(14):
            phase = pg.evaluate("() => (window.Store && window.Store.state"
                                " && window.Store.state.phase) || '?'")
            if phase == "play":
                break
            # 序章视频直接跳过
            if phase == "video":
                pg.evaluate("() => { const v=document.querySelector('video');"
                            " if(v){v.pause(); v.dispatchEvent(new Event('ended'));} }")
                time.sleep(1)
                continue
            for label in ("开始调查", "下一步", "进入", "继续", "确认"):
                try:
                    click_text(pg, label, timeout=1500)
                    break
                except Exception:
                    continue
            time.sleep(1.2)

        phase = pg.evaluate("() => (window.Store && window.Store.state"
                            " && window.Store.state.phase) || '?'")
        print(f"[phase] {phase}")
        time.sleep(1)

        # 打开场景地图
        click_text(pg, "场景地图", timeout=8000)
        time.sleep(2.5)
        map_ok = pg.locator(".loc-dot, .map-view, [class*=loc-node]").count() > 0
        print(f"[map] rendered={map_ok}")
        pg.screenshot(path=str(SHOT / "_scene_map.png"))

        results = []
        for name in TARGETS:
            try:
                ok = pg.evaluate(
                    """(name) => { const b = [...document.querySelectorAll('button.loc-node')]"""
                    """.find(e => (e.innerText||'').includes(name));"""
                    """ if (b) { b.click(); return true; } return false; }""", name)
                if not ok:
                    raise RuntimeError("no loc-node button")
            except Exception as e:
                results.append({"loc": name, "found": False, "err": str(e)[:80]})
                print(f"  ❌ {name}: 找不到热点")
                continue
            time.sleep(3)
            info = pg.evaluate("""() => {
                const h = document.querySelector('.scene-head');
                if (!h) return {head:false};
                const v = h.querySelector('video');
                const i = h.querySelector('img');
                if (v) return {video:{src:v.src,poster:v.poster,muted:v.muted,
                    loop:v.loop,autoplay:v.autoplay,readyState:v.readyState,
                    networkState:v.networkState,vw:v.videoWidth,vh:v.videoHeight,
                    paused:v.paused,t:+v.currentTime.toFixed(2)}};
                if (i) return {img:{src:i.src,nw:i.naturalWidth,complete:i.complete}};
                return {svg:!!h.querySelector('svg')};
            }""")
            info["loc"] = name
            info["found"] = True
            results.append(info)
            v = info.get("video")
            if v:
                ok = v["readyState"] >= 2 and v["vw"] > 0
                print(f"  {'✅' if ok else '❌'} {name}: readyState={v['readyState']} "
                      f"{v['vw']}x{v['vh']} muted={v['muted']} loop={v['loop']} "
                      f"paused={v['paused']} t={v['t']}s")
                print(f"       src={v['src']}")
            elif info.get("img"):
                print(f"  ⚠️ {name}: 降级 img {info['img']['nw']}px {info['img']['src']}")
            else:
                print(f"  ⚠️ {name}: 无 media (svg={info.get('svg')})")
            pg.screenshot(path=str(SHOT / f"_scene_{name}.png"))
            # 关闭弹窗，回到地图
            pg.keyboard.press("Escape")
            time.sleep(1.2)

        pg.screenshot(path=str(SHOT / "_scene_done.png"))
        out = SHOT / "_scene_play.json"
        out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n结果: {out.relative_to(GAME).as_posix()}")
        b.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
