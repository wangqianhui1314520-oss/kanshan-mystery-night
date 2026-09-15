"""G 原矩阵⑤：API 降级演练 —— 网关额度纪律 / 白名单 / 故障注入 / 缓存与恢复。

传输层故障注入点 = ZhihuGateway._call（认证调用唯一漏斗）；额度/白名单/缓存走真实代码路径。
全程零网络：_call 被注入伪造响应/异常，外层信封语义不变。

注（2026-09-14 比赛模式）：直答已取消本地每日额度与本地节流（额度裁决归知乎官方
响应），原「直答 1 次 → 第 2 次降级」守护改为「计数仍持久化 + 官方 429/超时走真实
降级信封、不伪造内容」。文件曾于并发重构中被清空，自 pyc 字节码重建（结构与
docstring 对齐原 11+ 项，并保留面板自建模型通道守护）。
"""
import asyncio
import json
import time

import httpx
import pytest

from server.gateway.zhihu_gateway import ZhihuGateway, GatewayError


def _fake_resp(status: int = 200, payload: dict | None = None) -> httpx.Response:
    """伪造 httpx.Response（注入 _call 用）。"""
    return httpx.Response(status_code=status, request=httpx.Request("POST", "https://drill"),
                          json=payload)


@pytest.fixture
def gw(tmp_path, monkeypatch):
    """标准演练网关：无凭证 / 热榜额度 1 / 无节流 / 独立缓存目录。"""
    for k in ("ZHIHU_ACCESS_SECRET", "ZHIHU_APP_KEY", "ZHIHU_GAME_QUOTA_ZHIDA",
              "ZHIHU_GAME_QUOTA_SEARCH", "ZHIHU_GAME_QUOTA_HOT",
              "ZHIHU_GAME_THROTTLE_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ZHIHU_GAME_QUOTA_HOT", "1")
    monkeypatch.setenv("ZHIHU_GAME_THROTTLE_SECONDS", "0")
    return ZhihuGateway("app", "key", tmp_path / "cache")


# ---------------------------------------------------------------------------
class TestQuotaDiscipline:
    def test_direct_answer_quota_exhaustion(self, gw, monkeypatch):
        """直答计数持久化（重启不涨）；官方限流 → 降级信封，不伪造内容。

        比赛模式语义更新：本地每日额度不再阻断直答（原「1 次成功 → 第 2 次
        降级」），官方 429 注入后仍走真实降级信封。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "fake-secret-for-drill")
        gw.access_secret = "fake-secret-for-drill"
        calls = {"n": 0}

        async def fake_call(kind, method, url, **kw):
            calls["n"] += 1
            return _fake_resp(200, {"choices": [{"message": {"content": f"答{calls['n']}"}}]})

        monkeypatch.setattr(gw, "_call", fake_call)
        r1 = asyncio.run(gw.direct_answer("问题一", bypass_cache=True))
        assert r1["ok"] is True and r1["source"] == "api"
        assert r1["data"]["content"] == "答1"

        async def limited(kind, method, url, **kw):
            raise GatewayError("http_error", "上游返回 HTTP 429 rate_limit_exceeded")

        monkeypatch.setattr(gw, "_call", limited)
        r2 = asyncio.run(gw.direct_answer("问题二", bypass_cache=True))
        assert r2["ok"] is False and r2["source"] == "fallback" and r2["degraded"] is True
        assert "429" in r2["notice"]
        assert gw._used("chat") == 1, "失败调用不计数"
        # 持久化：同目录重建网关，计数读回一致（重启不涨）
        g2 = ZhihuGateway("app", "key", gw.cache_dir)
        assert g2._used("chat") == 1

    def test_quota_file_shape(self, gw):
        """quotas.json 在首次计数后落盘；未计数时不预写（容错语义）。"""
        cache = gw.cache_dir / "quotas.json"
        assert not cache.exists()
        gw._count("hot")
        assert cache.exists()
        data = json.loads(cache.read_text(encoding="utf-8"))
        assert data[time.strftime("%Y-%m-%d")]["hot"] == 1


# ---------------------------------------------------------------------------
class TestDegradationEnvelopes:
    def test_no_credentials_hot_list(self, gw):
        """无凭证热榜 → 真实降级信封（degraded 标志=前端每日挑战灰化依据）+ 不耗额度。"""
        r = asyncio.run(gw.hot_list())
        assert r["ok"] is False and r["source"] == "fallback" and r["degraded"] is True
        assert "未配置 ZHIHU_ACCESS_SECRET" in r["notice"]
        assert gw._used("hot") == 0

    def test_hot_quota_exhausted_daily_challenge_unavailable(self, gw, monkeypatch):
        """额度耗尽分支：notice 明示「每日挑战不可用」——前端灰化直接依据。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "fake-secret-for-drill")
        gw.access_secret = "fake-secret-for-drill"
        gw._count("hot")                       # 额度 1/日，预置用尽
        r = asyncio.run(gw.hot_list())
        assert r["ok"] is False and r["degraded"] is True
        assert "每日挑战不可用" in r["notice"]

    def test_timeout_fault_injection(self, gw, monkeypatch):
        """直答网络超时 → fallback 信封 + 真实原因，不伪造内容、不耗额度。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "fake-secret-for-drill")
        gw.access_secret = "fake-secret-for-drill"

        async def boom(kind, method, url, **kw):
            raise GatewayError("network", "模拟超时（fault injection）")

        monkeypatch.setattr(gw, "_call", boom)
        r = asyncio.run(gw.direct_answer("问题", bypass_cache=True))
        assert r["ok"] is False and r["source"] == "fallback" and r["degraded"] is True
        assert "模拟超时" in r["notice"]
        assert gw._used("chat") == 0

    def test_429_rate_limit(self, gw, monkeypatch):
        """上游 429 → fallback + 真实原因。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "fake-secret-for-drill")
        gw.access_secret = "fake-secret-for-drill"

        async def rate_limited(kind, method, url, **kw):
            raise GatewayError("http_error", "上游返回 HTTP 429 rate_limit_exceeded")

        monkeypatch.setattr(gw, "_call", rate_limited)
        r = asyncio.run(gw.direct_answer("问题", bypass_cache=True))
        assert r["ok"] is False and r["source"] == "fallback" and r["degraded"] is True
        assert "429" in r["notice"]
        assert gw._used("chat") == 0

    def test_business_error_code(self, gw, monkeypatch):
        """上游业务错误码 → fallback。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "fake-secret-for-drill")
        gw.access_secret = "fake-secret-for-drill"

        async def fake_call(kind, method, url, **kw):
            return _fake_resp(200, {"Code": 10001, "Message": "参数/内容不可用"})

        monkeypatch.setattr(gw, "_call", fake_call)
        r = asyncio.run(gw.search("推理"))
        assert r["ok"] is False and r["source"] == "fallback" and r["degraded"] is True
        assert "10001" in r["notice"]
        assert gw._used("search") == 0

    def test_sync_chat_fallback_text(self, gw):
        """遗留同步入口 chat()：无凭证 → 明确标注的兜底文本（非真实生成内容）。"""
        text = gw.chat("系统", "你好")
        assert isinstance(text, str) and text.strip()
        assert "未配置" in gw.last_errors.get("chat", "")


# ---------------------------------------------------------------------------
class TestWhitelistGate:
    def test_search_outside_whitelist_rejected_free(self, gw, monkeypatch):
        """白名单外查询：拒绝且不消耗额度。"""
        async def must_not_call(kind, method, url, **kw):
            raise AssertionError("白名单外查询不应发起真实调用")

        monkeypatch.setattr(gw, "_call", must_not_call)
        r = asyncio.run(gw.search("量子物理超导实验"))
        assert r["ok"] is False and r["source"] == "rejected"
        assert "白名单" in r["notice"]
        assert gw._used("search") == 0

    def test_empty_query_rejected(self, gw):
        r = asyncio.run(gw.search("   "))
        assert r["ok"] is False and r["source"] == "rejected"
        assert "查询词为空" in r["notice"]


# ---------------------------------------------------------------------------
class TestCacheRecovery:
    def test_cache_hit_bypasses_quota(self, gw, monkeypatch):
        """缓存命中：无凭证/故障后仍可回放缓存（降级救回路径）。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "fake-secret-for-drill")
        gw.access_secret = "fake-secret-for-drill"
        calls = {"n": 0}

        async def fake_call(kind, method, url, **kw):
            calls["n"] += 1
            return _fake_resp(200, {"choices": [{"message": {"content": "缓存回放答案"}}]})

        monkeypatch.setattr(gw, "_call", fake_call)
        r1 = asyncio.run(gw.direct_answer("同一问题", bypass_cache=True))
        assert r1["ok"] is True and calls["n"] == 1
        # 随后注入网络故障 + 撤销凭证：同问题（允许缓存）命中回放，不再真实调用
        async def broken(kind, method, url, **kw):
            raise GatewayError("network", "故障注入")

        monkeypatch.setattr(gw, "_call", broken)
        gw.access_secret = ""
        r2 = asyncio.run(gw.direct_answer("同一问题"))
        assert r2["ok"] is True and r2["source"] == "cache"
        assert r2["data"]["content"] == "缓存回放答案"
        assert calls["n"] == 1, "缓存命中不应再发起真实调用"

    def test_hot_list_day_cache_shape(self, gw, monkeypatch):
        """热榜按天缓存键 + 白名单过滤字段落位。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "fake-secret-for-drill")
        gw.access_secret = "fake-secret-for-drill"
        calls = {"n": 0}

        async def fake_call(kind, method, url, **kw):
            calls["n"] += 1
            return _fake_resp(200, {"Code": 0, "Data": {"Items": [
                {"Title": "#看山失踪# 上热搜第一"},
                {"Title": "某欧洲球队签下新前锋"},
            ]}})

        monkeypatch.setattr(gw, "_call", fake_call)
        r1 = asyncio.run(gw.hot_list())
        assert r1["ok"] is True and r1["source"] == "api"
        assert r1["data"]["whitelist_filtered_out"] == 1
        assert len(r1["data"]["items"]) == 1
        day_key = f"hot_list_{time.strftime('%Y%m%d')}"
        assert (gw.cache_dir / f"{day_key}.json").exists()
        # 当日重复请求命中缓存不再真实调用
        r2 = asyncio.run(gw.hot_list())
        assert r2["ok"] is True and r2["source"] == "cache"
        assert calls["n"] == 1, "缓存命中不应再发起真实调用"


# ---------------------------------------------------------------------------
# 设置面板自建模型（DeepSeek 等）通道守护（2026-09-14 用户实测复现根因）
# ---------------------------------------------------------------------------

def test_openai_provider_explicit_creds_survive_sync_env(monkeypatch):
    """凭证锁：use_credentials 注入后，chat 内部 _sync_env 不得用进程 env
    覆盖实例凭证（否则面板填的 DeepSeek key 会被 env 值静默顶替——探针假阳性）。"""
    import os

    from agents.llm_client import OpenAICompatProvider
    monkeypatch.setenv("LLM_API_KEY", "sk-env-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    p = OpenAICompatProvider()
    p.use_credentials("sk-panel-key", "https://api.deepseek.com/v1", "deepseek-chat")
    p._sync_env()                      # 模拟 chat() 内部调用
    assert p.api_key == "sk-panel-key"
    assert p.base_url == "https://api.deepseek.com/v1"
    assert p.model == "deepseek-chat"
    # 未锁定实例仍遵循 env（默认语义不变）
    q = OpenAICompatProvider()
    q._sync_env()
    assert q.api_key == "sk-env-key"


def test_panel_main_config_displaces_zhida_slot(monkeypatch):
    """面板三件套齐全 → _llm_for_session 返回的 LLMClient 不注册 zhida 槽：
    call_gateway(provider="zhida") 降级落 main（DeepSeek 生效），而不是被
    env 恒可用的知乎凭证永久抢占（面板配置失效的根因）。

    BYOK 隔离（2026-09-15）：凭证经 use_credentials 显式锁进 Provider 实例，
    **不再写进程 env**（旧版断言 env 被改写 = 锁副作用本身，与跨会话凭证
    借用问题同源，已随 P1 修复更新语义）。"""
    import os

    import server.main as main_mod
    monkeypatch.setenv("ZHIHU_AI_DEFAULT", "1")
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "sk-zhihu-always-available")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    cfg = {"llm_key": "sk-panel", "llm_base": "https://api.deepseek.com/v1",
           "llm_model": "deepseek-chat"}
    monkeypatch.setattr(main_mod.app.state, "api_cfg", {"__panel_test__": cfg},
                        raising=False)
    client = main_mod.GameServer._llm_for_session(main_mod.game_server, "__panel_test__")
    assert client is not None
    assert "zhida" not in client.providers, "面板配置存在时不得注册 zhida 槽位"
    prov_main = client.providers["main"]
    assert prov_main.api_key == "sk-panel"
    assert prov_main.base_url == "https://api.deepseek.com/v1"
    assert prov_main.model == "deepseek-chat"
    assert getattr(prov_main, "_explicit_creds", False), \
        "面板凭证必须经 use_credentials 显式锁进实例（不落进程 env）"
    assert os.environ.get("LLM_BASE_URL") != "https://api.deepseek.com/v1", \
        "面板凭证不得泄漏到进程 env（否则未设 key 的会话会借到）"
    picked = client._pick("zhida")     # NPC 对话写死 provider="zhida"
    assert picked.name == "main"
    # 无面板配置的会话仍走默认通道（zhida 保留，行为不变）
    plain = main_mod.GameServer._llm_for_session(main_mod.game_server, "__plain__")
    assert plain is not None and "zhida" in plain.providers
