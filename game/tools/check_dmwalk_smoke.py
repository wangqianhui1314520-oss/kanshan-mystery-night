#!/usr/bin/env python3
"""dm-walk 雪碧图动画回归守护（只读）

背景：2026-09-13 发现 .dm-walk 基础规则与 @keyframes dm-walk-steps 在重构中丢失，
chat/电梯/侦探证/复盘共 6 处 DM 看山形象不可见。图源已升级 kanshan_big.png（@2x 30 帧）。
本脚本验证三件事：
  1. kanshan_big.png HTTP 200
  2. .dm-walk 计算样式解析到该背景图
  3. steps 动画真实推进 background-position-x（取两次采样对比）
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8899"


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome",
                              args=["--autoplay-policy=no-user-gesture-required"])
        pg = b.new_page(viewport={"width": 1280, "height": 900})

        # 1) 图源可达
        resp = pg.request.get(f"{BASE}/assets/official/kanshan/kanshan_big.png")
        print(f"[asset] kanshan_big.png -> {resp.status} {resp.headers.get('content-type', '')}")
        ok_asset = resp.status == 200

        pg.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(2500)  # 等 Vue 挂载 + CSS 就绪

        # 2+3) 探针元素：模拟组件内联样式（scale=0.42，与电梯用法一致）
        probe = pg.evaluate(
            """
            () => new Promise(res => {
              const el = document.createElement('span');
              el.className = 'dm-walk';
              el.style.cssText = 'width:46px;height:52px;'
                + 'background-size:462px 155px;background-position-y:-52px;'
                + '--dmw-end:-462px;animation:dm-walk-steps 0.7s steps(9) infinite;';
              document.body.appendChild(el);
              const cs = getComputedStyle(el);
              const bg = cs.backgroundImage || '';
              const p0 = cs.backgroundPositionX;
              setTimeout(() => {
                const p1 = getComputedStyle(el).backgroundPositionX;
                res({ bg, p0, p1 });
              }, 500);
            })
            """
        )
        bg = probe["bg"]
        ok_bg = "kanshan_big" in bg
        moved = probe["p0"] != probe["p1"]
        print(f"[css]   background-image = {bg[:90]}")
        print(f"[anim]  position-x {probe['p0']} -> {probe['p1']}  moved={moved}")
        el_ok = ok_bg and moved

        b.close()
        print("=" * 50)
        print(f"结果: asset={ok_asset} css_bg={ok_bg} anim_moved={moved}")
        if ok_asset and el_ok:
            print("✅ dm-walk 修复生效：图源/规则/动画三项全过")
            return 0
        print("❌ dm-walk 仍有问题")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
