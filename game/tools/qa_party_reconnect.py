"""真实 party 双 WS 回归：掉线 AI 接管 -> 同 player_id /join 恢复真人席位。

只读 QA，使用指定服务 BASE_URL；默认端口 8899，可用 QA_PARTY_BASE_URL 覆盖。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import httpx
import websockets

BASE = os.environ.get("QA_PARTY_BASE_URL", "http://127.0.0.1:8899").rstrip("/")
WS_BASE = BASE.replace("http://", "ws://").replace("https://", "wss://")


async def main() -> int:
    host = f"player:reconnectA{uuid.uuid4().hex[:5]}"
    guest = f"player:reconnectB{uuid.uuid4().hex[:5]}"
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        created = await client.post(f"{BASE}/api/session", json={
            "mode": "party", "player_id": host, "max_players": 2})
        created.raise_for_status()
        session = created.json()["session"]
        sid, room = session["session_id"], session["room_code"]
        joined = await client.post(f"{BASE}/api/session/{sid}/join", json={
            "room_code": room, "player_id": guest, "role": "player"})
        joined.raise_for_status()
        print(f"CREATE room={room} sid={sid}")

        async with websockets.connect(f"{WS_BASE}/ws/{sid}?player_id={host}") as host_ws, \
                websockets.connect(f"{WS_BASE}/ws/{sid}?player_id={guest}") as guest_ws:
            host_snapshot = json.loads(await host_ws.recv())
            guest_snapshot = json.loads(await guest_ws.recv())
            assert host_snapshot["payload"].get("seats"), "host snapshot missing seats"
            assert guest_snapshot["payload"].get("seats"), "guest snapshot missing seats"
            # 接收 join 广播，避免把关闭前的 peer_joined 留在 guest 流里。
            for _ in range(2):
                try:
                    await asyncio.wait_for(guest_ws.recv(), timeout=0.4)
                except asyncio.TimeoutError:
                    break
            await host_ws.close()
            takeover = None
            while takeover is None:
                raw = await asyncio.wait_for(guest_ws.recv(), timeout=8)
                evt = json.loads(raw)
                if (evt.get("payload") or {}).get("event") == "ai_takeover":
                    takeover = evt
            print("TAKEOVER", takeover["payload"].get("player_id"), takeover["payload"].get("char_id"))

        dropped = (await client.get(f"{BASE}/api/session/{sid}")).json()["session"]
        dropped_seat = next(s for s in dropped["seats"] if s.get("player_id") == host)
        assert dropped_seat["connected"] is False and dropped_seat["is_ai"] is True
        print("DROPPED", dropped_seat["char_id"], "connected=false is_ai=true")

        restored = await client.post(f"{BASE}/api/session/{sid}/join", json={
            "room_code": room, "player_id": host, "role": "player"})
        restored.raise_for_status()
        restored_seat = next(s for s in restored.json()["seats"] if s.get("player_id") == host)
        assert restored_seat["connected"] is True and restored_seat["is_ai"] is False
        print("RESTORED", restored_seat["char_id"], "connected=true is_ai=false")
        print("PASS: party reconnect recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
