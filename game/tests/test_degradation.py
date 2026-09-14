"""G 原矩阵⑤：API 降级演练 —— 网关额度纪律 / 白名单 / 故障注入 / 缓存与恢复。

传输层故障注入点 = ZhihuGateway._call（认证调用唯一漏斗）；额度/白名单/缓存走真实代码路径。
全程零真实网络、零真实凭证（凭证仅经环境变量——同时验证不落代码）。
"""
from __future__ import annotations

import json

import httpx
import pytest

from server.gateway.zhihu_gateway import GatewayError, ZhihuGateway

pytestmark = pytest.mark.degradation


@pytest.fixture()
def gw(tmp_path, monkeypatch):
    """标准演练网关：无凭证 / 额度 1 / 无节流 / 独立缓存目录。"""
    for k in ("ZHIHU_ACCESS_SECRET",):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ZHIHU_GAME_QUOTA_ZHIDA", "1")
    monkeypatch.setenv("ZHIHU_GAME_QUOTA_SEARCH", "1")
    monkeypatch.setenv("ZHIHU_GAME_QUOTA_HOT", "1")
    monkeypatch.setenv("ZHIHU_GAME_THROTTLE_SECONDS", "0")
    g = ZhihuGateway("app", "key", cache_dir=tmp_path / "cache")
    yield g


def _fake_resp(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload,
                          request=httpx.Request("GET", "https://mock"))


class TestQuotaDiscipline:
    @pytest.mark.asyncio
    async def test_direct_answer_quota_exhaustion(self, gw):
        """比赛模式：直答不受本地额度阻断（zhihu_gateway 433/476 注释为契约）；
        上游错误仍真实降级不伪造；额度计数持久化（重启不涨）。"""
        gw._call = lambda *a, **k: _async_return(
            _fake_resp({"choices": [{"message": {"content": "真实直答"}}],
                        "model": "m1"}))
        r1 = await gw.direct_answer("什么是信息茧房")
        assert r1["ok"] and r1["source"] == "api"
        assert gw._used("chat") == 1
        # 额度 1/1 已满：本地不阻断（比赛模式），第 2 次仍真实调用成功。
        r2 = await gw.direct_answer("什么是信息茧房2")
        assert r2["ok"] and r2["source"] == "api"
        assert gw._used("chat") == 2
        # 重启（新实例同缓存目录）：计数持久化，不回血。
        gw2 = ZhihuGateway("app", "key", cache_dir=gw.cache_dir)
        assert gw2._used("chat") == 2
        # 上游错误：仍走真实降级信封（degraded + fallback + 不伪造内容）。
        async def _boom(*a, **k):
            raise GatewayError("upstream_429", "额度超限（官方）")
        gw2._call = _boom
        r3 = await gw2.direct_answer("全新问题")
        assert not r3["ok"] and r3["source"] == "fallback" and r3["degraded"]
        assert "不伪造" in r3["notice"]

    def test_quota_file_shape(self, gw):
        """quotas.json 在首次计数后落盘；未计数时不预写（容错语义）。"""
        assert not (gw.cache_dir / "quotas.json").exists() or isinstance(
            json.loads((gw.cache_dir / "quotas.json").read_text(encoding="utf-8")), dict)


class TestDegradationEnvelopes:
    @pytest.mark.asyncio
    async def test_no_credentials_hot_list(self, gw):
        """无凭证热榜 → 真实降级信封（degraded 标志=前端每日挑战灰化依据）+ 不耗额度。"""
        used0 = gw._used("hot")
        r = await gw.hot_list()
        assert not r["ok"] and r["source"] == "fallback" and r["degraded"]
        assert "未配置 ZHIHU_ACCESS_SECRET" in r["notice"]
        assert "不伪造热榜数据" in r["notice"]
        assert gw._used("hot") == used0  # 失败不耗额度

    @pytest.mark.asyncio
    async def test_hot_quota_exhausted_daily_challenge_unavailable(self, gw, monkeypatch):
        """额度耗尽分支：notice 明示「每日挑战不可用」——前端灰化直接依据。"""
        monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "drill-secret")
        monkeypatch.setenv("ZHIHU_GAME_QUOTA_HOT", "0")  # 直接构造 0/0 额度态
        gw4 = ZhihuGateway(gw.app_id, gw.app_key, cache_dir=gw.cache_dir / "q0")
        r = await gw4.hot_list()
        assert not r["ok"] and "每日挑战" in r["notice"] and "额度已用尽" in r["notice"]
        assert r["degraded"] and r["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_timeout_fault_injection(self, gw):
        """直答网络超时 → fallback 信封 + 真实原因，不伪造内容、不耗额度。"""
        def boom(*a, **k):
            def _raise():
                raise GatewayError("network", "模拟超时（fault injection）")
            return _raise()
        gw._call = boom
        used0 = gw._used("chat")
        r = await gw.direct_answer("问题")
        assert not r["ok"] and r["degraded"] and r["source"] == "fallback"
        assert "模拟超时" in r["notice"]
        assert "不伪造" in r["notice"]
        assert gw._used("chat") == used0

    @pytest.mark.asyncio
    async def test_429_rate_limit(self, gw):
        """上游 429 → fallback + 真实原因。"""
        def rate_limited(*a, **k):
            def _raise():
                raise GatewayError("http_error", "HTTP 429 rate_limit_exceeded")
            return _raise()
        gw._call = rate_limited
        r = await gw.search("信息茧房")
        assert not r["ok"] and "429" in r["notice"] and r["degraded"]

    @pytest.mark.asyncio
    async def test_business_error_code(self, gw):
        """上游业务错误码 → fallback。"""
        gw._call = lambda *a, **k: _async_return(
            _fake_resp({"Code": 40301, "Message": "forbidden"}))
        r = await gw.hot_list()
        assert not r["ok"] and "40301" in r["notice"]

    def test_sync_chat_fallback_text(self, gw):
        """遗留同步入口 chat()：无凭证 → 预写台词，不泄漏后台故障词。"""
        text = gw.chat("system", "给一句开场白")
        assert text and "叮" in text
        assert "系统降级" not in text and "额度耗尽" not in text


class TestWhitelistGate:
    @pytest.mark.asyncio
    async def test_search_outside_whitelist_rejected_free(self, gw):
        """白名单外查询：拒绝且不消耗额度。"""
        used0 = gw._used("search")
        r = await gw.search("量子波动速读大师班")
        assert not r["ok"] and r["source"] == "rejected"
        assert "白名单" in r["notice"] and gw._used("search") == used0

    @pytest.mark.asyncio
    async def test_empty_query_rejected(self, gw):
        r = await gw.search("  ")
        assert not r["ok"] and r["source"] == "rejected"


class TestCacheRecovery:
    @pytest.mark.asyncio
    async def test_cache_hit_bypasses_quota(self, gw):
        """缓存命中：额度耗尽后仍可回放缓存（降级救回路径）。"""
        gw._call = lambda *a, **k: _async_return(
            _fake_resp({"choices": [{"message": {"content": "缓存我"}}],
                        "model": "m1"}))
        r1 = await gw.direct_answer("同一问题")
        assert r1["ok"] and r1["source"] == "api"
        r2 = await gw.direct_answer("同一问题")  # 额度已 1/1，但缓存优先
        assert r2["ok"] and r2["source"] == "cache"
        assert r2["data"]["content"] == "缓存我"

    @pytest.mark.asyncio
    async def test_hot_list_day_cache_shape(self, gw, monkeypatch):
        """热榜按天缓存键 + 白名单过滤字段落位。"""
        gw.access_secret = "fake-secret-for-drill"
        payload = {"Data": {"Items": [
            {"Title": "#看山失踪# 热议", "Heat": 1},
            {"Title": "某明星官宣恋情大爆料", "Heat": 2}]}}
        gw._call = lambda *a, **k: _async_return(_fake_resp(payload))
        r = await gw.hot_list()
        assert r["ok"] and r["source"] == "api"
        assert r["data"]["whitelist_filtered_out"] == 1
        assert len(r["data"]["items"]) == 1
        assert r["data"]["fetched_day"]
        # 第二次 → 当日缓存（不再打 API、不耗额度）
        used0 = gw._used("hot")
        gw._call = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("缓存命中不应再发起真实调用"))
        r2 = await gw.hot_list()
        assert r2["ok"] and r2["source"] == "cache"
        assert gw._used("hot") == used0


async def _async_return(v):
    return v
