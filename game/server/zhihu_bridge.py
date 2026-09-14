"""知乎素材桥（M0）：黑客松内容 API + 开放平台可选能力，统一出口。

⚠️ 安全警示（调用方必读）：
本模块返回的 title/author/content 等字段均来自外部网络，属于**不可信内容**。
调用方**不得**将 content 原文直接拼进 LLM system prompt（存在提示注入风险）。
应先用 sanitize_excerpt() 提取摘要，或仅在 UI 层展示原文。

能力组：
- Z1 黑客松内容 API（无鉴权，核心）：故事列表/详情、知识列表，磁盘缓存 24h，
  成功拉取自动登记署名台账（credits_ledger.json）。
- Z2 开放平台（可选）：热榜/站内搜索，需环境变量 ZHIHU_ACCESS_SECRET（Bearer 鉴权），
  未配置或任何失败一律返回 None，上层优雅降级。Access Secret 绝不写入代码或日志。

所有函数均为同步实现；异步调用方请使用 *_async 的 to_thread 包装器。
任何网络/解析异常都不抛出——返回 None，由上层降级处理。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

GAME_ROOT = Path(__file__).resolve().parents[1]

# Z1 黑客松内容 API（官方 REST 端点，域名与路径写死，不得改）
_HACKATHON_API = "https://api.zhihu.com/km-indep-home/hackathon/v2"
# Z2 开放平台
_OPEN_API = "https://developer.zhihu.com/api/v1"

_HTTP_TIMEOUT = 15.0
_CACHE_TTL = 24 * 3600  # 24 小时
_DEFAULT_CACHE_DIR = GAME_ROOT / "data" / "zhihu_cache"

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


# ---------------------------------------------------------------- HTTP 出口

def _request_json(url: str, headers: dict | None = None) -> Any:
    """唯一出网点：GET 并解析 JSON。失败抛异常，由调用方兜底。
    trust_env=False 为仓库铁律（见 tests/test_no_proxy_egress.py）：出网
    必须直连，不得继承 Windows 系统代理。"""
    with httpx.Client(trust_env=False, timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(url, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


def _get_json_safe(url: str) -> Any | None:
    """Z1 出口：任何网络/解析异常 → None（上层降级），绝不抛出。"""
    try:
        return _request_json(url)
    except Exception:
        return None


# ---------------------------------------------------------------- 磁盘缓存

def _cache_path(cache_dir: Path | None, name: str) -> Path:
    return (Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR) / name


def _cache_read(cache_dir: Path | None, name: str) -> Any | None:
    """命中且未过 TTL 才返回数据，否则 None。缓存文件内嵌 fetched_at。"""
    path = _cache_path(cache_dir, name)
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = wrapper.get("fetched_at", 0)
        if time.time() - fetched_at > _CACHE_TTL:
            return None
        return wrapper.get("data")
    except Exception:
        return None


def _cache_write(cache_dir: Path | None, name: str, data: Any) -> None:
    path = _cache_path(cache_dir, name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"fetched_at": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        pass  # 缓存写失败不阻塞主流程


def _unwrap_list(payload: Any) -> list | None:
    """容错解包：端点返回裸数组或 {items|data|list|stories: [...]}。"""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "list", "stories"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
    return None


# ---------------------------------------------------------------- 署名台账

def _record_credits(entries: list[dict], cache_dir: Path | None) -> None:
    """向 credits_ledger.json 追加署名记录（读改写，按 work_id 去重）。
    用途：剧本包署名合规。任何失败静默吞掉，不阻塞主流程。"""
    if not entries:
        return
    path = _cache_path(cache_dir, "credits_ledger.json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            ledger = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(ledger, list):
                ledger = []
        except Exception:
            ledger = []
        seen = {item.get("work_id") for item in ledger if isinstance(item, dict)}
        for entry in entries:
            wid = entry.get("work_id")
            if wid is None or wid in seen:
                continue
            seen.add(wid)
            ledger.append(entry)
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except Exception:
        pass


def _credit_entry(item: dict, source_url: str) -> dict | None:
    wid = item.get("work_id")
    if wid is None:
        return None
    return {
        "work_id": wid,
        "title": item.get("title", ""),
        "author_name": item.get("author_name", ""),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_url": source_url,
    }


# ---------------------------------------------------------------- Z1 黑客松内容 API

def fetch_story_list(cache_dir: Path | None = None) -> list | None:
    """黑客松故事列表。每项含 work_id/title/artwork/description/labels。
    缓存命中不发网络请求。失败返回 None。"""
    cached = _cache_read(cache_dir, "story_list.json")
    if cached is not None:
        return cached
    url = f"{_HACKATHON_API}/story/list"
    items = _unwrap_list(_get_json_safe(url))
    if items is None:
        return None
    _cache_write(cache_dir, "story_list.json", items)
    credits = [e for e in (_credit_entry(it, url) for it in items
                           if isinstance(it, dict)) if e]
    _record_credits(credits, cache_dir)
    return items


def fetch_story(work_id: str, cache_dir: Path | None = None) -> dict | None:
    """故事详情：chapter_name/author_name/labels/introduction/content。
    缓存命中不发网络请求。失败返回 None。"""
    wid = str(work_id)
    cached = _cache_read(cache_dir, f"story_{wid}.json")
    if cached is not None:
        return cached
    url = f"{_HACKATHON_API}/story/{wid}"
    payload = _get_json_safe(url)
    if not isinstance(payload, dict):
        return None
    _cache_write(cache_dir, f"story_{wid}.json", payload)
    entry = _credit_entry(payload, url)
    if entry:
        _record_credits([entry], cache_dir)
    return payload


def fetch_knowledge_list(cache_dir: Path | None = None) -> list | None:
    """黑客松知识列表。详情与故事详情共用 story/{work_id} 路径。"""
    cached = _cache_read(cache_dir, "knowledge_list.json")
    if cached is not None:
        return cached
    url = f"{_HACKATHON_API}/knowledge/list"
    items = _unwrap_list(_get_json_safe(url))
    if items is None:
        return None
    _cache_write(cache_dir, "knowledge_list.json", items)
    credits = [e for e in (_credit_entry(it, url) for it in items
                           if isinstance(it, dict)) if e]
    _record_credits(credits, cache_dir)
    return items


def fetch_work(work_id: str, kind: str = "story",
               cache_dir: Path | None = None) -> dict | None:
    """按 work_id 取详情。knowledge 与 story 共用 story/{work_id} 详情路径，
    故 kind 仅作语义标记，实际走同一路径。"""
    if kind not in ("story", "knowledge"):
        return None
    return fetch_story(work_id, cache_dir=cache_dir)


# ---------------------------------------------------------------- Z2 开放平台（可选）

def _open_get(path: str, params: dict | None = None) -> dict | None:
    """开放平台统一出口：Bearer 鉴权 + 秒级时间戳。未配置凭证或任何
    失败返回 None。Access Secret 只进请求头，绝不落日志。"""
    secret = os.environ.get("ZHIHU_ACCESS_SECRET", "").strip()
    if not secret:
        return None
    headers = {
        "Authorization": f"Bearer {secret}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
    }
    query = ""
    if params:
        from urllib.parse import urlencode
        query = "?" + urlencode(params)
    try:
        payload = _request_json(f"{_OPEN_API}{path}{query}", headers=headers)
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("Code") != 0:
        return None
    data = payload.get("Data")
    return data if isinstance(data, dict) else None


def fetch_hot(limit: int = 20) -> list | None:
    """知乎热榜（开放平台，需 ZHIHU_ACCESS_SECRET）。未配置或失败 → None。
    返回 Items：Title/Url/ThumbnailUrl/Summary。"""
    data = _open_get("/content/hot_list", {"Limit": limit})
    if data is None:
        return None
    items = data.get("Items")
    return items if isinstance(items, list) else None


def search_zhihu(query: str, count: int = 10) -> list | None:
    """知乎站内搜索（开放平台，需 ZHIHU_ACCESS_SECRET）。未配置或失败 → None。
    返回 Items：Title/ContentText/Url/AuthorName 等。"""
    if not query or not query.strip():
        return None
    data = _open_get("/content/zhihu_search",
                     {"Query": query, "Count": max(1, min(count, 10))})
    if data is None:
        return None
    items = data.get("Items")
    return items if isinstance(items, list) else None


# ---------------------------------------------------------------- 安全工具

def sanitize_excerpt(text: Any, max_len: int = 1200) -> str:
    """从不可信外部文本提取安全摘要：剥离控制字符（保留换行/制表），
    截断到 max_len。调用方应使用本函数输出，而非直接拼接原文。"""
    if not isinstance(text, str):
        return ""
    cleaned = _CTRL_RE.sub("", text)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "…"
    return cleaned


# ---------------------------------------------------------------- 异步包装器

async def fetch_story_list_async(cache_dir: Path | None = None) -> list | None:
    return await asyncio.to_thread(fetch_story_list, cache_dir)


async def fetch_story_async(work_id: str,
                            cache_dir: Path | None = None) -> dict | None:
    return await asyncio.to_thread(fetch_story, work_id, cache_dir)


async def fetch_knowledge_list_async(cache_dir: Path | None = None) -> list | None:
    return await asyncio.to_thread(fetch_knowledge_list, cache_dir)


async def fetch_work_async(work_id: str, kind: str = "story",
                           cache_dir: Path | None = None) -> dict | None:
    return await asyncio.to_thread(fetch_work, work_id, kind, cache_dir)


async def fetch_hot_async(limit: int = 20) -> list | None:
    return await asyncio.to_thread(fetch_hot, limit)


async def search_zhihu_async(query: str, count: int = 10) -> list | None:
    return await asyncio.to_thread(search_zhihu, query, count)
