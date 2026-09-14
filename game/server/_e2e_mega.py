"""MEGA_MODE 接线 E2E（party/OAuth/assets；用后即删，证据落 STATUS.md）。"""
import asyncio
import json

import httpx
import websockets

BASE = "http://127.0.0.1:8899"
results = []


def rec(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))


async def act(c, sid, typ, actor="player:1", **payload):
    return await c.post(f"{BASE}/api/session/{sid}/action",
                        json={"type": typ, "actor": actor, "payload": payload})


async def main():
    async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
        # ---------- assets 静态路由 ----------
        r = await c.get(f"{BASE}/assets/")
        rec("M1 /assets/ 可列目录或 200/404 结构响应", r.status_code in (200, 404),
            f"status={r.status_code}")
        # 找一个真实资产验证
        import pathlib
        real = sorted(pathlib.Path("content/assets").rglob("*.png"))[:1]
        if real:
            rel = real[0].relative_to("content/assets").as_posix()
            r2 = await c.get(f"{BASE}/assets/{rel}")
            rec("M2 /assets/<真实png> 200+image", r2.status_code == 200
                and r2.headers.get("content-type", "").startswith("image/"),
                f"{rel} ct={r2.headers.get('content-type', '')[:24]}")
        else:
            rec("M2 /assets/<真实png>", False, "content/assets 无 png")

        # ---------- party 多人态 ----------
        s = (await c.post(f"{BASE}/api/session",
                          json={"mode": "party", "player_id": "player:1",
                                "max_players": 3})).json()
        sid = s["session"]["session_id"]
        code = s["session"].get("room_code", "")
        rec("M3 party 建局带房间码", bool(code) and s["session"]["max_players"] == 3,
            f"room_code={code}")

        r = await c.post(f"{BASE}/api/session/{sid}/join",
                         json={"room_code": "wrong", "player_id": "2"})
        rec("M4 错误房间码→403", r.status_code == 403)

        r = await c.post(f"{BASE}/api/session/{sid}/join",
                         json={"room_code": code, "player_id": "2"})
        rec("M5 join 玩家2", r.status_code == 200 and "player:2" in r.json()["players"])

        r = await c.post(f"{BASE}/api/session/{sid}/join",
                         json={"room_code": code, "player_id": "sp1",
                               "role": "spectator"})
        rec("M6 join 观战", r.status_code == 200 and r.json()["role"] == "spectator")

        # 上限 3：再加 2 个玩家，第 4 个→409
        await c.post(f"{BASE}/api/session/{sid}/join",
                     json={"room_code": code, "player_id": "3"})
        r = await c.post(f"{BASE}/api/session/{sid}/join",
                         json={"room_code": code, "player_id": "4"})
        rec("M7 房间满→409+观战指引", r.status_code == 409 and "观战" in r.json()["detail"])

        # ---------- 真人私聊路由 ----------
        ws_p2 = await websockets.connect(
            f"ws://127.0.0.1:8899/ws/{sid}?player_id=player:2")
        await ws_p2.recv()  # snapshot
        r = await c.post(f"{BASE}/api/session/{sid}/whisper",
                         json={"from": "player:1", "to": "player:2",
                               "text": "我觉得 3 号有问题，别声张"})
        d = r.json()
        whisper_evt = None
        try:
            while True:
                whisper_evt = json.loads(await asyncio.wait_for(ws_p2.recv(), 5))
                if whisper_evt.get("type") == "chat" and \
                        whisper_evt["payload"].get("whisper"):
                    break
        except asyncio.TimeoutError:
            pass
        rec("M8 whisper 定向投递到目标 WS", r.status_code == 200 and d["ok"]
            and d["delivered"] is True and whisper_evt is not None
            and whisper_evt["payload"]["to"] == "player:2",
            f"delivered={d.get('delivered')} evt={bool(whisper_evt)}")
        r = await c.post(f"{BASE}/api/session/{sid}/whisper",
                         json={"from": "player:1", "to": "npc:char_01", "text": "hi"})
        rec("M9 whisper 目标须为真人→400", r.status_code == 400)
        r = await c.post(f"{BASE}/api/session/{sid}/whisper",
                         json={"from": "player:1", "to": "player:2",
                               "text": "我的手机号 13812345678"})
        rec("M10 whisper 内容安全→422", r.status_code == 422)

        # ---------- OAuth（无凭证真实降级 + 有 mock token 的 /me 行为） ----------
        h = (await c.get(f"{BASE}/api/health")).json()
        rec("M11 health 含 oauth 状态", "oauth" in h and "configured" in h["oauth"],
            json.dumps(h["oauth"], ensure_ascii=False)[:100])
        r = await c.post(f"{BASE}/api/session/{sid}/login",
                         json={"player_id": "player:1", "code": "fake_code_123"})
        detail = r.json().get("detail", "")
        degraded = (r.status_code == 502
                    and ("OAuth" in detail or "凭证" in detail or "交换" in detail))
        rec("M12 login 无凭证/假码→真实降级不伪造", degraded, detail[:90])
        r = await c.get(f"{BASE}/api/profile/me",
                        params={"session_id": sid, "player_id": "player:1"})
        d = r.json()
        rec("M13 /profile/me 未登录→指引+authorize_url", r.status_code == 200
            and d["ok"] is False and ("authorize_url" in d or "未" in d["notice"]),
            d.get("notice", "")[:80])

        # ---------- 掉线 AI 接管广播（WS 验证） ----------
        ws2 = await websockets.connect(f"ws://127.0.0.1:8899/ws/{sid}?spectator=1")
        snap2 = json.loads(await ws2.recv())
        rec("M14 观战快照标记", snap2["payload"]["spectator"] is True
            and "spectators" in snap2["payload"])
        # 观战发动作 → 只读拒绝（漏斗过滤自身 join 广播）
        async def ws_recv_until(pred, t=5):
            while True:
                e = json.loads(await asyncio.wait_for(ws2.recv(), t))
                if pred(e):
                    return e
        await ws2.send(json.dumps({"type": "chat", "actor": "player:1",
                                   "payload": {"text": "x"}}))
        err = await ws_recv_until(
            lambda e: e["type"] == "system"
            and e["payload"].get("event") == "error")
        rec("M15 观战只读拦截", "只读" in err["payload"]["notice"])
        # player:2 掉线 → ai_takeover 广播（ws_p2 关闭即掉线）
        await ws_p2.close()
        got = None
        try:
            got = await ws_recv_until(
                lambda e: e.get("payload", {}).get("event") == "ai_takeover", 6)
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            pass
        rec("M16 掉线 AI 接管广播", got is not None
            and got["payload"].get("event") == "ai_takeover"
            and got["payload"]["player_id"] == "player:2",
            (got or {}).get("payload", {}).get("notice", "")[:60])
        sess = (await c.get(f"{BASE}/api/session/{sid}")).json()["session"]
        rec("M17 ai_takeover 落 session", sess.get("ai_takeover", {}).get("player:2") is True)
        try:
            await ws2.close()
        except Exception:
            pass

    fails = [r for r in results if not r[1]]
    print(f"\n== MEGA-E2E: {len(results)-len(fails)}/{len(results)} PASS ==")
    if fails:
        print("FAILURES:", fails)
        raise SystemExit(1)


asyncio.run(main())
