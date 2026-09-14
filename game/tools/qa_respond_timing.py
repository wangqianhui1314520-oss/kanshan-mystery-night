"""QA 探针 3：本地直调 npc.respond 全链路计时（与服务器同款代码路径）。只读。"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

# 与服务器一致：加载 .env（load_dotenv 语义）
for line in (GAME_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        import os
        os.environ.setdefault(k, v)

from agents.llm_client import LLMClient, call_gateway  # noqa: E402

llm = LLMClient()
ch = json.loads((GAME_ROOT / "content" / "scenarios" / "kanshan" / "characters"
                 / "char_01.json").read_text(encoding="utf-8"))

from agents.npc_agent import NPCAgent  # noqa: E402

from engine.timeline import Timeline  # noqa: E402
timeline = Timeline(GAME_ROOT / "content" / "scenarios" / "kanshan")
npc = NPCAgent(llm, ch, timeline)

for q in ["知之者，你带我做的第一篇爆款，数据是刷的吗？",
          "那晚 21:30 你在哪个房间？"]:
    t0 = time.monotonic()
    try:
        reply = npc.respond(q)
        dt = (time.monotonic() - t0) * 1000
        print(f"[{dt:8.0f}ms] prov={llm.last_provider} err={llm.last_error[:60]!r}")
        print("   reply:", reply[:80].replace("\n", " "))
    except Exception as e:
        print("EXC:", type(e).__name__, str(e)[:150])
print("degrade_log:", llm.degrade_log[-5:])
