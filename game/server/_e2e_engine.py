"""引擎接线 E2E 实测（走 REST 全链路；两阶段：phase1 建中途档 → 重启服务 → phase2 验证回放重建）。"""
import asyncio
import json
import sys

import httpx

BASE = "http://127.0.0.1:8899"
results = []


def rec(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))


async def act(c, sid, typ, actor="player:1", **payload):
    r = await c.post(f"{BASE}/api/session/{sid}/action",
                     json={"type": typ, "actor": actor, "payload": payload})
    return r


async def main():
    async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
        s = (await c.post(f"{BASE}/api/session",
                          json={"mode": "main", "player_id": "player:1"})).json()
        sid = s["session"]["session_id"]
        rec("E1 create engine_v3", s["session"]["engine"] == "engine_v3"
            and s["session"]["clue_pool_size"] == 32
            and len(s["session"]["npcs"]) == 8,
            f"pool={s['session']['clue_pool_size']}")

        r = await act(c, sid, "advance")
        rec("E2 break_ice→investigate", r.json()["session"]["stage"] == "investigate",
            f"AP={r.json()['session']['actions_left']}")

        # 搜证：看山工位 + 鱼干 → clue_028 (boss_flaw, 默认条件)
        r = await act(c, sid, "search", location="desk_kanshan", keyword="鱼干")
        d = r.json()
        clue_types = [e["type"] for e in d["events"]]
        clue_ids = [e["payload"].get("clue_id") for e in d["events"]
                    if e["type"] == "clue_gained"]
        has_flaw = any(e["type"] == "system" and
                       e["payload"].get("event") == "flaw_progress" for e in d["events"])
        drawn = any(e["type"] == "system" and
                    e["payload"].get("event") == "card_drawn" for e in d["events"])
        rec("E3 search 命中 boss_flaw", "clue_028" in clue_ids and has_flaw and drawn,
            f"events={clue_types} clues={clue_ids}")

        # 对话框触发线索：clue_031（chat:keyword_看山，关门）
        r = await act(c, sid, "chat", target="npc:char_04", text="看山，关门")
        d = r.json()
        got31 = any(e["type"] == "clue_gained" and
                    e["payload"].get("clue_id") == "clue_031" for e in d["events"])
        pending = any(e["type"] == "system" and
                      e["payload"].get("event") == "npc_pending" for e in d["events"])
        rec("E4 chat 关键词触发 clue_031 + NPC 诚实占位", got31 and pending)

        # 获取持有卡，动态配对开导
        sess = (await c.get(f"{BASE}/api/session/{sid}")).json()["session"]
        held = sess["held_cards"]
        rec("E5 抽卡入袋", len(held) >= 1, f"held={held}")
        ks_binds = {}
        # 通过一次本地查询拿 binds（不额外开接口：counsel 后看 matched 即验证）
        target_map = {}
        # 直接尝试：对每张 held 卡，试 char_02/05/06（B 验证的匹配对 kc_05→char_02, kc_01→char_06, kc_06→char_05）
        matched_any, unmatched_any = False, False
        counsel_events = {}
        for card in held:
            for guess in ("char_02", "char_05", "char_06"):
                r = await act(c, sid, "counsel", card=card, target=f"npc:{guess}")
                d = r.json()
                if not d.get("ok"):
                    continue
                ev = d["events"][0]
                if ev["payload"]["matched"]:
                    matched_any = True
                    counsel_events[card] = (guess, ev["payload"].get("effect"))
                    break
                else:
                    unmatched_any = True
        rec("E6 counsel 引擎心病匹配", matched_any and unmatched_any,
            f"{counsel_events}")

        # skill：辟谣（引擎匹配 post_008×kc_01 假定卡在/不在都返回真实结果）
        r = await act(c, sid, "skill", skill="refute", post="post_008", card="kc_01")
        d = r.json()
        kinds = [e["type"] for e in d["events"]] if d.get("ok") else []
        rec("E7 skill refute 产出 hotfeed_refresh", "hotfeed_refresh" in kinds,
            f"kinds={kinds}")
        r = await act(c, sid, "skill", skill="buy_heat", post="post_009")
        d = r.json()
        rec("E8 skill buy_heat", d.get("ok") is not None)

        # advance×4 走完幕循环 → accuse
        stages = []
        for i in range(4):
            r = await act(c, sid, "advance")
            stages.append(r.json()["session"]["stage"])
        rec("E9 幕内轮循环→accuse", stages[-1] == "accuse", f"stages={stages}")

        # 终局：破绽 2/5 指认 DM → dm_mock 群嘲结局（引擎真实裁决）
        r = await act(c, sid, "vote", target="dm")
        d = r.json()
        evs = d["events"]
        ending = next((e for e in evs if e["type"] == "ending"), None)
        rec("E10 vote DM→dm_mock 结局（破绽不足）",
            ending is not None and ending["payload"]["outcome"] == "dm_mock"
            and d["session"]["status"] == "ended",
            f"outcome={ending['payload']['outcome'] if ending else None}")

        # ended 后再动作 → 诚实拒绝
        r = await act(c, sid, "search", location="desk_kanshan", keyword="鱼干")
        rec("E11 ended 后动作→400", r.status_code == 400)

        # E12（phase1 部分）：建中途档（不终局），供服务重启后回放重建验证
        s2 = (await c.post(f"{BASE}/api/session",
                           json={"mode": "quick", "player_id": "player:1"})).json()
        sid2 = s2["session"]["session_id"]
        await act(c, sid2, "advance")
        await act(c, sid2, "search", location="desk_kanshan", keyword="鱼干")
        mid = (await c.get(f"{BASE}/api/session/{sid2}")).json()["session"]
        fp = {"sid": sid2, "stage": mid["stage"], "ap": mid["actions_left"],
              "clues": len(mid["clues_gained"]), "flaw": mid["flaw_count"],
              "acts": len(mid["actions"])}
        print("MID-STATE:", json.dumps(fp, ensure_ascii=False))
        with open("data/_e2e_midstate.json", "w", encoding="utf-8") as f:
            json.dump(fp, f)
        rec("E12p 中途档已落盘（供重启回放验证）", mid["stage"] == "investigate")

    fails = [r for r in results if not r[1]]
    print(f"\n== ENGINE-E2E(P1): {len(results)-len(fails)}/{len(results)} PASS ==")
    if fails:
        print("FAILURES:", fails)
        raise SystemExit(1)


async def phase2():
    """服务重启后执行：验证 actions 日志回放重建（get_engine 路径）。"""
    fp = json.load(open("data/_e2e_midstate.json", encoding="utf-8"))
    sid2 = fp["sid"]
    async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
        # 进程重启后 engines 缓存为空 → 首个动作触发 get_engine 回放重建
        r = await act(c, sid2, "search", location="监控室", keyword="监控")
        ok = r.status_code == 200 and r.json().get("ok")
        s = (await c.get(f"{BASE}/api/session/{sid2}")).json()["session"]
        rec("E12 回放重建后动作连续（actions 单调+1，无回放膨胀）",
            ok and s["stage"] == fp["stage"]
            and len(s["clues_gained"]) >= fp["clues"]
            and s["flaw_count"] >= fp["flaw"]
            and s["actions_left"] <= fp["ap"] - 1
            and len(s["actions"]) == fp["acts"] + 1,
            f"acts: {fp['acts']}→{len(s['actions'])} | "
            f"clues: {fp['clues']}→{len(s['clues_gained'])} | "
            f"ap: {fp['ap']}→{s['actions_left']} | flaw={s['flaw_count']}")

    fails = [r for r in results if not r[1]]
    print(f"\n== ENGINE-E2E(P2): {len(results)-len(fails)}/{len(results)} PASS ==")
    if fails:
        print("FAILURES:", fails)
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "phase2":
        asyncio.run(phase2())
    else:
        asyncio.run(main())
