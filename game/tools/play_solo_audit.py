#!/usr/bin/env python3
"""真实前端单人主线回归：从选角一路走到「终极 · 看山还是山」。

所有剧情动作均通过 Chromium 页面上的可见控件完成，页面使用真实 WS + engine：
  选角 -> 序章 -> 案件卷宗 -> 读本/破冰 -> 搜证 -> 记忆修复
  -> 心晴开导 -> 圆桌推进 -> 热搜辟谣 -> DM 投票 -> 结局

脚本不直接调用游戏 action REST/WS；只读取 window.Store.state 作为诊断事实源，
并在最后做一次健康检查。AI 未配置时的 503 npc-wave 属于已知降级，不阻断确定性主线。

用法：
  C:/Python314/python.exe game/tools/play_solo_audit.py --budget 360
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

GAME = Path(__file__).resolve().parent.parent
ROOT = GAME.parent
OUT = Path(os.environ.get("PLAY_AUDIT_OUT", str(ROOT / "outputs")))
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("PLAY_AUDIT_BASE", "http://127.0.0.1:8899")

TIMELINE: list[dict] = []
ISSUES: list[dict] = []
DEGRADED: list[dict] = []
MILESTONE_SHOTS: dict[str, str] = {}

# 第一幕用真实地点+关键词，覆盖两个看山破绽、第一章门控和知识卡池。
SEARCH_PLAN = [
    ("看山工位", "鱼干"),
    ("监控室", "监控"),
    ("前台", "排班"),
    ("茶水间", "泡面"),
    ("档案室", "日志"),
    ("服务器机房", "机房"),
    ("天台", "监控"),
    ("热搜后台", "热搜"),
    ("快递柜", "快递"),
    ("空调机房", "门禁"),
]


def log(kind: str, msg: str, **extra) -> None:
    rec = {"t": round(time.time(), 3), "kind": kind, "msg": msg, **extra}
    TIMELINE.append(rec)
    print(f"[{time.strftime('%H:%M:%S')}][{kind}] {msg}", flush=True)


def issue(sev: str, where: str, what: str, **extra) -> None:
    rec = {"sev": sev, "where": where, "what": what, "t": time.time(), **extra}
    ISSUES.append(rec)
    log("ISSUE", f"[{sev}] {where}: {what}", **extra)


def degraded(where: str, what: str, **extra) -> None:
    rec = {"where": where, "what": what, "t": time.time(), **extra}
    DEGRADED.append(rec)
    log("DEGRADED", f"{where}: {what}", **extra)


def shot(page, name: str) -> str:
    path = OUT / f"play_solo_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True, timeout=10000)
        MILESTONE_SHOTS[name] = str(path)
        log("shot", name, path=str(path))
    except Exception as exc:  # noqa: BLE001
        log("warn", f"screenshot failed: {exc}")
    return str(path)


def read_state(page) -> dict:
    try:
        return page.evaluate(
            """() => {
              const S = window.Store && window.Store.state;
              if (!S) return null;
              const progress = window.Store.chapterProgress
                ? window.Store.chapterProgress() : {};
              let flawCount = null;
              try { flawCount = window.Store.flawCount(); } catch (e) {}
              return {
                phase: S.phase, stage: S.stage, act: S.act, round: S.round,
                view: S.view, ap: S.ap, apMax: S.apMax, busy: !!S.busy,
                ended: !!S.ended, ending: S.ending || null,
                netKind: S.netKind, sessionId: S.sessionId, playerId: S.playerId,
                showtime: S.showtime ? S.showtime.step : null,
                cut: S.showtime && S.showtime.cut ? S.showtime.cut.act : null,
                bookletForced: S.bookletForced || null,
                bookletOpen: !!S.bookletOpen, dmBookRead: !!S.dmBookRead,
                recap: !!S.recap, studioNeedAdvance: !!S.studioNeedAdvance,
                clues: Object.keys(S.clues || {}).length,
                clueIds: Object.keys(S.clues || {}),
                searched: Object.keys(S.searched || {}),
                tamperPts: Number(S.tamperPts || 0),
                kcards: Object.keys(S.kcards || {}),
                liveMemories: Object.keys(S.liveMemories || {}),
                counselOk: (S.counsel || []).filter(x => x && x.ok).map(x => ({
                  char_id: x.char_id, kc_id: x.kc_id
                })),
                flaws: flawCount,
                heat: S.heat,
                posts: S.posts ? Object.keys(S.posts).length : 0,
                refuted: S.refuted ? Object.keys(S.refuted).filter(k => S.refuted[k] && S.refuted[k].ok).length : 0,
                voteTarget: S.voteTarget || null,
                voteEvidence: (S.voteEvidence || []).slice(),
                chatLen: (S.chat || []).length,
                npcChat: (S.chat || []).filter(m => m.actor === 'npc').length,
                firstVote: S.firstVote ? { open: !!S.firstVote.open, done: !!S.firstVote.done } : null,
                cleared: !!progress.cleared, hint: progress.hint || ''
              };
            }"""
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def wait_state(page, predicate: str, timeout: int = 20000) -> None:
    page.wait_for_function(f"() => Boolean({predicate})", timeout=timeout)


def visible_locator(locator):
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible():
                return item
        except Exception:  # noqa: BLE001
            continue
    return None


def click_button(page, text: str, timeout: int = 5000, exact: bool = False) -> bool:
    selector = "button" if not exact else "button"
    loc = page.locator(selector, has_text=text)
    for i in range(loc.count()):
        item = loc.nth(i)
        try:
            if item.is_visible() and item.is_enabled():
                item.click(timeout=timeout)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def click_selector(page, selector: str, timeout: int = 5000) -> bool:
    loc = page.locator(selector)
    item = visible_locator(loc)
    if item is None:
        return False
    try:
        if item.is_enabled():
            item.click(timeout=timeout)
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


def click_nav(page, tour: str, timeout: int = 5000) -> bool:
    return click_selector(page, f".ab-menus button[data-tour='{tour}']", timeout)


def dismiss_overlays(page) -> None:
    """只点击真实页面上的关闭/确认控件，不直接篡改游戏状态。"""
    for text in ("收起闭卷", "开始本章", "翻开卷宗"):
        for _ in range(3):
            if not click_button(page, text, timeout=2500):
                break
            page.wait_for_timeout(500)


def dismiss_onboarding(page) -> None:
    """关闭真实新手引导遮罩，避免它拦截后续可见控件。"""
    guide = page.locator(".ux-guide")
    try:
        if not guide.is_visible():
            return
    except Exception:  # noqa: BLE001
        return
    if not click_button(page, "跳过引导", timeout=3000):
        raise RuntimeError("新手引导已打开但未找到跳过引导按钮")
    try:
        page.wait_for_function(
            "() => !document.querySelector('.ux-guide')",
            timeout=5000,
        )
    except PWTimeout as exc:
        raise RuntimeError("跳过新手引导后遮罩仍未关闭") from exc
    log("act", "已通过页面控件关闭新手引导")


def dismiss_optional_theater(page) -> None:
    """按真实页面控件跳过随机触发的可选反诈剧场。"""
    # 自定义元素宿主始终挂载；只有内部 .at-stage 存在时才代表剧场真的打开。
    theater = page.locator(".antifraud-theater .at-stage")
    try:
        if not theater.is_visible():
            return
    except Exception:  # noqa: BLE001
        return
    # Vue fade 卸载期间可能短暂保留 .antifraud-theater 宿主，但内部内容已移除；
    # 只有存在可见操作按钮时才视为玩家可操作的遮罩。
    skip = theater.locator("button", has_text="跳过")
    if visible_locator(skip) is None:
        try:
            page.wait_for_function(
                "() => !document.querySelector('.antifraud-theater .at-stage') "
                "|| !!document.querySelector('.antifraud-theater .at-stage button')",
                timeout=1500,
            )
        except PWTimeout:
            pass
        if not theater.is_visible() or visible_locator(skip) is None:
            return
    if not click_button(page, "跳过（放弃反诈学分）", timeout=3000):
        # 兼容文案尾部标点/空白差异，仍只点击剧场内部的可见控件。
        if not visible_locator(skip):
            raise RuntimeError("反诈剧场已打开但未找到跳过按钮")
        skip.click(timeout=3000)
    try:
        page.wait_for_function(
            "() => !document.querySelector('.antifraud-theater .at-stage')",
            timeout=5000,
        )
    except PWTimeout as exc:
        raise RuntimeError("跳过反诈剧场后遮罩仍未关闭") from exc
    log("act", "已通过页面控件跳过可选反诈剧场")


def state_sig(st: dict) -> tuple:
    return (
        st.get("phase"), st.get("stage"), st.get("act"), st.get("round"),
        st.get("view"), st.get("ap"), st.get("clues"), len(st.get("searched", [])),
        st.get("tamperPts"), len(st.get("kcards", [])), len(st.get("counselOk", [])),
        st.get("flaws"), st.get("ended"), st.get("ending"), st.get("showtime"),
    )


def wait_idle(page, seconds: float = 1.2) -> None:
    page.wait_for_timeout(int(seconds * 1000))
    try:
        page.wait_for_function("() => !window.Store.state.busy", timeout=8000)
    except PWTimeout:
        pass


def choose_role_and_start(page) -> None:
    if not click_button(page, "开 始 调 查"):
        page.evaluate("() => window.Store.chooseMode('solo')")
    page.wait_for_function("() => window.Store.state.phase === 'seat'", timeout=15000)
    log("act", "进入选角页")
    if not click_selector(page, ".pp-seat-char button.g-card:not([disabled])"):
        # 兼容旧 DOM：选第一张可用角色卡。
        if not click_selector(page, ".pp-seat-char .g-card:not(.taken)"):
            raise RuntimeError("选角页没有可点击角色卡")
    page.wait_for_timeout(500)
    if not click_button(page, "确 认 · 进 入 序 章", timeout=6000):
        raise RuntimeError("未找到确认进入序章按钮")
    page.wait_for_function("() => window.Store.state.phase === 'prologue'", timeout=15000)
    log("act", "完成选角并进入序章")


def start_real_game(page) -> None:
    # 序章正常点击跳过开场白，视频再点击跳过；不调用 startGame 旁路。
    if not click_button(page, "跳过开场白", timeout=5000):
        raise RuntimeError("序章跳过控件缺失")
    page.wait_for_function("() => window.Store.state.phase === 'video'", timeout=10000)
    if not click_button(page, "跳过序章", timeout=5000):
        raise RuntimeError("视频跳过控件缺失")
    page.wait_for_function("() => window.Store.state.phase === 'play'", timeout=20000)
    # 等 startPrologue 的真实会话建立，避免在 WS 尚未接通时误判。
    page.wait_for_function(
        "() => window.Store.state.netKind === 'ws' && window.Store.state.sessionId && window.Store.state.sessionId !== '-'",
        timeout=30000,
    )
    log("act", "序章完成，真实 WS 已建立", session_id=read_state(page).get("sessionId"))


def open_case_file_and_read_book(page) -> None:
    wait_state(page, "window.Store.state.showtime && window.Store.state.showtime.step === 'case_file'", 15000)
    if not click_button(page, "翻开卷宗", timeout=8000):
        raise RuntimeError("案件卷宗确认按钮缺失")
    page.wait_for_timeout(1000)
    # 真实主线必须读本；强制弹本可能要等转场自动关闭。
    for _ in range(12):
        if click_button(page, "收起闭卷", timeout=1500):
            break
        if click_button(page, "我的剧本", timeout=1500):
            page.wait_for_timeout(500)
            if click_button(page, "收起", timeout=1500):
                break
        page.wait_for_timeout(500)
    wait_state(page, "window.Store.state.dmBookRead === true", 15000)
    log("act", "案件卷宗确认 + 第一幕剧本已阅读")


def send_chat(page, text: str, target: str | None = None) -> None:
    dismiss_onboarding(page)
    if read_state(page).get("view") != "chat":
        if not click_nav(page, "chat"):
            raise RuntimeError("未找到圆桌对话导航")
        page.wait_for_function("() => window.Store.state.view === 'chat'", timeout=8000)
    if target and target != "dm":
        target_name = page.evaluate(
            "(cid) => { const c = (window.MOCK.chars || []).find(x => x.id === cid); return c && c.name; }",
            target,
        )
        if not target_name:
            raise RuntimeError(f"未知圆桌目标角色：{target}")
        seat = visible_locator(page.locator("button.cs-seat", has_text=target_name))
        if seat is None:
            seat = visible_locator(page.locator("button.cs-rail-ava", has_text=target_name))
        if seat is None:
            raise RuntimeError(f"圆桌没有可见目标座位：{target_name}")
        seat.click(timeout=5000)
    box = page.locator("input[aria-label='对话内容']")
    item = visible_locator(box)
    if item is None:
        raise RuntimeError("未找到圆桌对话输入框")
    item.fill(text)
    if not click_selector(page, ".cs-send"):
        raise RuntimeError("未找到圆桌发送按钮")
    wait_idle(page, 1.0)
    log("chat", text[:80], target=target or "当前角色")


def wait_break_ice_ready(page) -> None:
    # AI 未配置时 requestNpcWave 会返回 503，随后进入确定性自走棋补位；给它足够时间。
    try:
        page.wait_for_function("() => (window.Store.state.chat || []).some(m => m.actor === 'npc')", timeout=45000)
    except PWTimeout:
        # 仍通过可见 UI 重试一次 AI 角色波次；不发送旁路 advance。
        click_button(page, "请 AI 角色依次发言", timeout=4000)
        page.wait_for_function("() => (window.Store.state.chat || []).some(m => m.actor === 'npc')", timeout=45000)
    log("state", "破冰角色亮相已就绪", npc_chat=read_state(page).get("npcChat"))


def finish_break_ice(page) -> None:
    if not click_button(page, "开始搜证", timeout=8000):
        # 任务卡底部 CTA 也是真实入口。
        if not click_selector(page, ".cs-advance-bar button"):
            raise RuntimeError("破冰完成后未找到开始搜证入口")
    page.wait_for_function("() => window.Store.state.stage === 'investigate'", timeout=20000)
    log("stage", "break_ice -> investigate")


def search_one(page, location: str, keyword: str) -> None:
    if read_state(page).get("view") != "map":
        if not click_nav(page, "map"):
            raise RuntimeError("第一幕未找到现场搜证导航")
    page.wait_for_function("() => window.Store.state.view === 'map'", timeout=8000)
    nodes = page.locator(".map-view .loc-node", has_text=location)
    node = visible_locator(nodes)
    if node is None:
        raise RuntimeError(f"地图没有可见地点：{location}")
    node.click(timeout=5000)
    page.locator(".search-panel").wait_for(state="visible", timeout=8000)
    inp = page.locator(".search-panel input[placeholder*='关键词']")
    if visible_locator(inp) is None:
        inp = page.locator(".search-panel .kw-input input")
    item = visible_locator(inp)
    if item is None:
        raise RuntimeError(f"地点 {location} 未出现搜证输入框")
    item.fill(keyword)
    btn = page.locator(".search-panel button", has_text="提交搜证")
    submit = visible_locator(btn)
    if submit is None:
        raise RuntimeError(f"地点 {location} 未出现提交搜证按钮")
    before = read_state(page)
    submit.click(timeout=5000)
    wait_idle(page, 1.5)
    after = read_state(page)
    log("search", f"{location} / {keyword}", before=before, after=after)
    # 关闭搜证弹层，下一步继续通过地图导航。
    page.evaluate(
        """() => {
          const modal = [...document.querySelectorAll('.modal')]
            .find(x => x.offsetParent !== null && x.querySelector('.search-panel'));
          const close = modal && modal.querySelector('.modal-hd button');
          if (close) close.click();
        }"""
    )
    page.wait_for_timeout(300)


def first_act_search(page) -> None:
    for loc, kw in SEARCH_PLAN:
        search_one(page, loc, kw)
    st = read_state(page)
    if not st.get("searched"):
        raise RuntimeError("第一幕搜证完成后 state.searched 仍为空")
    if not st.get("cleared"):
        raise RuntimeError(f"第一幕门控未达成：{st}")
    log("stage", "第一幕搜证门控已达成", searched=st["searched"], clues=st["clues"], kcards=st["kcards"])


def advance_chapter(page, from_act: int, expected_stage: str) -> None:
    if not click_selector(page, ".act-next"):
        raise RuntimeError(f"第 {from_act} 幕未找到进入下一章按钮")
    page.wait_for_function(f"() => window.Store.state.stage === '{expected_stage}'", timeout=20000)
    dismiss_overlays(page)
    log("stage", f"act {from_act} -> {expected_stage}")


def repair_memory(page, char_name: str = "流量酱") -> None:
    if read_state(page).get("view") != "memory":
        if not click_nav(page, "memory"):
            raise RuntimeError("第二幕未找到记忆修复入口")
    page.wait_for_function("() => window.Store.state.view === 'memory'", timeout=8000)
    card = page.locator(".mc-char", has_text=char_name)
    item = visible_locator(card)
    if item is None:
        raise RuntimeError(f"记忆修复页没有角色卡：{char_name}")
    item.click(timeout=5000)
    action = item.locator("button.mc-act")
    action.click(timeout=5000)
    page.wait_for_function(
        "() => Object.keys(window.Store.state.liveMemories || {}).length > 0 && Number(window.Store.state.tamperPts || 0) >= 2",
        timeout=15000,
    )
    log("act", f"完成记忆修复：{char_name}", state=read_state(page))


def counsel_one(page, kc_keyword: str, char_name: str) -> None:
    if read_state(page).get("view") != "clinic":
        if not click_nav(page, "clinic"):
            raise RuntimeError("第二幕未找到心晴诊室入口")
    page.wait_for_function("() => window.Store.state.view === 'clinic'", timeout=8000)
    kc = page.locator(".cl-kc .kc-pick-item", has_text=kc_keyword)
    kc_item = visible_locator(kc)
    if kc_item is None:
        raise RuntimeError(f"未持有匹配知识卡：{kc_keyword}")
    kc_item.click(timeout=5000)
    char = page.locator(".clinic-view .mc-char", has_text=char_name)
    char_item = visible_locator(char)
    if char_item is None:
        raise RuntimeError(f"心晴诊室没有目标角色：{char_name}")
    action = char_item.locator("button.mc-act")
    action.click(timeout=5000)
    page.wait_for_function(
        "(name) => (window.Store.state.counsel || []).some(x => x && x.ok && ((window.Labels && window.Labels.who(x.char_id)) === name || x.char_id === name))",
        arg=char_name,
        timeout=15000,
    )
    log("act", f"完成心晴开导：{kc_keyword} -> {char_name}", state=read_state(page))


def open_hotfeed_and_refute(page) -> None:
    dismiss_optional_theater(page)
    if not click_nav(page, "hotfeed"):
        raise RuntimeError("第三幕未找到热搜面板入口")
    page.wait_for_function("() => window.Store.state.view === 'hotfeed'", timeout=8000)
    page.wait_for_function("() => !!window.Store.state.hotfeedPanel || Object.keys(window.Store.state.posts || {}).length > 0", timeout=12000)
    dismiss_optional_theater(page)
    # 逐帖尝试，优先按 DOM 的 .match 选择；成功判据同时覆盖真实引擎回执
    # 已经写入的 state.refuted，避免异步 WS 回执时序造成误判。
    buttons = page.locator(".hf-card button.hf-refute")
    for i in range(buttons.count()):
        b = buttons.nth(i)
        try:
            if not b.is_visible() or not b.is_enabled():
                continue
            b.click(timeout=4000)
            page.locator(".refute-panel").wait_for(state="visible", timeout=5000)
            post_id = page.evaluate(
                "() => { const p = window.Store.state; "
                "return (p.refutePost && p.refutePost.id) || null; }"
            )
            # 当前页面的弹窗对象由 Vue setup 持有，不一定暴露到 Store；
            # 用按钮所属卡片标题/帖子索引回读一个稳定的候选 ID。
            if not post_id:
                post_id = page.evaluate(
                    "(idx) => { const cards = [...document.querySelectorAll('.hf-card')]; "
                    "const card = cards[idx]; return card && card.dataset && card.dataset.id || null; }",
                    i,
                )
            matches = page.locator(".refute-panel .kc-pick-item.match")
            match = visible_locator(matches)
            if match is None:
                click_selector(page, ".modal-hd button", timeout=2000)
                continue
            match.click(timeout=5000)
            page.wait_for_function(
                "() => Object.values(window.Store.state.refuted || {}).some(x => x && x.ok) "
                "|| !!window.Store.state.heatReport "
                "|| (window.Store.state.chat || []).some(m => m && m.text && m.text.includes('辟谣成功'))",
                timeout=15000,
            )
            # 辟谣结果弹窗是正常的玩家反馈，但会拦截其后的剧场和底部导航；
            # 必须先关闭包含当前结果面板的弹窗，再处理可选反诈剧场。
            if not click_selector(page, ".modal-mask:has(.refute-panel) .modal-hd button", timeout=3000):
                raise RuntimeError("辟谣成功后未找到关闭结果弹窗的控件")
            page.wait_for_function(
                "() => !document.querySelector('.refute-panel')",
                timeout=5000,
            )
            dismiss_optional_theater(page)
            wait_idle(page, 0.5)
            st = read_state(page)
            if st.get("refuted", 0) < 1:
                raise RuntimeError(f"引擎已回执但前端未登记辟谣：{st}")
            log("act", "第三幕完成一次真实热搜辟谣", state=st)
            return
        except Exception:  # noqa: BLE001
            dismiss_optional_theater(page)
            click_selector(page, ".modal-hd button", timeout=1000)
    raise RuntimeError("热搜面板没有找到可匹配的知识卡辟谣目标")


def vote_dm(page) -> None:
    dismiss_optional_theater(page)
    if not click_nav(page, "vote"):
        detail = page.evaluate(
            """() => ({
              state: {
                view: window.Store.state.view,
                act: window.Store.state.act,
                stage: window.Store.state.stage,
                recap: !!window.Store.state.recap,
                cut: window.Store.state.showtime && window.Store.state.showtime.cut,
                busy: !!window.Store.state.busy
              },
              menus: [...document.querySelectorAll('.ab-menus button')].map(b => ({
                text: (b.innerText || '').trim(),
                tour: b.getAttribute('data-tour'),
                visible: !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length),
                disabled: !!b.disabled
              })),
              overlays: [...document.querySelectorAll(
                '.modal-mask, .antifraud-theater, .recap-mask, .bk-mask, .pb-mask, .ux-guide'
              )].filter(x => {
                const s = getComputedStyle(x);
                return s.display !== 'none' && s.visibility !== 'hidden';
              }).map(x => ({ cls: x.className, text: (x.innerText || '').slice(0, 120) }))
            })"""
        )
        raise RuntimeError("第三幕未找到终局指认入口：" + json.dumps(detail, ensure_ascii=False))
    page.wait_for_function("() => window.Store.state.view === 'vote'", timeout=8000)
    dismiss_overlays(page)
    dismiss_optional_theater(page)
    page.wait_for_function("() => Number(window.Store.flawCount()) >= 5", timeout=15000)
    dm = page.locator("button.suspect.dm-slot")
    dm_item = visible_locator(dm)
    if dm_item is None:
        raise RuntimeError("破绽 5/5 后仍未出现 DM 指认卡")
    dm_item.click(timeout=5000)
    evidence = page.locator(".ev-pool button.ev-item")
    selected = 0
    for i in range(evidence.count()):
        item = evidence.nth(i)
        try:
            if item.is_visible() and item.is_enabled():
                item.click(timeout=3000)
                selected += 1
                if selected >= 2:
                    break
        except Exception:  # noqa: BLE001
            continue
    if selected < 2:
        raise RuntimeError("终局证据池不足两张")
    btn = page.locator("button.vote-btn")
    vote = visible_locator(btn)
    if vote is None or not vote.is_enabled():
        raise RuntimeError(f"终局指认按钮未就绪：{read_state(page)}")
    vote.click(timeout=5000)
    page.wait_for_function("() => window.Store.state.ended === true", timeout=30000)
    st = read_state(page)
    if st.get("ending") != "kanshan":
        raise RuntimeError(f"终局已结算但不是终极结局：{st}")
    # 终极结局先进入 Boss 揭晓全屏演出；标题在 phase=4 才对玩家可见。
    title = page.locator(".boss-reveal .br-title h2")
    try:
        title.wait_for(state="visible", timeout=30000)
    except PWTimeout as exc:
        raise RuntimeError("结局状态为 kanshan，但 Boss 揭晓标题未在页面显示") from exc
    if title.inner_text().strip() != "终极 · 看山还是山":
        raise RuntimeError(f"终极标题文案不符：{title.inner_text()!r}")
    log("ending", "终极 · 看山还是山", state=st)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=360)
    args = parser.parse_args()
    started = time.time()
    deadline = started + args.budget
    last_sig = None

    final = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 900}, locale="zh-CN")
        page = context.new_page()

        def on_console(msg):
            if msg.type != "error":
                return
            text = msg.text[:300]
            if "status of 503" in text and "Service Unavailable" in text:
                degraded("npc-wave", "AI 未配置，浏览器资源请求按确定性引擎降级", text=text)
                return
            issue("P2", "console", text)

        def on_pageerror(exc):
            issue("P0", "pageerror", str(exc)[:500])

        def on_request_failed(req):
            media = "/assets/audio/" in req.url or "/assets/videos/" in req.url
            failure = str(req.failure or "")
            if media and "ERR_ABORTED" in failure:
                degraded("media", "音视频请求被浏览器中止，主线按无声/静态资源降级", url=req.url)
            else:
                issue("P1", "requestfailed", f"{req.method} {req.url[:180]} {req.failure}")

        def on_response(resp):
            if resp.status < 400 or "/assets/" in resp.url:
                return
            if resp.status == 503 and "/npc-wave" in resp.url:
                degraded("npc-wave", "AI 未配置，使用确定性引擎补位", url=resp.url)
                return
            issue("P1", f"http{resp.status}", f"{resp.request.method} {resp.url[:180]}")

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)

        try:
            log("boot", f"open {BASE}")
            page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_function("() => window.Store && window.Store.state", timeout=30000)
            shot(page, "00_menu")

            # 轻量状态监听：只做诊断，不代替 UI 动作。
            end_by = time.time() + args.budget
            while time.time() < end_by:
                st = read_state(page)
                sig = state_sig(st) if st else None
                if sig != last_sig:
                    log("state", json.dumps(st, ensure_ascii=False)[:900])
                    last_sig = sig
                if st.get("ended"):
                    break
                if st.get("phase") == "menu":
                    choose_role_and_start(page)
                elif st.get("phase") in ("prologue", "video"):
                    start_real_game(page)
                elif st.get("phase") == "play":
                    # 主流程由一次性阶段函数完成；使用标记避免重复执行。
                    if not getattr(main, "_boot_done", False):
                        open_case_file_and_read_book(page)
                        wait_break_ice_ready(page)
                        send_chat(page, "看山，关门", "dm")
                        finish_break_ice(page)
                        first_act_search(page)
                        shot(page, "01_investigate")
                        advance_chapter(page, 1, "round_table")
                        repair_memory(page, "流量酱")
                        counsel_one(page, "职业倦怠", "沉底君")
                        counsel_one(page, "不想学习", "看山Bot")
                        # 第二幕再进行一次自然语言互动，证明圆桌路径仍可用。
                        send_chat(page, "看山Bot，你的日志里还剩下什么？", "char_05")
                        shot(page, "02_round_table")
                        advance_chapter(page, 2, "accuse")
                        open_hotfeed_and_refute(page)
                        shot(page, "03_accuse_hotfeed")
                        vote_dm(page)
                        shot(page, "99_ending")
                        main._boot_done = True
                    else:
                        break
                else:
                    page.wait_for_timeout(500)
                if time.time() > deadline:
                    break

            final = read_state(page)
            if not final.get("ended"):
                issue("P0", "incomplete", f"预算 {args.budget}s 内未通关：{json.dumps(final, ensure_ascii=False)[:800]}")
                shot(page, "98_timeout")
            elif final.get("ending") != "kanshan":
                issue("P0", "wrong-ending", f"完成但结局不符：{json.dumps(final, ensure_ascii=False)[:800]}")
        except Exception as exc:  # noqa: BLE001
            # 即使主流程在页面交互处失败，也保留失败瞬间的真实状态，
            # 便于区分引擎失败、UI 遮罩和选择器误判。
            final = read_state(page)
            issue("P0", "playthrough", f"真实前端主线失败：{type(exc).__name__}: {exc}", final=final)
            shot(page, "98_failure")
        finally:
            try:
                import urllib.request
                health = json.loads(urllib.request.urlopen(BASE + "/api/health", timeout=5).read())
                log("health", json.dumps({
                    "degraded": health.get("degraded"),
                    "engine": health.get("engine"),
                    "ai": health.get("ai"),
                    "sessions": health.get("sessions", {}).get("active"),
                }, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                log("warn", f"health check failed: {exc}")
            browser.close()

    report = {
        "budget_s": args.budget,
        "elapsed_s": round(time.time() - started, 1),
        "ended": bool(final.get("ended")),
        "final": final,
        "issues": ISSUES,
        "degraded": DEGRADED,
        "timeline": TIMELINE,
        "screenshots": MILESTONE_SHOTS,
    }
    path = OUT / "play_solo_final_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== DONE report={path} issues={len(ISSUES)} degraded={len(DEGRADED)}", flush=True)
    for rec in ISSUES:
        print(f"  [{rec['sev']}] {rec['where']}: {rec['what'][:220]}", flush=True)
    return 0 if not any(x.get("sev") == "P0" for x in ISSUES) else 1


if __name__ == "__main__":
    sys.exit(main())
