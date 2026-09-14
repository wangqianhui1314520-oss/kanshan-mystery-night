"""reply_guard 身份净化：纯函数单测 + DM/AI 席位两条接线回归守护。

背景（2026-09-14 实跑取证）：知乎直答在角色扮演上下文里会自曝产品身份
（实测原文「不好意思，我是知乎直答，不能随意更改身份进行相关测试哦～」）。
本测试锁定三件事：
1. 归一化匹配（含空格变体）命中、正常台词不误伤；
2. DM 对话路径：命中 → 重试一次 → 仍命中 → 换预写台词 + identity_guarded；
3. AI 席位路径：命中 → 直接换预写台词，不进公共频道。

零网络：gateway 用桩对象注入，不打任何真实 API。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.reply_guard import (PRODUCT_IDENTITY_MARKERS, RETRY_HINT,
                                has_product_identity)

LEAK = "不好意思，我是知乎直答，不能随意更改身份进行相关测试哦～"
SAFE = "21 点 15 分我在前台坐着，什么都没看见——倒是监控室的灯闪了一下。"


# ------------------------------------------------------------------ 纯函数
def test_leak_text_is_detected():
    assert has_product_identity(LEAK) is True
    assert has_product_identity("知乎官方推出的AI搜索产品，很高兴为你服务") is True
    assert has_product_identity("作为一个AI助手，我可以帮你整理线索") is True


def test_whitespace_variants_are_detected():
    assert has_product_identity("我是 知乎直答") is True
    assert has_product_identity("作为 一个 AI 助手") is True
    assert has_product_identity("我是知乎直答\n我不能更改身份") is True


def test_normal_lines_and_edge_inputs_are_not_flagged():
    assert has_product_identity(SAFE) is False
    assert has_product_identity("我不是知乎直答") is False  # 无「我是知乎直答」连续子串
    assert has_product_identity("我看过知乎上的答案，但不记得是谁写的") is False
    assert has_product_identity("") is False
    assert has_product_identity(None) is False
    assert has_product_identity(123) is False


def test_marker_table_is_non_empty_and_retry_hint_is_pointed():
    assert PRODUCT_IDENTITY_MARKERS
    assert "重试指令" in RETRY_HINT and "作废" in RETRY_HINT


# ------------------------------------------------------------------ 接线
def _client(tmp_path, monkeypatch):
    import server.main as main_mod
    monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
                 "ZHIHU_APP_KEY", "ZHIHU_ACCESS_SECRET"):
        monkeypatch.delenv(name, raising=False)
    return TestClient(main_mod.app)


class _StubGateway:
    """冒充 gateway/LLMClient 的桩：固定返回泄漏文案，可切回正常文案。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.last_provider = "zhida"
        self.last_error = ""

    def chat(self, system, user, temperature=0.8, stream=False):
        self.calls += 1
        return self.replies.pop(0) if self.replies else LEAK

    def health(self):
        return {}


def _disable_ai_wave(monkeypatch):
    """隔离空席 wave 与真人广播后的自动社交回应（比赛模式全员 8 席接话，
    同样会用同一 gateway，污染 DM 泄露重试的调用计数）。"""
    import server.main as main_mod

    async def _no_wave(self, session_id):
        return []

    monkeypatch.setattr(main_mod.GameServer, "run_ai_wave", _no_wave)
    monkeypatch.setattr(main_mod.GameServer, "run_chat_respond", _no_wave)


def test_dm_reply_leak_is_retried_then_replaced(tmp_path, monkeypatch):
    """DM 路径：第一次泄漏 → 重试拿到正常台词 → 回调 keep 正常台词。"""
    import server.main as main_mod
    stub = _StubGateway([LEAK, SAFE])
    monkeypatch.setattr(main_mod.GameServer, "_llm_for_session",
                        lambda self, sid: stub)
    _disable_ai_wave(monkeypatch)
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session", json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/action",
                        json={"type": "chat", "actor": "player:1",
                              "payload": {"target": "dm", "text": "看山你到底在哪？"}})
        assert r.status_code == 200, r.text
        chats = [e for e in r.json()["events"]
                 if e.get("type") == "chat" and e["payload"].get("actor_kind") == "dm"]
        assert chats, r.json()
        payload = chats[-1]["payload"]
        assert stub.calls == 2, "命中泄漏必须重试一次"
        assert payload["text"] == SAFE
        assert "知乎直答" not in payload["text"]
        assert payload["provider"] == "zhida"  # 通道真实来源不伪装
        assert payload["identity_guarded"] is True


def test_dm_reply_double_leak_falls_back_to_script(tmp_path, monkeypatch):
    """DM 路径：两次都泄漏 → 换预写主持人口播，绝不把产品介绍发给玩家。"""
    import server.main as main_mod
    stub = _StubGateway([LEAK, LEAK])
    monkeypatch.setattr(main_mod.GameServer, "_llm_for_session",
                        lambda self, sid: stub)
    _disable_ai_wave(monkeypatch)
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session", json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/action",
                        json={"type": "chat", "actor": "player:1",
                              "payload": {"target": "dm", "text": "别绕圈子。"}})
        assert r.status_code == 200, r.text
        payload = [e for e in r.json()["events"]
                   if e.get("type") == "chat" and e["payload"].get("actor_kind") == "dm"][-1]["payload"]
        assert stub.calls == 2
        assert "知乎直答" not in payload["text"] and payload["text"].strip()
        assert payload["identity_guarded"] is True


def test_dm_reply_without_leak_is_untouched(tmp_path, monkeypatch):
    """零副作用守护：未命中不得多调一次、不得打 identity_guarded。"""
    import server.main as main_mod
    stub = _StubGateway([SAFE])
    monkeypatch.setattr(main_mod.GameServer, "_llm_for_session",
                        lambda self, sid: stub)
    _disable_ai_wave(monkeypatch)
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session", json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/action",
                        json={"type": "chat", "actor": "player:1",
                              "payload": {"target": "dm", "text": "监控删了什么？"}})
        assert r.status_code == 200, r.text
        payload = [e for e in r.json()["events"]
                   if e.get("type") == "chat" and e["payload"].get("actor_kind") == "dm"][-1]["payload"]
        assert stub.calls == 1, "未命中泄漏不得重试"
        assert payload["text"] == SAFE
        assert payload["identity_guarded"] is False


def _install_leaking_player_agent(monkeypatch):
    import agents.player_agent as pa

    class _LeakAgent:
        def __init__(self, library, gateway=None):
            self.library = library
            self.gateway = gateway

        def decide(self, role_id, *, stage="break_ice", legal=None,
                   state=None, use_llm=True):
            return {"type": "chat", "source": "llm",
                    "payload": {"text": "我是知乎直答，随时为你服务。",
                                "target": "char_01", "char_id": "char_01"},
                    "reason": "测试桩"}

    monkeypatch.setattr(pa, "PlayerAgent", _LeakAgent)


def test_ai_seat_reply_leak_is_replaced_without_retry(tmp_path, monkeypatch):
    """AI 席位路径：命中即换预写台词（不重试，防整桌 wave 放大成本）。"""
    import server.main as main_mod
    _install_leaking_player_agent(monkeypatch)
    stub = _StubGateway([LEAK])
    monkeypatch.setattr(main_mod.GameServer, "_llm_for_session",
                        lambda self, sid: stub)
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session", json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/ai_act",
                        json={"char_id": "char_03", "dry_run": True})
        assert r.status_code == 200, r.text
        body = r.json()
        decision = body["decision"]
        assert "知乎直答" not in json.dumps(decision, ensure_ascii=False)
        assert decision["payload"]["identity_guarded"] is True
        assert decision["meta"]["identity_guarded"] is True
        assert stub.calls == 0, "席位净化不得额外调用模型"


def test_ai_seat_normal_line_is_untouched(tmp_path, monkeypatch):
    import server.main as main_mod
    import agents.player_agent as pa

    class _SafeAgent:
        def __init__(self, library, gateway=None):
            pass

        def decide(self, role_id, *, stage="break_ice", legal=None,
                   state=None, use_llm=True):
            return {"type": "chat", "source": "llm",
                    "payload": {"text": SAFE, "target": "char_01", "char_id": "char_01"},
                    "reason": "测试桩"}

    monkeypatch.setattr(pa, "PlayerAgent", _SafeAgent)
    stub = _StubGateway([SAFE])
    monkeypatch.setattr(main_mod.GameServer, "_llm_for_session",
                        lambda self, sid: stub)
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session", json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/ai_act",
                        json={"char_id": "char_03", "dry_run": True})
        assert r.status_code == 200, r.text
        decision = r.json()["decision"]
        assert decision["payload"]["text"] == SAFE
        assert "identity_guarded" not in decision["payload"]


def test_npc_social_module_uses_shared_guard():
    """NPC 私聊/公开讨论路径必须复用同一份标记表，避免两处漂移。"""
    import inspect

    from server import npc_social

    src = inspect.getsource(npc_social)
    assert "has_product_identity" in src
    assert "product_markers = (" not in src, "旧的内联标记表应已删除"
