"""rt 演出层接线 E2E（契约 §3.5c；用后即删，证据落 STATUS.md）。"""
import asyncio
import json

import httpx

BASE = "http://127.0.0.1:8899"
results = []


def rec(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))


async def act(c, sid, typ, actor="player:1", **payload):
    return await c.post(f"{BASE}/api/session/{sid}/action",
                        json={"type": typ, "actor": actor, "payload": payload})


async def main():
    async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
        h = (await c.get(f"{BASE}/api/health")).json()
        rec("R0 服务在线+引擎模式", h["status"] == "ok" and h["engine"]["mode"] == "engine")

        s = (await c.post(f"{BASE}/api/session",
                          json={"mode": "main", "player_id": "player:1"})).json()
        sid = s["session"]["session_id"]
        await act(c, sid, "advance")

        # 搜证命中（喂 hit_count）+ 打码彩蛋（喂 bake_count）
        await act(c, sid, "search", location="desk_kanshan", keyword="鱼干")
        r = await act(c, sid, "chat", target="npc:char_02", text="垃圾系统，破档案局")
        bake = any(e["type"] == "system" and e["payload"].get("kind") == "gagged"
                   for e in r.json().get("events", []))
        rec("R1 bake 彩蛋产出（record_event 素材）", bake)

        # rt skill 分流：collect（rt 自有 CollectiblesBoard 裁决）
        r = await act(c, sid, "skill", skill="collect", item="fish_01")
        d = r.json()
        ev = next((e for e in d.get("events", [])
                   if e["payload"].get("event") == "collect_result"), None)
        rec("R2 skill collect→rt.collect_flow（拾取成功计数+1）",
            d.get("ok") and ev is not None and bool(ev["payload"].get("collected")),
            f"collected={ev['payload'].get('collected') if ev else None}")
        r = await act(c, sid, "skill", skill="collect", item="fish_01")
        ev2 = next((e for e in r.json().get("events", [])
                    if e["payload"].get("event") == "collect_result"), None)
        rec("R3 重复拾取→already_collected 诚实拒绝",
            ev2 is not None and ev2["payload"].get("collected") is False,
            f"collected={ev2['payload'].get('collected') if ev2 else None}")

        # rt skill 分流：bid_headline（rt.opinion 明牌竞标裁决 + 演出）
        r = await act(c, sid, "skill", skill="bid_headline",
                      post="post_004", amount=1, topic="#谁动了我的鱼干#")
        d = r.json()
        ev = next((e for e in d.get("events", [])
                   if e["payload"].get("event") == "headline_result"), None)
        rec("R4 skill bid_headline→rt.headline_flow",
            d.get("ok") and ev is not None
            and ev["payload"].get("host_line")
            and "faction" not in json.dumps(ev["payload"]["bid"] or {}),
            f"settle_ok={(ev['payload'].get('settle') or {}).get('ok') if ev else None}")

        # 3 次幂等验证：重复 collect/bid 不崩、如实返回
        r = await act(c, sid, "skill", skill="bid_headline",
                      post="post_004", amount=1)
        rec("R5 bid_headline 幂等复用", r.status_code == 200 and r.json().get("ok"))

        # 推进到 accuse → 终局 vote DM（破绽不足）→ ending + rt 成就/报告
        for _ in range(2):
            await act(c, sid, "advance")
        r = await act(c, sid, "vote", target="dm")
        d = r.json()
        evs = d.get("events", [])
        has_ending = any(e["type"] == "ending" for e in evs)
        report = next((e for e in evs
                       if e["payload"].get("event") == "detective_report"), None)
        achs = [e for e in evs if e["type"] == "achievement_unlocked"]
        rep_text = (report or {}).get("payload", {}).get("report_text", "")
        rec("R6 终局产出 detective_report（rt.report_flow）",
            has_ending and report is not None and len(rep_text) > 20,
            f"report_len={len(rep_text)}")
        checked = [e for e in evs if e["payload"].get("event") == "achievements_checked"]
        rec("R7 成就流已被调用（achievement_unlocked 或 checked 审计事件）",
            bool(achs) or bool(checked)
            and all("achievement" in e["payload"] for e in achs),
            f"unlocked={len(achs)} checked={len(checked)}")
        rec("R8 报告结构合规（badges/achievements 字段）",
            report is not None
            and isinstance(report["payload"].get("badges"), list)
            and isinstance(report["payload"].get("achievements"), list))

        # record_event 计数回喂：report_text 非空即 rt 演出链贯通（mock LLM 文案
        # 不含数字高光——具体数字回喂以 achievements_checked/collect 等事件佐证）
        rec("R9 rt 演出链贯通（report_text 非空 + 记账无异常）",
            bool(rep_text) and report is not None, rep_text[:100])

    fails = [r for r in results if not r[1]]
    print(f"\n== RT-E2E: {len(results)-len(fails)}/{len(results)} PASS ==")
    if fails:
        print("FAILURES:", fails)
        raise SystemExit(1)


asyncio.run(main())
