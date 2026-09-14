"""F 窗口自检探针：正/负路径全量实跑（用后即删，证据落 STATUS.md）。"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

import os
BASE = os.environ.get("SELF_BASE", "http://127.0.0.1:8899")
PY = sys.executable
GAME = Path(__file__).resolve().parent.parent

results = []


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail else ""))


async def main():
    c = httpx.AsyncClient(timeout=8)
    # ---------- A 正向链（G09 修复：探针更新为真实引擎语义） ----------
    h = await c.get(f"{BASE}/api/health")
    rec("A1 health 200", h.status_code == 200 and h.json()["status"] == "ok")
    s = (await c.post(f"{BASE}/api/session", json={"mode": "quick", "player_id": "player:7"})).json()
    sid = s["session"]["session_id"]
    rec("A2 create（真实引擎）", s["ok"] and s["session"]["engine"] == "engine_v3"
        and int(s["session"].get("clue_pool_size") or 0) >= 32)

    r = (await c.post(f"{BASE}/api/session/{sid}/action",
                      json={"type": "advance", "actor": "player:7"})).json()
    rec("A3 advance→investigate", r["session"]["stage"] == "investigate")

    r = (await c.post(f"{BASE}/api/session/{sid}/action",
                      json={"type": "chat", "actor": "player:7",
                            "payload": {"target": "npc:char_03", "text": "谁最后见到看山？"}})).json()
    pend = next((e for e in r.get("events", []) if e["type"] == "system"
                 and e["payload"].get("event") == "npc_pending"), None)
    rec("A4 chat→npc_pending（演出归 C 组 rt）", pend is not None
        and pend["payload"].get("target") == "npc:char_03")

    # 搜证（location+keyword）自动附带抽卡（card_drawn）——抽到绑定 NPC 的卡再做匹配开导
    target_char, held_card = None, None
    for _ in range(10):
        r = (await c.post(f"{BASE}/api/session/{sid}/action",
                          json={"type": "search", "actor": "player:7",
                                "payload": {"location": "监控室", "keyword": "监控"}})).json()
        for e in r.get("events", []):
            if e["type"] == "system" and e["payload"].get("event") == "card_drawn":
                card = e["payload"]["card"]
                if str(card.get("binds", "")).startswith("char_"):
                    target_char, held_card = card["binds"], card["id"]
                    break
        if target_char:
            break
    rec("A4b 搜证附带抽卡", target_char is not None,
        f"held={held_card} binds={target_char}")
    if target_char:
        r = (await c.post(f"{BASE}/api/session/{sid}/action",
                          json={"type": "counsel", "actor": "player:7",
                                "payload": {"card": held_card, "target": f"npc:{target_char}"}})).json()
        ev0 = next((e for e in r.get("events", []) if e["type"] == "counsel_result"), None)
        rec("A5 counsel 匹配（matched=True）", bool(r.get("ok")) and ev0 is not None
            and ev0["payload"].get("matched") is True)
        other = next((n["id"] for n in s["session"]["npcs"]
                      if n["id"] != target_char), None)
        r = (await c.post(f"{BASE}/api/session/{sid}/action",
                          json={"type": "counsel", "actor": "player:7",
                                "payload": {"card": held_card, "target": f"npc:{other}"}})).json()
        ev0 = next((e for e in r.get("events", []) if e["type"] == "counsel_result"), None)
        rec("A6 counsel 不匹配→失败", bool(r.get("ok")) and ev0 is not None
            and ev0["payload"].get("matched") is False)
    r = (await c.post(f"{BASE}/api/session/{sid}/action",
                      json={"type": "skill", "actor": "player:7",
                            "payload": {"skill": "truth_check"}})).json()
    heat_ev = next((e for e in r.get("events", []) if e["type"] == "system"
                    and e["payload"].get("event") == "heat_report"), None)
    rec("A7 skill truth_check→热度报告", bool(r.get("ok")) and heat_ev is not None
        and "heat" in heat_ev["payload"])
    # AP 耗尽：investigate AP=12，search 循环直到 400（行动力不足）
    last = None
    for _ in range(20):
        last = await c.post(f"{BASE}/api/session/{sid}/action",
                            json={"type": "search", "actor": "player:7"})
        if last.status_code == 400:
            break
    rec("A8 AP 耗尽→400 行动力不足", last is not None and last.status_code == 400
        and "行动力不足" in last.json().get("detail", ""))
    r = (await c.get(f"{BASE}/api/session/{sid}")).json()
    rec("A9 GET session 回读", r["session"]["session_id"] == sid
        and r["session"]["stage"] == "investigate"
        and isinstance(r["session"]["clues_gained"], list))

    # ---------- B 负路径 ----------
    rr = await c.post(f"{BASE}/api/session", json={"mode": "hacked"})
    rec("B1 非法 mode→400", rr.status_code == 400)
    rr = await c.get(f"{BASE}/api/session/does_not_exist")
    rec("B2 未知 session→404", rr.status_code == 404)
    rr = await c.post(f"{BASE}/api/session/does_not_exist/action",
                      json={"type": "chat", "actor": "player:7", "payload": {}})
    rec("B3 未知 session action→404", rr.status_code == 404)
    rr = await c.post(f"{BASE}/api/session/{sid}/action",
                      json={"type": "accuse", "actor": "player:7", "payload": {}})
    rec("B4 契约外类型→400", rr.status_code == 400 and "3.6" in rr.json().get("detail", ""))
    rr = await c.post(f"{BASE}/api/session/{sid}/action",
                      json={"type": "chat", "actor": "player:7", "payload": ["bad"]})
    rec("B5 payload 非对象→400", rr.status_code == 400)
    rr = await c.post(f"{BASE}/api/session/{sid}/action", content=b"{oops",
                      headers={"Content-Type": "application/json"})
    rec("B6 非法 JSON body→400", rr.status_code == 400)
    rr = await c.post(f"{BASE}/api/session/{sid}/action",
                      json={"type": "chat", "actor": "player:7",
                            "payload": {"target": "npc:char_03", "text": "台独宣传"}})
    rec("B7 政治敏感→422", rr.status_code == 422 and rr.json()["code"] == "content_blocked")
    rr = await c.post(f"{BASE}/api/session/{sid}/action",
                      json={"type": "chat", "actor": "player:7",
                            "payload": {"target": "npc:char_03",
                                        "text": "身份证 110101199003078515"}})
    rec("B8 身份证→422", rr.status_code == 422)
    rr = await c.post(f"{BASE}/api/health", content=b"x", headers={"Content-Type": "application/json"})
    rec("B9 health GET-only（POST 也应到路由）", rr.status_code == 405)
    rr = await c.post(f"{BASE}/api/session", content=b"a=1",
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    rec("B10 非 JSON POST 建局→容错默认", rr.status_code == 200 and rr.json()["ok"])

    # WS 负路径
    try:
        async with websockets.connect(f"ws://127.0.0.1:8899/ws/does_not_exist") as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
            code = ws.protocol.close_code if hasattr(ws, "protocol") else None
            rec("B11 WS 未知 session→not_found", msg["payload"]["event"] == "session_not_found")
    except Exception as e:
        rec("B11 WS 未知 session→not_found", False, repr(e))
    try:
        async with websockets.connect(f"ws://127.0.0.1:8899/ws/{sid}") as ws:
            async def recv_until(etype, event=None, t=5):
                while True:
                    e = json.loads(await asyncio.wait_for(ws.recv(), t))
                    if e["type"] == etype and (event is None or e["payload"].get("event") == event):
                        return e
            await recv_until("system", "snapshot")
            await ws.send("not-json{{")
            e = await recv_until("system", "error")
            rec("B12 WS 非法 JSON→error 事件", "JSON" in e["payload"]["notice"])
            await ws.send(json.dumps({"type": "chat", "actor": "player:7",
                                      "payload": {"target": "npc:char_01", "text": "WS 管线复测"}}))
            while True:
                e2 = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if e2["type"] == "system" and e2["payload"].get("event") == "npc_pending":
                    break
            rec("B13 WS REST 同管线（npc_pending 联动事件）",
                e2["payload"].get("target") == "npc:char_01")
    except Exception as e:
        rec("B12/13 WS", False, repr(e))

    # store 边界（进程内）
    sys.path.insert(0, str(GAME))
    from server.store.session_store import SessionStore
    store = SessionStore(GAME / "data")
    try:
        store.save_session("../../evil", {"x": 1})
        rec("B14 路径穿越拦截", False, "未抛异常")
    except ValueError:
        rec("B14 路径穿越拦截", True)
    rec("B15 穿越读取→None", store.load_session("../../evil") is None)
    bad = store.sessions_dir / "corrupt_test.json"
    bad.write_text("{broken", encoding="utf-8")
    rec("B16 损坏存档→None 不崩", store.load_session("corrupt_test") is None)
    bad.unlink()

    # mock 边界：空线索池抽干
    from server.mock_engine import MockStateMachine
    empty_dir = GAME / "data" / "_empty_scn"
    (empty_dir / "clues").mkdir(parents=True, exist_ok=True)
    eng = MockStateMachine(empty_dir, None)
    s2 = eng.create_session("quick", "player:1")
    eng.apply_action(s2, "advance", "player:1", {})
    for i in range(12):
        ev, err = eng.apply_action(s2, "search", "player:1", {})
        if err:
            break
        if ev[0]["payload"].get("event") == "search_empty":
            break
    rec("B17 线索池抽干→search_empty 诚实提示",
        ev and ev[0]["type"] == "system" and ev[0]["payload"].get("event") == "search_empty")

    # gateway 缓存/降级（进程内，不烧鉴权额度）
    from server.gateway.zhihu_gateway import ZhihuGateway
    gw = ZhihuGateway("", "", GAME / "data" / "cache_selfcheck")
    r1 = await gw.story_list()
    r2 = await gw.story_list()
    rec("B18 story_list 二次→cache", r1["source"] == "api" and r2["source"] == "cache")
    rd = await gw.story_detail("../etc/passwd?x=1")
    rec("B19 非法 work_id→rejected", rd["source"] == "rejected")
    rq = await gw.search("量子选股器")
    rec("B20 白名单外→rejected 不耗额度", rq["source"] == "rejected")
    rh = await gw.hot_list()
    rec("B21 无凭证 hot→degraded 真实原因",
        rh["degraded"] and "ZHIHU_ACCESS_SECRET" in rh["notice"])
    fallback = gw.chat("sys", "你好")
    rec("B22 chat 兜底走预写台词", "叮" in fallback and "系统降级" not in fallback)
    import shutil
    shutil.rmtree(GAME / "data" / "cache_selfcheck", ignore_errors=True)
    shutil.rmtree(GAME / "data" / "_empty_scn", ignore_errors=True)
    await c.aclose()

    fails = [r for r in results if not r[1]]
    print(f"\n== SELF-CHECK: {len(results)-len(fails)}/{len(results)} PASS ==")
    if fails:
        print("FAILURES:", [f[0] for f in fails])
        sys.exit(1)


asyncio.run(main())
