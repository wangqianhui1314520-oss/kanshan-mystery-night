"""知乎素材桥零网络测试：mock 唯一出网点 _request_json，不触网。

铁律：本文件 fixture 显式清空全部 AI/知乎凭证（game/.env 经 conftest
load_dotenv 会污染进程 env），确保 Z2 未配置路径与降级路径可测。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import zhihu_bridge as zb


@pytest.fixture(autouse=True)
def _clean_credentials(monkeypatch):
    """每个测试独立清空凭证：防 .env 真凭证泄漏进 Z2 降级判定。"""
    for key in ("ZHIHU_APP_KEY", "ZHIHU_ZHIDA_URL", "ZHIHU_ACCESS_SECRET",
                "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)


class _Counter:
    """统计 _request_json 调用次数，断言缓存命中零请求。"""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self, url, headers=None):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


STORY_LIST = [
    {"work_id": "w1", "title": "山中来信", "artwork": "", "description": "d1",
     "labels": ["悬疑"]},
    {"work_id": "w2", "title": "看守所之夜", "artwork": "", "description": "d2",
     "labels": ["本格"]},
]

STORY_DETAIL = {
    "work_id": "w1", "title": "山中来信", "chapter_name": "第一章",
    "author_name": "档案员甲", "labels": ["悬疑"],
    "introduction": "intro", "content": "正文内容",
}


def _patch(monkeypatch, result) -> _Counter:
    counter = _Counter(result)
    monkeypatch.setattr(zb, "_request_json", counter)
    return counter


# ---------------------------------------------------------------- Z1 列表与详情

def test_fetch_story_list_parses(tmp_path, monkeypatch):
    counter = _patch(monkeypatch, STORY_LIST)
    items = zb.fetch_story_list(cache_dir=tmp_path)
    assert items == STORY_LIST
    assert counter.calls == 1
    assert items[0]["work_id"] == "w1"
    # 裸数组外的 {items: [...]} 包装也能解包
    counter2 = _patch(monkeypatch, {"items": STORY_LIST})
    assert zb.fetch_story_list(cache_dir=tmp_path / "alt") == STORY_LIST
    assert counter2.calls == 1


def test_fetch_story_detail_parses(tmp_path, monkeypatch):
    counter = _patch(monkeypatch, STORY_DETAIL)
    detail = zb.fetch_story("w1", cache_dir=tmp_path)
    assert detail["chapter_name"] == "第一章"
    assert detail["author_name"] == "档案员甲"
    assert counter.calls == 1
    assert detail["work_id"] == "w1"


def test_fetch_story_url_contract(tmp_path, monkeypatch):
    """详情路径必须是 story/{work_id}（knowledge 详情共用，不得发明新路径）。"""
    captured = {}

    def fake_request(url, headers=None):
        captured["url"] = url
        return STORY_DETAIL

    monkeypatch.setattr(zb, "_request_json", fake_request)
    zb.fetch_story("w1", cache_dir=tmp_path)
    assert captured["url"] == \
        "https://api.zhihu.com/km-indep-home/hackathon/v2/story/w1"
    zb.fetch_work("w1", kind="knowledge", cache_dir=tmp_path)
    assert captured["url"].endswith("/story/w1")


def test_fetch_knowledge_list_parses(tmp_path, monkeypatch):
    counter = _patch(monkeypatch, [{"work_id": "k1", "title": "山区地质"}])
    items = zb.fetch_knowledge_list(cache_dir=tmp_path)
    assert items[0]["work_id"] == "k1"
    assert counter.calls == 1


# ---------------------------------------------------------------- 缓存命中

def test_cache_hit_no_second_request(tmp_path, monkeypatch):
    counter = _patch(monkeypatch, STORY_LIST)
    assert zb.fetch_story_list(cache_dir=tmp_path) == STORY_LIST
    assert zb.fetch_story_list(cache_dir=tmp_path) == STORY_LIST
    assert counter.calls == 1  # 第二次走缓存，零网络

    counter_d = _patch(monkeypatch, STORY_DETAIL)
    zb.fetch_story("w1", cache_dir=tmp_path)
    zb.fetch_story("w1", cache_dir=tmp_path)
    assert counter_d.calls == 1


def test_cache_ttl_expiry_triggers_refetch(tmp_path, monkeypatch):
    counter = _patch(monkeypatch, STORY_DETAIL)
    zb.fetch_story("w1", cache_dir=tmp_path)
    assert counter.calls == 1
    # 人为把 fetched_at 拨回 25 小时前 → 过期 → 重新请求
    cache_file = tmp_path / "story_w1.json"
    wrapper = json.loads(cache_file.read_text(encoding="utf-8"))
    wrapper["fetched_at"] -= 25 * 3600
    cache_file.write_text(json.dumps(wrapper), encoding="utf-8")
    zb.fetch_story("w1", cache_dir=tmp_path)
    assert counter.calls == 2


# ---------------------------------------------------------------- 网络异常降级

def test_network_error_returns_none(tmp_path, monkeypatch):
    import httpx
    _patch(monkeypatch, httpx.ConnectError("boom"))
    assert zb.fetch_story_list(cache_dir=tmp_path) is None
    assert zb.fetch_story("w1", cache_dir=tmp_path) is None
    assert zb.fetch_knowledge_list(cache_dir=tmp_path) is None
    assert zb.fetch_work("w1", kind="story", cache_dir=tmp_path) is None


def test_malformed_payload_returns_none(tmp_path, monkeypatch):
    _patch(monkeypatch, {"unexpected": 1})          # 无法解包的列表响应
    assert zb.fetch_story_list(cache_dir=tmp_path) is None
    _patch(monkeypatch, ["not", "a", "dict"])       # 详情必须是 dict
    assert zb.fetch_story("w1", cache_dir=tmp_path) is None
    assert zb.fetch_work("w1", kind="bad", cache_dir=tmp_path) is None  # 非法 kind


# ---------------------------------------------------------------- 署名台账

def test_credits_ledger_written_and_deduped(tmp_path, monkeypatch):
    counter = _patch(monkeypatch, STORY_LIST)
    zb.fetch_story_list(cache_dir=tmp_path)
    _patch(monkeypatch, STORY_DETAIL)          # 详情接口返回 dict 载荷
    zb.fetch_story("w1", cache_dir=tmp_path)   # 详情补全 author_name
    ledger_path = tmp_path / "credits_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    by_id = {e["work_id"]: e for e in ledger}
    assert set(by_id) == {"w1", "w2"}
    assert ledger_path.exists()
    assert "source_url" in by_id["w1"]

    # 重复拉取（清缓存强制走网络）→ 台账不产生重复 work_id
    (tmp_path / "story_list.json").unlink()
    (tmp_path / "story_w1.json").unlink()
    counter2 = _patch(monkeypatch, STORY_LIST)
    zb.fetch_story_list(cache_dir=tmp_path)
    _patch(monkeypatch, STORY_DETAIL)
    zb.fetch_story("w1", cache_dir=tmp_path)
    ledger2 = json.loads(ledger_path.read_text(encoding="utf-8"))
    ids2 = [e["work_id"] for e in ledger2]
    assert len(ids2) == len(set(ids2))
    assert counter.calls + counter2.calls >= 2


# ---------------------------------------------------------------- sanitize_excerpt

def test_sanitize_excerpt_strips_controls_and_truncates():
    evil = "正常\x1b[31m注入\x07文本\n\t保留" + "长" * 2000
    out = zb.sanitize_excerpt(evil, max_len=100)
    assert "\x1b" not in out and "\x07" not in out
    assert "\n" in out and "\t" in out          # 换行/制表保留
    assert len(out) <= 101                      # 截断 + 省略号
    assert out.endswith("…")
    assert zb.sanitize_excerpt(None) == ""
    assert zb.sanitize_excerpt(12345) == ""
    assert zb.sanitize_excerpt("") == ""
    default = zb.sanitize_excerpt("a" * 3000)
    assert len(default) == 1201                 # 默认 max_len=1200


# ---------------------------------------------------------------- Z2 开放平台

def test_z2_without_secret_returns_none(monkeypatch):
    # autouse fixture 已清空凭证；未配置 → 不发请求直接 None
    def fail(url, headers=None):
        raise AssertionError("未配置凭证不得发请求")

    monkeypatch.setattr(zb, "_request_json", fail)
    assert zb.fetch_hot() is None
    assert zb.search_zhihu("看山") is None


def test_z2_with_secret_parses(monkeypatch):
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "test-secret-do-not-log")
    captured = {}

    def fake_request(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        return {"Code": 0, "Data": {"Items": [{"Title": "热榜一条",
                                               "Url": "https://zhihu.com/q/1"}]}}

    monkeypatch.setattr(zb, "_request_json", fake_request)
    hot = zb.fetch_hot(limit=5)
    assert hot[0]["Title"] == "热榜一条"
    assert "Limit=5" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer test-secret-do-not-log"
    assert "X-Request-Timestamp" in captured["headers"]

    def fake_search(url, headers=None):
        captured["url"] = url
        return {"Code": 0, "Data": {"Items": [{"Title": "搜索结果"}]}}

    monkeypatch.setattr(zb, "_request_json", fake_search)
    assert zb.search_zhihu("看山", count=99)[0]["Title"] == "搜索结果"
    assert "Query=" in captured["url"] and "Count=10" in captured["url"]  # 上限截断


def test_z2_api_error_returns_none(monkeypatch):
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "test-secret")
    _patch(monkeypatch, {"Code": 20001, "Message": "鉴权失败"})
    assert zb.fetch_hot() is None
    assert zb.search_zhihu("看山") is None


# ---------------------------------------------------------------- 异步包装器

def test_async_wrappers_work(tmp_path, monkeypatch):
    import asyncio
    _patch(monkeypatch, STORY_DETAIL)

    async def main():
        return await zb.fetch_story_async("w1", cache_dir=tmp_path)

    detail = asyncio.run(main())
    assert detail["title"] == "山中来信"
