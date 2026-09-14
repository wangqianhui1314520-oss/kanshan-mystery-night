"""只读审计：验证 server/main.py run_ai_act 的 PlayerAgent.decide 是否阻塞事件循环。

背景（2026-09-14 P1 修复）：decide 内部为同步 LLM 调用（LLM_TIMEOUT=30s + 429
退避最多 ~24s），修复前直接在事件循环线程执行会冻结全服务心跳；修复后应与
npc_social 一致走 asyncio.to_thread（线程池）。

取证方式（真实代码路径，零 mock 引擎、零业务写盘，会话落 tmp 临时目录）：
  A. 修复后语义（当前源码，to_thread）：慢网关 chat 阻塞 3s，同一事件循环并发
     50ms 心跳协程；decide 期间心跳 tick 应持续（>=40）。
  B. mutation（伪同步 to_thread 替换，等价修复前代码语义，不改源文件）：
     decide 期间心跳应冻结（<=5）。
  C. 决策一致性：A/B 的 decision dict（剥离 latency_ms）必须完全相等——
     证明修复只是执行位置变化，决策逻辑零变化。

用法（game/ 目录）：
    python tools/audit_decide_blocking.py
    零网络：LLM_*/ZHIHU_* 凭证全程 delenv，ZHIHU_AI_DEFAULT=0。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME_ROOT))

# 测试隔离铁律：清空真实凭证，禁知乎默认通道（game/.env 真凭证不得进入本审计）。
for _k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
           "ZHIHU_APP_KEY", "ZHIHU_ACCESS_SECRET", "ZHIHU_ZHIDA_URL"):
    os.environ.pop(_k, None)
os.environ["ZHIHU_AI_DEFAULT"] = "0"

from server.main import GameServer                      # noqa: E402
from server.store.session_store import SessionStore     # noqa: E402
from server.engine_driver import EngineDriver           # noqa: E402

SCENARIO_DIR = GAME_ROOT / "content" / "scenarios" / "kanshan"
SLOW_SECONDS = 3.0
TICK_INTERVAL = 0.05


class SlowGateway:
    """模拟慢/限流 LLM：chat 在调用线程阻塞 3s（等价 429 退避+超时最坏路径）。
    返回合法决策 JSON，让 PlayerAgent._llm_decide 走真实解析/校验路径。"""

    last_provider = "slow_audit"
    last_error = ""

    @staticmethod
    def available() -> bool:
        return True

    def chat(self, system: str, user: str, temperature: float = 0.8,
             provider: str = "main") -> str:
        time.sleep(SLOW_SECONDS)
        return json.dumps({
            "type": "chat",
            "payload": {"text": "（审计慢网关台词）我先说两句。",
                        "target": "char_01", "char_id": "char_01"},
            "reason": "audit",
        }, ensure_ascii=False)


class Heartbeat:
    """同事件循环心跳计数器：事件循环被阻塞时 tick 停止增长。"""

    def __init__(self):
        self.ticks = 0
        self._stop = asyncio.Event()

    async def run(self):
        while not self._stop.is_set():
            self.ticks += 1
            await asyncio.sleep(TICK_INTERVAL)

    def stop(self):
        self._stop.set()


async def _run_once(server: GameServer, sid: str, role: str) -> tuple[dict, int]:
    """跑一次 run_ai_act(dry_run)，返回 (body, decide 期间心跳 tick 差)。"""
    hb = Heartbeat()
    task = asyncio.create_task(hb.run())
    await asyncio.sleep(TICK_INTERVAL * 2)   # 让心跳先起跳
    before = hb.ticks
    t0 = time.perf_counter()
    body, err = await server.run_ai_act(sid, role, dry_run=True)
    elapsed = time.perf_counter() - t0
    after = hb.ticks
    hb.stop()
    await asyncio.sleep(0)
    task.cancel()
    if err is not None:
        raise RuntimeError(f"run_ai_act 失败: {err}")
    assert (body.get("decision") or {}).get("source") == "llm", \
        "decide 未走 LLM 路径（source!=llm），慢网关未命中，审计无效"
    body["decision"]["meta"]["_elapsed_s"] = round(elapsed, 2)
    return body, after - before


async def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kanshan_audit_decide_") as tmp:
        server = GameServer(SCENARIO_DIR)
        server.store = SessionStore(Path(tmp))
        eng = EngineDriver(SCENARIO_DIR)
        session = eng.create_session("main", "player:1")
        sid = "audit_decide"
        session["session_id"] = sid
        server.store.save_session(sid, session)
        # 注入慢网关：只影响本次 run_ai_act 的 decide 路径
        server._llm_for_session = lambda _sid: SlowGateway()  # type: ignore[method-assign]

        print("=" * 64)
        print("Run A 修复后语义（当前源码：asyncio.to_thread）")
        body_a, ticks_a = await _run_once(server, sid, "char_03")
        print(f"  decide 耗时 = {body_a['decision']['meta']['_elapsed_s']}s，"
              f"期间心跳 tick = {ticks_a}（阈值 >=40 为不阻塞）")

        print("Run B mutation（伪同步 to_thread = 修复前代码语义，不改源文件）")
        real_to_thread = asyncio.to_thread

        async def fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)      # 在事件循环线程内同步执行 = 修复前

        try:
            asyncio.to_thread = fake_to_thread  # type: ignore[assignment]
            body_b, ticks_b = await _run_once(server, sid, "char_03")
        finally:
            asyncio.to_thread = real_to_thread  # type: ignore[assignment]
        print(f"  decide 耗时 = {body_b['decision']['meta']['_elapsed_s']}s，"
              f"期间心跳 tick = {ticks_b}（预期 <=5：事件循环冻结复现）")

        # C 决策一致性（剥离审计注入的 _elapsed_s 与天然随环境波动的 latency_ms）
        def _core(dec: dict) -> str:
            meta = {k: v for k, v in (dec.get("meta") or {}).items()
                    if k not in ("latency_ms", "_elapsed_s")}
            return json.dumps({**dec, "meta": meta}, sort_keys=True,
                              ensure_ascii=False)

        same = _core(body_a["decision"]) == _core(body_b["decision"])
        print(f"Run C 决策一致性（A vs B，剥离 latency_ms 后）：{'一致' if same else '不一致'}")

        print("=" * 64)
        ok = ticks_a >= 40 and ticks_b <= 5 and same
        verdict = "PASS" if ok else "FAIL"
        print(f"审计结论：{verdict}")
        print(f"  A 不阻塞（tick={ticks_a}>=40）：{'PASS' if ticks_a >= 40 else 'FAIL'}")
        print(f"  B 冻结复现（tick={ticks_b}<=5）：{'PASS' if ticks_b <= 5 else 'FAIL'}")
        print(f"  C 决策逻辑零变化：{'PASS' if same else 'FAIL'}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
