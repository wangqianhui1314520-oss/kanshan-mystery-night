"""LLM_PRIMARY=main 通道开关回归守护（零网络）。

背景（2026-09-15 实测）：NPC/DM 统一用 provider="zhida" 调用，而
LLMClient._pick 的降级序是 zhida→main→mock。只要知乎凭证可用，.env 里
配的自建 LLM（DeepSeek）永远排不上号——NPC 不会调用它。
LLM_PRIMARY=main 让 _llm_for_session 只注册 main（+mock），
provider="zhida" 的请求经 _pick 自然落到 main。

守护三条：
1. LLM_PRIMARY=main + 三件套齐全 → 只注册 main/mock，且 _pick("zhida") 命中 main；
2. 凭证取自 cfg/env 回退链（base=api.deepseek.com、model 原样透传）；
3. 未设 LLM_PRIMARY（或设为 zhida）→ 维持比赛默认：zhida 槽位仍在，行为不回退。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

GAME_ROOT = Path(__file__).resolve().parents[1]
if str(GAME_ROOT) not in sys.path:
    sys.path.insert(0, str(GAME_ROOT))

DS_KEY = "sk-unit-test-not-real"
DS_BASE = "https://api.deepseek.com"
DS_MODEL = "deepseek-flash"


@pytest.fixture()
def server_main(monkeypatch):
    """装配一套完整的"服务器 .env"凭证：自建 LLM 三件套 + 知乎 Secret 并存。"""
    for key in ("ZHIHU_ACCESS_SECRET", "ZHIHU_APP_KEY", "ZHIHU_ZHIDA_URL",
                "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_PRIMARY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_API_KEY", DS_KEY)
    monkeypatch.setenv("LLM_BASE_URL", DS_BASE)
    monkeypatch.setenv("LLM_MODEL", DS_MODEL)
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "dummy-zhihu-secret")
    monkeypatch.setenv("ZHIHU_AI_DEFAULT", "1")
    import server.main as m
    return m


def test_primary_main_registers_only_main(server_main, monkeypatch):
    monkeypatch.setenv("LLM_PRIMARY", "main")
    client = server_main.game_server._llm_for_session("__unit__")
    assert client is not None
    assert set(client.providers) == {"main", "mock"}
    # 关键：NPC/DM 走 provider="zhida"，必须自然落到 main（DeepSeek）
    assert client._pick("zhida").name == "main"


def test_primary_main_uses_env_credentials(server_main, monkeypatch):
    monkeypatch.setenv("LLM_PRIMARY", "main")
    client = server_main.game_server._llm_for_session("__unit__")
    prov = client.providers["main"]
    assert prov.base_url == DS_BASE
    assert prov.model == DS_MODEL
    assert prov.api_key == DS_KEY


@pytest.mark.parametrize("value", ["", "zhida"])
def test_without_primary_keeps_zhida_default(server_main, monkeypatch, value):
    """比赛默认语义不变：未显式指定 main 时知乎直答仍是主通道。"""
    if value:
        monkeypatch.setenv("LLM_PRIMARY", value)
    client = server_main.game_server._llm_for_session("__unit__")
    assert "zhida" in client.providers
    assert client._pick("zhida").name == "zhida"


def test_primary_main_falls_back_to_zhida_when_main_fails():
    """主通道（DeepSeek）抖动时必须回落备用通道，不能整局 ai_reply_failed。

    回归背景：providers 收敛成 {main, mock} 后主通道一挂就无路可走，
    比改动前（zhida 优先）更脆——这里用桩件锁住该行为。
    """

    class _Boom:
        name = "main"

        def available(self):
            return True

        def chat(self, *a, **k):
            raise RuntimeError("HTTP 429 rate limited")

    class _Backup:
        name = "zhida"

        def available(self):
            return True

        def chat(self, *a, **k):
            return "回落通道接上了"

    from server.main import _MainWithBackup
    chain = _MainWithBackup(_Boom(), _Backup())
    assert chain.available()
    assert chain.chat("sys", "user") == "回落通道接上了"
    assert chain.backup_used is True


def test_primary_main_no_backup_reraises():
    """无可用备用通道时，异常必须原样抛出（如实降级，不吞错）。"""

    class _Boom:
        name = "main"

        def available(self):
            return True

        def chat(self, *a, **k):
            raise RuntimeError("boom")

    from server.main import _MainWithBackup
    chain = _MainWithBackup(_Boom(), None)
    with pytest.raises(RuntimeError, match="boom"):
        chain.chat("sys", "user")


def test_primary_main_ignored_when_credentials_incomplete(server_main, monkeypatch):
    """三件套不全时不该"半启用"：退回默认通道，避免注册一个空 main。"""
    monkeypatch.setenv("LLM_PRIMARY", "main")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    client = server_main.game_server._llm_for_session("__unit__")
    assert "zhida" in client.providers
