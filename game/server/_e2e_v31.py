"""V31 增量 E2E（party 席位/minis/零透出/set_round；用后即删，证据落 STATUS.md）。"""
import asyncio
import json

import httpx
import websockets

BASE = "http://127.0.0.1:8899"
results = []


def rec(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))


async def main():
    async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
        # ---------- minis 双路由 ----------
        r = await c.get(f"{BASE}/api/minis/memory-puzzle")
        d = r.json()
        item = d.get("item", {})
        face_keys = sorted(item.keys())
        rec("V1 memory-puzzle rt 池取题（open 题面白名单+缓存头）",
            r.status_code == 200 and d.get("tier") == "open"
            and face_keys == ["heart", "npc", "said"]
            and "max-age" in r.headers.get("cache-control", ""),
            f"face={face_keys} pool={d.get('pool_size')} "
            f"cache={r.headers.get('cache-control', '')[:22]}")
        case_w = ("删除", "监控", "芯片", "打卡", "接头", "水军", "篡改",
                  "权限", "记忆编辑", "仿冒", "备份")
        leak = [w for w in case_w if w in json.dumps(item, ensure_ascii=False)]
        rec("V2 open 题面零 answer/teaching 零案情词",
            not leak and "answer" not in item and "teaching" not in item,
            f"leak={leak or '无'}")
        r = await c.get(f"{BASE}/api/minis/hotfeed-pool", params={"n": 6})
        d = r.json()
        posts = d.get("posts", [])
        bad = [p for p in posts if "is_fake" in p or "clue_ref" in p]
        rec("V3 hotfeed-pool 脱敏抽样（is_fake/clue_ref 零透出）",
            r.status_code == 200 and len(posts) == 6 and not bad
            and all("author_mask" in p for p in posts),
            f"count={len(posts)} pool={d.get('total_pool')}")
        r2 = await c.get(f"{BASE}/api/minis/hotfeed-pool", params={"n": 6})
        rec("V4 可缓存（两次请求一致 200）", r2.status_code == 200
            and len(r2.json().get("posts", [])) == 6)

        # ---------- party 席位（引擎 PartyBoard 接线） ----------
        s = (await c.post(f"{BASE}/api/session",
                          json={"mode": "party", "player_id": "player:1",
                                "max_players": 3})).json()
        sid = s["session"]["session_id"]
        code = s["session"]["room_code"]
        r = await c.post(f"{BASE}/api/session/{sid}/join",
                         json={"room_code": code, "player_id": "1"})
        seats1 = r.json().get("seats")
        rec("V5 join→PartyBoard 席位（无 faction 字段）",
            r.status_code == 200 and seats1
            and all("faction" not in st for st in seats1)
            and sum(1 for st in seats1 if st.get("player_id")) == 1,
            f"owned={sum(1 for st in (seats1 or []) if st.get('player_id'))}")
        await c.post(f"{BASE}/api/session/{sid}/join",
                     json={"room_code": code, "player_id": "2",
                           "char_id": "char_03"})
        sess = (await c.get(f"{BASE}/api/session/{sid}")).json()["session"]
        rec("V6 GET session 零暗置阵营（party 键被剥离）",
            "party" not in sess
            and all("faction" not in p for p in sess.get("players", [])),
            f"players_keys={sorted(set(k for p in sess.get('players', []) for k in p))}")

        # party AP 各算各的：player:1 search 1AP → ap_state 变化
        await act(c, sid, "advance")
        r = await act(c, sid, "search", actor="player:1",
                      location="desk_kanshan", keyword="鱼干")
        d = r.json()
        ap1 = d.get("session", {}).get("ap_state", {})
        rec("V7 party AP 各算各的（pb.spend 生效）",
            d.get("ok") and ap1.get("player:1") == 2, f"ap_state={ap1}")

        # 急诊室轮次注入：counsel 失败→红灯，advance 进下一轮后 er_active 生效
        held = d["session"]["held_cards"]
        if held:
            r = await act(c, sid, "counsel", actor="player:2",
                          card=held[0], target="npc:char_07")
            d2 = r.json()
            matched = d2["events"][0]["payload"]["matched"] if d2.get("ok") else None
            rec("V8 counsel 走引擎（matched 布尔产出）",
                d2.get("ok") and isinstance(matched, bool), f"matched={matched}")

        # ---------- 掉线接管新口径 ----------
        wsp = await websockets.connect(
            f"ws://127.0.0.1:8899/ws/{sid}?player_id=player:2")
        await wsp.recv()
        wss = await websockets.connect(
            f"ws://127.0.0.1:8899/ws/{sid}?spectator=1")
        await wss.recv()
        await wsp.close()

        async def recv_until(ws, pred, t=6):
            while True:
                e = json.loads(await asyncio.wait_for(ws.recv(), t))
                if pred(e):
                    return e
        evt = await recv_until(wss, lambda e: e.get("payload", {}).get("event") == "ai_takeover")
        blob = json.dumps(evt, ensure_ascii=False)
        rec("V9 ai_takeover 只说『该角色已由 AI 接管』",
            evt["payload"]["notice"] == "该角色已由 AI 接管"
            and "pollution" not in blob and "truth" not in blob,
            f"notice={evt['payload']['notice']}")
        sess = (await c.get(f"{BASE}/api/session/{sid}")).json()["session"]
        seats = sess.get("seats") or []
        taken = [st for st in seats if st.get("ai_takeover")]
        rec("V10 PartyBoard.ai_takeover 落席位", bool(taken), f"seats={len(seats)}")
        await wss.close()

        # ---------- 幕切换难度钩子 ----------
        s2 = (await c.post(f"{BASE}/api/session",
                           json={"mode": "main", "player_id": "player:1"})).json()
        sid2 = s2["session"]["session_id"]
        await act(c, sid2, "advance")
        r = await act(c, sid2, "advance")
        d = r.json()
        kinds = [e["payload"].get("event") for e in d["events"]
                 if e["type"] == "system"]
        rec("V11 幕切换产出 difficulty_set（梯度落地）",
            "difficulty_set" in kinds, f"kinds={kinds}")

    fails = [r for r in results if not r[1]]
    print(f"\n== V31-E2E: {len(results)-len(fails)}/{len(results)} PASS ==")
    if fails:
        print("FAILURES:", fails)
        raise SystemExit(1)


async def act(c, sid, typ, actor="player:1", **payload):
    return await c.post(f"{BASE}/api/session/{sid}/action",
                        json={"type": typ, "actor": actor, "payload": payload})


asyncio.run(main())
