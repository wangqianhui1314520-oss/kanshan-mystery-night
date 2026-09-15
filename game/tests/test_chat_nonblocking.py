"""P0-3 行为级守护：聊天管线的同步 LLM 调用必须 to_thread 化。

背景（2026-09-14 压测取证）：run_action 聊天管线里的 call_gateway/npc_chat
是同步 urllib——直接跑在事件循环上。10 并发聊天时事件循环被冻结 45s，
8/10 个 WS 连接 keepalive ping 超时被踢（1011），服务进程崩溃。

mutation 对照（证明守护有效）：
  把 main.py 中两处 `await asyncio.to_thread(rt.npc_chat, ...)` 还原为
  `rt.npc_chat(...)` 同步调用后，test_ping_survives_slow_llm_chat 必 FAIL
  （B 连接的 pong 会被 A 连接的慢 LLM 冻结 >4s）。

零外部依赖：LLM 上游用本地 stub（sleep 4s 后返回标准 OpenAI 格式），
不烧直答额度、不受网络波动影响。
"""
from __future__ import annotations

import ast
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
import websockets

from tests.conftest import GAME_ROOT

pytestmark = pytest.mark.e2e

PORT = int(os.environ.get("ZHIHU_GAME_E2E_NB_PORT") or 8927)
BASE = f"http://127.0.0.1:{PORT}"
LLM_DELAY = 4.0


def _venv_python() -> str:
    venv = Path(r"C:\Users\Administrator\.workbuddy\binaries\python\envs"
                r"\default\Scripts\python.exe")
    return str(venv) if venv.exists() else sys.executable


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


class _SlowLLM(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        time.sleep(LLM_DELAY)  # 模拟真实 LLM 往返（同步阻塞）
        body = json.dumps({
            "id": "chatcmpl-stub", "object": "chat.completion",
            "model": "stub-model",
            "choices": [{"index": 0,
                         "message": {"role": "user", "content": "stub-回复-行为验证"},
                         "finish_reason": "stop"}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def nb_server():
    """慢速 LLM stub + 游戏服务子进程（凭证清空隔离）。"""
    stub = ThreadingHTTPServer(("127.0.0.1", 0), _SlowLLM)
    lport = stub.server_address[1]
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    if not _port_free(PORT):
        stub.shutdown()
        pytest.skip(f"端口 {PORT} 被占用")
    env = dict(os.environ)
    env["ZHIHU_GAME_USE_MOCK_ENGINE"] = "0"
    for k in ("ZHIHU_APP_KEY", "ZHIHU_ACCESS_SECRET"):
        env[k] = ""                       # 关 zhida 通道（隔离铁律）
    env["LLM_API_KEY"] = "stub-key"       # main 通道 → 本地慢速 stub
    env["LLM_BASE_URL"] = f"http://127.0.0.1:{lport}/v1"
    env["LLM_MODEL"] = "stub-model"
    env["LLM_CACHE"] = ""
    proc = subprocess.Popen(
        [_venv_python(), "-m", "uvicorn", "server.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(GAME_ROOT), env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        deadline, ready = time.time() + 30, False
        while time.time() < deadline:
            try:
                if httpx.get(f"{BASE}/api/health", timeout=2).status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
        if not ready:
            pytest.fail("服务 30s 内未就绪")
        yield BASE
    finally:
        if proc.poll() is None:
            if hasattr(signal, "CTRL_BREAK_EVENT"):
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        stub.shutdown()


def _test_ping_survives_slow_llm_chat(nb_server):
    """A 连接慢 LLM 聊天期间，B 连接的 ping 必须秒回（事件循环不被冻结）。"""
    import asyncio

    async def flow():
        sid = (await _mk_session())["session"]["session_id"]
        urlA = f"ws://127.0.0.1:{PORT}/ws/{sid}?player_id=player:qaA"
        urlB = f"ws://127.0.0.1:{PORT}/ws/{sid}?player_id=player:qaB"
        async with websockets.connect(urlA, max_size=2**23) as wa:
            await wa.recv()  # snapshot
            t_chat = time.monotonic()
            await wa.send(json.dumps({"type": "chat", "actor": "player:qaA",
                                      "payload": {"text": "验证事件循环不被冻结",
                                                  "target": "char_01"}}))
            await asyncio.sleep(1.0)  # 让 A 的 LLM 调用进入同步睡眠窗口
            t0 = time.monotonic()
            async with websockets.connect(urlB, max_size=2**23) as wb:
                await wb.recv()  # snapshot
                await wb.send("ping")
                while True:
                    evt = json.loads(await asyncio.wait_for(wb.recv(), timeout=5))
                    if evt.get("payload", {}).get("event") == "pong":
                        break
            pong_ms = (time.monotonic() - t0) * 1000
            # 等 A 的慢 LLM 回来（4s stub + wave），确认聊天本身仍成功
            reply_ok = False
            while time.monotonic() - t_chat < 15:
                evt = json.loads(await asyncio.wait_for(wa.recv(), timeout=20))
                p = evt.get("payload", {})
                if evt.get("type") == "chat" and p.get("source") == "agent":
                    reply_ok = True
                    break
                if p.get("event") == "ai_reply_failed":
                    break
            return pong_ms, reply_ok

    async def _mk_session():
        async with httpx.AsyncClient(timeout=15, trust_env=False) as c:
            r = await c.post(f"{BASE}/api/session",
                             json={"mode": "main", "player_id": "player:qaA"})
            r.raise_for_status()
            return r.json()

    pong_ms, reply_ok = asyncio.run(flow())
    assert pong_ms < 2500, (
        f"B 连接 pong 耗时 {pong_ms:.0f}ms ≥ 2500ms —— 事件循环被 A 的"
        f"同步 LLM 调用冻结（P0-3 回退），8/10 连接 1011 踢线事故将复现")
    assert reply_ok, "慢速 LLM 场景下聊天未在 15s 内返回 agent 回复"


def test_ping_survives_slow_llm_chat(nb_server):
    _test_ping_survives_slow_llm_chat(nb_server)


def test_ws_next_action_not_blocked_by_slow_chat(nb_server):
    """公开聊天的慢 AI 回复后台化后，下一条 advance 必须立即被引擎裁决。"""
    import asyncio

    async def flow():
        async with httpx.AsyncClient(timeout=15, trust_env=False) as c:
            sid = (await c.post(
                f"{BASE}/api/session",
                json={"mode": "main", "player_id": "player:qa-chat"},
            )).json()["session"]["session_id"]
        url = f"ws://127.0.0.1:{PORT}/ws/{sid}?player_id=player:qa-chat"
        async with websockets.connect(url, max_size=2**23) as ws:
            await ws.recv()  # snapshot
            started = time.monotonic()
            await ws.send(json.dumps({
                "type": "chat", "actor": "player:qa-chat",
                "payload": {"text": "看山，关门", "target": "dm"},
            }))
            await ws.send(json.dumps({
                "type": "advance", "actor": "player:qa-chat", "payload": {},
            }))
            stage = None
            while time.monotonic() - started < 3.0:
                evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                payload = evt.get("payload") or {}
                if payload.get("event") == "stage_changed":
                    stage = payload.get("stage")
                    break
            return stage, time.monotonic() - started

    stage, elapsed = asyncio.run(flow())
    assert stage == "investigate", (
        f"聊天 AI 回复不应阻塞下一条 advance：stage={stage}, elapsed={elapsed:.2f}s")


def test_ast_chat_pipeline_wraps_sync_llm():
    """AST 守护：run_action 聊天管线的 npc_chat/call_gateway 必须经 to_thread；
    管线内不得出现同步 time.sleep。"""
    src = (GAME_ROOT / "server" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 1) run_action 函数体内不得有裸 time.sleep
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) \
                and node.name == "run_action":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    fn = sub.func
                    name = getattr(fn, "attr", "") or getattr(fn, "id", "")
                    assert name != "sleep" or _is_asyncio_sleep(sub), \
                        "run_action 内出现同步 sleep（P0-3 回退）"

    # 2) to_thread 包裹的调用点计数：npc_chat ≥2、call_gateway ≥3
    assert src.count("rt.npc_chat, tgt") >= 2, "npc_chat 调用未全部 to_thread 化"
    assert src.count("call_gateway, llm") >= 3, "call_gateway 调用未全部 to_thread 化"


def _is_asyncio_sleep(call: ast.Call) -> bool:
    fn = call.func
    return isinstance(fn, ast.Attribute) and fn.attr == "sleep" \
        and isinstance(fn.value, ast.Name) and fn.value.id == "asyncio"
