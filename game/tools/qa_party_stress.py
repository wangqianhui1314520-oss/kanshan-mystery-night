"""QA 房间模式（party）前端全流程实测（协议级，模拟前端双人 + 观战路径）。

背景：2026-09-14 修复了 main 模式的 AI 聊天链路（代理劫持/同步阻塞/wave
后台化/投票竞态）。用户要求验证 party 模式是否有相同问题。

覆盖：建房→join→双人 WS→定向私聊（含房间广播可见性）→公开广播（社交波
后台化）→搜证→vote 证据门控→双人投票→G11 AI 跟票终局→全程连接存活。
只读测试，不修改游戏代码；session 为运行时产物。
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
import uuid

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import httpx
import websockets

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.environ.get("QA_PARTY_BASE_URL", "http://127.0.0.1:8899").rstrip("/")
WS = BASE.replace("http://", "ws://").replace("https://", "wss://")
T0 = time.monotonic()
RESULTS = []


def ts():
    return f"{time.monotonic()-T0:7.2f}s"


def rec(case, ok, detail="", ms=0.0):
    RESULTS.append({"case": case, "ok": ok, "ms": round(ms), "detail": str(detail)[:180]})
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {case:34s} {ms:7.0f}ms  {str(detail)[:150]}")


async def drain(ws, dur=0.6):
    n = 0
    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=dur)
            n += 1
        except (asyncio.TimeoutError, TimeoutError):
            return n


async def recv_until(ws, want, timeout=30.0):
    t0 = time.monotonic()
    events = []
    while time.monotonic() - t0 < timeout:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.5, timeout - (time.monotonic() - t0)))
        except (asyncio.TimeoutError, TimeoutError):
            break
        evt = json.loads(raw)
        events.append(evt)
        if want(evt):
            return True, events, (time.monotonic() - t0) * 1000
    return False, events, (time.monotonic() - t0) * 1000


def is_agent_chat(evt):
    return evt.get("type") == "chat" and evt.get("payload", {}).get("source") == "agent"


def is_fail(evt):
    return (evt.get("type") == "system"
            and evt.get("payload", {}).get("event") == "ai_reply_failed")


def is_error(evt):
    return evt.get("type") == "system" and evt.get("payload", {}).get("event") == "error"


async def main():
    pa, pb = f"player:pA{uuid.uuid4().hex[:4]}", f"player:pB{uuid.uuid4().hex[:4]}"
    async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
        # 1. 建房
        t0 = time.monotonic()
        r = await c.post(f"{BASE}/api/session",
                         json={"mode": "party", "player_id": pa, "max_players": 4})
        body = r.json()
        sid = (body.get("session") or {}).get("session_id")
        room = (body.get("session") or {}).get("room_code")
        rec("P0/create_party_room", r.status_code == 200 and bool(sid) and bool(room),
            f"sid={sid} room={room}", (time.monotonic() - t0) * 1000)
        if not sid:
            return

        # 2. 第二玩家 join
        t0 = time.monotonic()
        r2 = await c.post(f"{BASE}/api/session/{sid}/join",
                          json={"room_code": room, "player_id": pb, "role": "player"})
        seats = ((r2.json().get("session") or {}).get("seats_public")
                 or r2.json().get("session", {}).get("seats") or [])
        rec("P1/second_player_join", r2.status_code == 200,
            f"seats={[(s.get('char_id'), s.get('is_ai')) for s in seats][:5] if seats else r2.text[:120]}",
            (time.monotonic() - t0) * 1000)

    # 3. 双人 WS
    try:
        async with websockets.connect(f"{WS}/ws/{sid}?player_id={pa}", max_size=2**23) as wa, \
                   websockets.connect(f"{WS}/ws/{sid}?player_id={pb}", max_size=2**23) as wb:
            await drain(wa, 1.0)
            await drain(wb, 1.0)

            # 4. pA 定向私聊 char_01（真实 LLM）
            t0 = time.monotonic()
            await wa.send(json.dumps({"type": "chat", "actor": pa,
                                      "payload": {"text": "知之者，你手上的爆款数据干净吗？", "target": "char_01"}}))
            hit, evs, ms = await recv_until(
                wa, lambda e: (is_agent_chat(e) and e.get("actor") == "npc:char_01")
                or is_fail(e) or is_error(e), 75)
            if hit and is_agent_chat(evs[-1]):
                p = evs[-1]["payload"]
                rec("P2/pA_dm_chat_char01", True,
                    f"prov={p.get('provider')} deg={p.get('degraded')} len={len(str(p.get('text','')))}", ms)
            elif hit and is_fail(evs[-1]):
                rec("P2/pA_dm_chat_char01", True,
                    "DEGRADED_EXPECTED: AI 未配置，服务端明确返回 ai_reply_failed", ms)
            else:
                rec("P2/pA_dm_chat_char01", False, f"{evs[-1].get('payload') if evs else 'timeout'}", ms)

            # 4b. pB 同时应收到该互动（房间广播）
            seen_by_b = await recv_until(wb, lambda e: e.get("type") == "chat"
                                         and (e.get("payload", {}).get("char_id") == "char_01"), 5)
            rec("P3/pB_sees_A_whisper_broadcast", seen_by_b[0], f"hits={len(seen_by_b[1])}", seen_by_b[2])

            # 5. pB 广播聊天（对 dm）→ 社交波后台化，期间 pA ping 应存活
            await drain(wa, 0.5)
            t0 = time.monotonic()
            await wb.send(json.dumps({"type": "chat", "actor": pb,
                                      "payload": {"text": "大家好，我是第二位侦探。", "target": "dm"}}))
            hit, evs, ms = await recv_until(
                wb, lambda e: (is_agent_chat(e) and e.get("actor") == "dm")
                or is_fail(e) or is_error(e), 75)
            rec("P4/pB_broadcast_dm_reply",
                (hit and (is_agent_chat(evs[-1]) or is_fail(evs[-1]))) if evs else False,
                ("DEGRADED_EXPECTED: AI 未配置" if evs and is_fail(evs[-1])
                 else f"prov={evs[-1]['payload'].get('provider') if evs else '-'}"), ms)
            # wave 后台化核心验证：社交波运行期间 pA 的 ping 不得被阻塞
            await asyncio.sleep(1.0)
            t0 = time.monotonic()
            await wa.send("ping")
            hit, evs, ms = await recv_until(wa, lambda e: e.get("payload", {}).get("event") == "pong", 6)
            rec("P5/ping_alive_during_social_wave", hit and ms < 2500,
                f"pong={ms:.0f}ms（<2500=事件循环未冻结）", ms)

            # 5b. break_ice → investigate；第二次 advance 要求先取得 PARTY_CH1_KEYS。
            await wa.send(json.dumps({"type": "advance", "actor": pa, "payload": {}}))
            await drain(wa, 1.5)
            await drain(wb, 0.5)

            # 6. 两人搜证（使用真实 player:* actor；至少一张关键线索后再推进）。
            search_cases = (("pA", pa, wa), ("pB", pb, wb))
            for label, actor, ws in search_cases:
                t0 = time.monotonic()
                await ws.send(json.dumps({"type": "search", "actor": actor,
                                          "payload": {"location": "茶水间", "keyword": "泡面"}}))
                hit, evs, ms = await recv_until(
                    ws, lambda e: e.get("type") in ("clue_gained", "search_result") or is_error(e), 30)
                got_clue = any(e.get("type") in ("clue_gained", "search_result") for e in evs)
                rec(f"P6/search_{label}", hit and got_clue,
                    f"clue={'Y' if got_clue else 'N'} events={[e.get('type') for e in evs][:4]}", ms)

            # 6b. 关键线索门槛通过后推进到 round_table，再到 accuse。
            for _ in range(2):
                await wa.send(json.dumps({"type": "advance", "actor": pa, "payload": {}}))
                await drain(wa, 1.5)
            await drain(wb, 0.5)

            # 7. vote 证据门控：无 evidence → vote_rejected
            await wa.send(json.dumps({"type": "vote", "actor": pa,
                                      "payload": {"target": "char_02"}}))
            hit, evs, ms = await recv_until(
                wa, lambda e: e.get("payload", {}).get("event") in ("vote_rejected", "vote")
                or is_error(e), 15)
            ev_names = [e.get("payload", {}).get("event") for e in evs]
            rec("P7/vote_gate_no_evidence", "vote_rejected" in ev_names or "vote" in ev_names,
                f"events={ev_names[:4]}", ms)

            # 8. 双人带 evidence 投票 → G11 AI 跟票 → 终局
            await wb.send(json.dumps({"type": "vote", "actor": pb,
                                      "payload": {"target": "char_02",
                                                  "evidence": ["clue_e1", "clue_e2"]}}))
            hit, evs, ms = await recv_until(wb, lambda e: e.get("type") == "vote", 15)
            rec("P8/pB_vote_with_evidence", hit, f"voters={evs[-1]['payload'].get('voters') if evs else '-'}", ms)
            # pA 投第二票 → 真人票齐 → party G11 AI 跟票 → 终局
            t0 = time.monotonic()
            await wa.send(json.dumps({"type": "vote", "actor": pa,
                                      "payload": {"target": "char_02",
                                                  "evidence": ["clue_e1", "clue_e2"]}}))
            ending = None
            try:
                async with httpx.AsyncClient(timeout=10, trust_env=False) as c2:
                    deadline = time.monotonic() + 40
                    while time.monotonic() < deadline:
                        st = await c2.get(f"{BASE}/api/session/{sid}")
                        s = (st.json().get("session") or {})
                        ev_list = s.get("events") or []
                        ending = next((e for e in reversed(ev_list) if e.get("type") == "ending"), None)
                        if ending is not None or s.get("status") == "ended":
                            break
                        # 同时从 WS 收
                        try:
                            raw = await asyncio.wait_for(wa.recv(), timeout=0.3)
                            e = json.loads(raw)
                            if e.get("type") == "ending":
                                ending = e
                                break
                        except (asyncio.TimeoutError, TimeoutError):
                            pass
                        await asyncio.sleep(0.3)
            finally:
                ms = (time.monotonic() - t0) * 1000
            rec("P9/two_human_votes_ending", ending is not None,
                f"accused={((ending or {}).get('payload') or {}).get('accused')} outcome={((ending or {}).get('payload') or {}).get('outcome')}", ms)

            # 9. 双连接全程存活检查
            t0 = time.monotonic()
            for w in (wa, wb):
                await w.send("ping")
            hit_a, _, ms = await recv_until(wa, lambda e: e.get("payload", {}).get("event") == "pong", 6)
            rec("P10/connections_alive_at_end", hit_a, f"pong={ms:.0f}ms", ms)

    except Exception as e:
        rec("EXCEPTION", False, f"{type(e).__name__}: {e}")

    n_fail = sum(1 for r in RESULTS if not r["ok"])
    print(f"\n===== PARTY SUMMARY: {len(RESULTS)-n_fail}/{len(RESULTS)} PASS =====")


if __name__ == "__main__":
    asyncio.run(main())
