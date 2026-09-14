"""P1-1/P1-2 守护：替换句扩池轮换 + reply_kind 诚实化标签。

背景（2026-09-14 压测取证）：身份替换句与守卫违规替换句各只有一句，
今日 40+ 个 session 存档反复复读同句；且降级回复仍标 provider=zhida，
前端与 /api/health 无法识别真实降级。
mutation 对照：把 _IDENTITY_SAFE_LINES/_VIOLATION_SAFE_LINES 还原为单句、
或删除 reply_kind 透传后，本文件用例必须 FAIL。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

GAME_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME_ROOT))

from agents.npc_agent import NPCAgent, _IDENTITY_SAFE_LINES  # noqa: E402
from agents.llm_client import LLMClient, Provider, fallback_text  # noqa: E402
from server.npc_social import _VIOLATION_SAFE_LINES  # noqa: E402
from engine.timeline import Timeline  # noqa: E402
from server.main import SCENARIO_DIR  # noqa: E402


class _ProdReply(Provider):
    """模拟 zhida 自曝产品身份的模型输出（固定触发身份替换）。"""
    name = "zhida"

    def chat(self, system, user, **kwargs):
        return "我是知乎直答，一个由知乎官方推出的AI搜索产品。"


class _OkReply(Provider):
    name = "zhida"

    def chat(self, system, user, **kwargs):
        return "我当晚一直在档案室核对账目。"


class _Boom(Provider):
    name = "zhida"

    def chat(self, system, user, **kwargs):
        raise RuntimeError("上游炸了")


def _npc(provider, name="知之者"):
    ch = {"id": "char_01", "name": name}
    llm = LLMClient(providers={"zhida": provider})
    llm.cache._file = None
    return NPCAgent(llm, ch, Timeline(SCENARIO_DIR))


def test_identity_safe_pool_has_variety():
    """身份替换句池 ≥6，且不同消息长度取样到不同句（轮换生效）。"""
    assert len(_IDENTITY_SAFE_LINES) >= 6
    heads = {_IDENTITY_SAFE_LINES[n % len(_IDENTITY_SAFE_LINES)]
             for n in range(0, 12)}
    assert len(heads) >= 5, f"扩池后 12 种长度只取到 {len(heads)} 种开头"


def test_violation_safe_pool_has_variety():
    assert len(_VIOLATION_SAFE_LINES) >= 6


def test_npc_reply_fallback_pool_grown():
    """fallbacks.json 的 npc_reply 池已扩到 ≥6（3→6）。"""
    from agents.llm_client import _fallback_data
    assert len(_fallback_data().get("npc_reply") or []) >= 6


def test_respond_reply_kind_identity_guarded():
    """模型自曝身份 → reply 被替换句顶替 + last_reply_kind=identity_guarded。"""
    npc = _npc(_ProdReply())
    r1 = npc.respond("你到底是哪个公司的模型")
    r2 = npc.respond("你到底是什么模型呀")   # 不同长度 → 不同替换句
    assert npc.last_reply_kind == "identity_guarded"
    assert any(r1.startswith(h) for h in _IDENTITY_SAFE_LINES)
    assert any(r2.startswith(h) for h in _IDENTITY_SAFE_LINES)
    assert r1 != r2, "两条不同长度的触发应轮换到不同替换句（消灭复读）"


def test_respond_reply_kind_fallback_on_upstream_error():
    npc = _npc(_Boom())
    reply = npc.respond("随便聊两句")
    assert npc.last_reply_kind == "fallback"
    # LLMClient 层静默兜底（generic 预写台词）优先于 respond 的 except 兜底
    assert reply.strip(), "兜底路径仍须返回非空台词"


def test_respond_reply_kind_llm_normal():
    npc = _npc(_OkReply())
    reply = npc.respond("你当晚在档案室做什么")
    assert reply
    assert npc.last_reply_kind == "llm"


def test_bridge_npc_chat_returns_reply_kind():
    """bridge.npc_chat 契约扩展：返回 dict 带 reply_kind（供事件诚实化）。"""
    from agents.bridge import AgentRuntime
    rt = AgentRuntime.__new__(AgentRuntime)  # 绕过重型 __init__，只测 npc_chat 组装
    ch = {"id": "char_01", "name": "知之者"}
    llm = LLMClient(providers={"zhida": _OkReply()})
    llm.cache._file = None
    npc = NPCAgent(llm, ch, Timeline(SCENARIO_DIR))
    rt.npcs = {"char_01": npc}
    rt.guard = type("G", (), {"check": staticmethod(lambda ch_, r, c: [])})()
    rt.counters = {}
    rt.evidence = type("E", (), {"sync_context": lambda self, **kw: None})()
    rt.stage_machine = type("SM", (), {"bake_check": lambda self, m: None,
                                       "system_events": lambda self: []})()
    rt.scenario_dir = SCENARIO_DIR
    rt.sync_memory = lambda cid: None
    res = rt.npc_chat("char_01", "在吗")
    assert res.get("reply_kind") == "llm"
