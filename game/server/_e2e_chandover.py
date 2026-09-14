"""C 组交代对接 E2E（暗拍 2AP 上层扣减 / 拼图篡改点 flow 内校验；用后即删）。"""
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
        s = (await c.post(f"{BASE}/api/session",
                          json={"mode": "main", "player_id": "player:1"})).json()
        sid = s["session"]["session_id"]
        await act(c, sid, "advance")  # → investigate (AP 12)

        # ---------- 暗拍：2AP 上层扣减/校验 ----------
        r = await act(c, sid, "skill", skill="stealth_photo",
                      location="desk_kanshan", keyword="鱼干")
        d = r.json()
        ev = next((e for e in d.get("events", [])
                   if e["payload"].get("event") == "stealth_photo_result"), None)
        sess = (await c.get(f"{BASE}/api/session/{sid}")).json()["session"]
        rec("C1 暗拍 2AP 上层扣减（12→10）",
            d.get("ok") and ev is not None and ev["payload"]["ok"] is True
            and sess["actions_left"] == 10,
            f"ap={sess['actions_left']} ok={ev['payload']['ok'] if ev else None}")
        photo = ev["payload"].get("photo") if ev else None
        rec("C2 照片持有（photo 结构）", bool(photo and photo.get("photo_id")),
            f"photo_id={photo.get('photo_id') if photo else None}")

        # ---------- 拼图：篡改点 flow 内校验 ----------
        r = await act(c, sid, "skill", skill="puzzle",
                      target="char_02", proposal=["blk_x", "blk_y"])
        d = r.json()
        ev = next((e for e in d.get("events", [])
                   if e["payload"].get("event") == "puzzle_rejected"), None)
        rec("C3 篡改点不足→puzzle_rejected 诚实返回（无需预扣）",
            d.get("ok") and ev is not None and "篡改点" in ev["payload"]["notice"],
            ev["payload"]["notice"][:50] if ev else "no-event")

        # 记忆修复（driver 裁决解锁）→ 事件回喂 rt.unlock_memory → 篡改点就位
        r = await act(c, sid, "skill", skill="memory_fix", target="char_02")
        d = r.json()
        unlocked = any(e["type"] == "memory_unlock" for e in d.get("events", []))
        rec("C4 memory_fix→memory_unlock（回喂 rt 同步链）",
            d.get("ok") and unlocked)
        r = await act(c, sid, "skill", skill="memory_fix", target="char_02")
        r = await act(c, sid, "skill", skill="memory_fix", target="char_02")

        # 再次拼图：篡改点已就位 → flow 内扣 2 → 判定（proposal 乱序→排错锐评）
        r = await act(c, sid, "skill", skill="puzzle",
                      target="char_02", proposal=["blk_x", "blk_y"])
        d = r.json()
        ev = next((e for e in d.get("events", [])
                   if e["payload"].get("event") == "puzzle_result"), None)
        rec("C5 篡改点就位→puzzle_flow 判定（排错锐评）",
            d.get("ok") and ev is not None and ev["payload"]["ok"] is True
            and ev["payload"]["correct"] is False,
            f"correct={ev['payload']['correct'] if ev else None}")

        # ---------- faction 零透出复核（headline） ----------
        r = await act(c, sid, "skill", skill="bid_headline",
                      post="post_004", amount=1)
        blob = json.dumps(r.json().get("events", []), ensure_ascii=False)
        rec("C6 headline 事件 faction 零透出",
            r.status_code == 200 and '"faction"' not in blob,
            "no-faction-key" if '"faction"' not in blob else "LEAK")

        # ---------- 回归快照 ----------
        rec("C7 对局仍可继续（无副作用）",
            (await act(c, sid, "chat", target="npc:char_02",
                       text="继续")).status_code == 200)

    fails = [r for r in results if not r[1]]
    print(f"\n== C-HANDOVER-E2E: {len(results)-len(fails)}/{len(results)} PASS ==")
    if fails:
        print("FAILURES:", fails)
        raise SystemExit(1)


asyncio.run(main())
