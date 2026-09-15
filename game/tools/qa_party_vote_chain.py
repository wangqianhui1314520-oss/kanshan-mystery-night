"""party 投票链精准验证：每步确认 stage/状态，429 等待重试。只读。"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
import uuid

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

import httpx
import websockets

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8899"
WS = "ws://127.0.0.1:8899"


async def stage(c, sid):
    st = await c.get(f"{BASE}/api/session/{sid}")
    s = st.json().get("session") or {}
    return s.get("stage"), s.get("status"), s.get("events") or []


async def drain(ws, dur=0.8):
    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=dur)
        except (asyncio.TimeoutError, TimeoutError):
            return


async def main():
    pa, pb = f"player:vA{uuid.uuid4().hex[:4]}", f"player:vB{uuid.uuid4().hex[:4]}"
    async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
        r = await c.post(f"{BASE}/api/session",
                         json={"mode": "party", "player_id": pa, "max_players": 4})
        s = (r.json().get("session") or {})
        sid, room = s["session_id"], s["room_code"]
        await c.post(f"{BASE}/api/session/{sid}/join",
                     json={"room_code": room, "player_id": pb, "role": "player"})
        print(f"room={room} sid={sid}")

    async with websockets.connect(f"{WS}/ws/{sid}?player_id={pa}", max_size=2**23) as wa, \
               websockets.connect(f"{WS}/ws/{sid}?player_id={pb}", max_size=2**23) as wb:
        await drain(wa, 1.0)
        await drain(wb, 1.0)
        async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
            # 推进到 investigate
            for i in range(2):
                await wa.send(json.dumps({"type": "advance", "actor": pa, "payload": {}}))
                await drain(wa, 2.0)
                st, status, _ = await stage(c, sid)
                print(f"advance{i+1} -> stage={st} status={status}")
                if status != "playing":
                    break

            # 双人各搜证两次拿卡（429/冷却容忍，仅确认 clue_gained 机制）
            for ws, who in ((wa, pa), (wb, pb)):
                for i in range(2):
                    st, status, _ = await stage(c, sid)
                    if st != "investigate":
                        break
                    await ws.send(json.dumps({"type": "search", "actor": who,
                                              "payload": {"location": "监控室", "keyword": "监控"}}))
                    await drain(ws, 2.0)
                    await asyncio.sleep(0.5)
            st, status, evs = await stage(c, sid)
            clues = [e["payload"].get("clue_id") for e in evs
                     if e.get("type") == "clue_gained"]
            print(f"after search: stage={st} clues={clues[:6]}")

            # 推进到 accuse
            for i in range(4):
                st, status, _ = await stage(c, sid)
                if st == "accuse" or status != "playing":
                    break
                await wa.send(json.dumps({"type": "advance", "actor": pa, "payload": {}}))
                await drain(wa, 2.0)
                await asyncio.sleep(0.3)
            st, status, _ = await stage(c, sid)
            print(f"pre-vote: stage={st} status={status}")
            if st != "accuse" or status != "playing":
                print(f"!! 未能推进到 accuse（stage={st} status={status}），流程止步")
                return

            # 门控验证：无 evidence → vote_rejected
            await wa.send(json.dumps({"type": "vote", "actor": pa,
                                      "payload": {"target": "char_02"}}))
            got_gate = False
            for _ in range(6):
                raw = await asyncio.wait_for(wa.recv(), timeout=8)
                e = json.loads(raw)
                ev_name = e.get("payload", {}).get("event")
                if ev_name == "vote_rejected":
                    got_gate = True
                    print("gate: vote_rejected ✓ ->",
                          str(e["payload"].get("notice", ""))[:80])
                    break
            print("gate check:", "PASS" if got_gate else "FAIL")

            # 双人带 evidence 投票
            for ws, who in ((wa, pa), (wb, pb)):
                await ws.send(json.dumps({"type": "vote", "actor": who,
                                          "payload": {"target": "char_02",
                                                      "evidence": ["c1", "c2"]}}))
                await drain(ws, 1.5)

            # 轮询终局（party G11：AI 空席跟真人多数票，同步引擎结算）
            t0 = time.monotonic()
            ending = None
            while time.monotonic() - t0 < 45:
                st, status, evs = await stage(c, sid)
                ending = next((e for e in reversed(evs) if e.get("type") == "ending"), None)
                if ending or status == "ended":
                    break
                try:
                    raw = await asyncio.wait_for(wa.recv(), timeout=0.4)
                    e = json.loads(raw)
                    if e.get("type") == "ending":
                        ending = e
                        break
                except (asyncio.TimeoutError, TimeoutError):
                    pass
                await asyncio.sleep(0.4)
            p = (ending or {}).get("payload") or {}
            print(f"ending: {'YES' if ending else 'NO(45s)'} accused={p.get('accused')} "
                  f"outcome={p.get('outcome')} final_status={status} took={time.monotonic()-t0:.1f}s")


asyncio.run(main())
