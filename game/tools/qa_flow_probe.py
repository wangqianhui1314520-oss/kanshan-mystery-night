"""QA 探针 2：完整事件流录屏（60s），一锤定音 AI 回复链路时序。只读。"""
from __future__ import annotations
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import websockets

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8899"
T0 = time.monotonic()


def ts() -> str:
    return f"{time.monotonic()-T0:7.2f}s"


async def main():
    pid = f"player:qa_flow{uuid.uuid4().hex[:4]}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/api/session", json={"mode": "main", "player_id": pid})
        sid = (r.json().get("session") or {})["session_id"]
    print(f"[{ts()}] session={sid}")
    async with websockets.connect(f"ws://127.0.0.1:8899/ws/{sid}?player_id={pid}",
                                  max_size=2**23, ping_interval=5, ping_timeout=30) as ws:
        # 后台收流 60s，全部落盘
        got: list = []

        async def reader():
            while True:
                raw = await ws.recv()
                e = json.loads(raw)
                got.append((time.monotonic() - T0, e))

        task = asyncio.create_task(reader())
        await asyncio.sleep(1.0)
        for label, text, tgt in [
            ("Q1", "知之者，你带我做的第一篇爆款，数据是刷的吗？", "char_01"),
            ("Q2", "流量酱，那晚 21:30 你在哪个房间？谁指使你删记录的？", "char_03"),
            ("Q3", "V587，你昨晚几点到的档案局？看见谁进过档案室？", "char_08"),
        ]:
            print(f"[{ts()}] >>> {label} -> {tgt}: {text}")
            await ws.send(json.dumps({"type": "chat", "actor": pid,
                                      "payload": {"text": text, "target": tgt}}))
            await asyncio.sleep(12)
        await asyncio.sleep(8)
        task.cancel()
        print(f"\n===== 事件流（共 {len(got)} 条） =====")
        for t, e in got:
            p = e.get("payload", {})
            et = e.get("type")
            actor = e.get("actor", "")
            if et == "chat":
                src = p.get("source", "player")
                mark = "AI" if src == "agent" else ("ME" if actor == pid else "??")
                txt = str(p.get("text", "")).replace("\n", " ")[:90]
                print(f"[{t:7.2f}s] {mark:2s} {actor[:22]:<24} prov={p.get('provider','')} "
                      f"guard={p.get('identity_guarded')} | {txt}")
            elif et == "system":
                ev = p.get("event", "")
                if ev not in ("pong",):
                    notice = str(p.get("notice", ""))[:60]
                    print(f"[{t:7.2f}s] SYS {ev:<18} {notice}")


asyncio.run(main())
