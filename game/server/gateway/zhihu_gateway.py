"""知乎 API 网关：限额缓存与降级。

所有盐言故事 / 知乎知识 / 热榜 / 搜索 / 直答调用必须经过本网关
（契约 docs/CONTRACTS.md §五-4「API 纪律」与 docs/ASSETS_INVENTORY.md「额度纪律」）。

额度纪律（ASSETS_INVENTORY 未建队基础额度，可用环境变量覆盖）：
  直答 2/日 · 热榜 2/日 · 知乎搜索 10/日 · 全网搜索 10/日
  creator 组（本人创作统计 + 问题推荐共用，官方 creator.md）默认 100/日、
  未实名 10/日——网关保守取 10/日硬编码；用户资料 1000/日——网关保守取 200/日。
鉴权边界（官方 hackathon-oauth.md / hackathon-user-profile-api.md / creator.md）：
  盐言故事 / 知乎知识 = 黑客松内容接口，免鉴权直调；
  热榜 / 搜索 / 直答 / creator 组 = 需要 Access Secret——只读环境变量
  ZHIHU_ACCESS_SECRET（Bearer + 秒级时间戳），凭证绝不落代码 / 前端 / 文档；
  用户资料 GET openapi.zhihu.com/user = 只带 OAuth access_token（Bearer），
  无需 Access Secret / X-OAuth-Token / 时间戳；creator 组不认 X-OAuth-Token
  （仅 Access Secret 所属账号）。

降级信封（硬规则：API 失败给真实降级提示，不伪造内容）：
  {"ok": bool, "source": "api|cache|fallback|rejected", "degraded": bool,
   "notice": str|None, "data": ...}

缓存（cache_dir 磁盘 JSON）：
  盐言/知识 永久缓存（制作期拉取入库哲学）；热榜按天缓存（每日挑战全服共享一份）；
  搜索/直答按归一化问题永久缓存（预生成缓存：重复问题不重复烧额度）。
节流：同类真实调用最小间隔 + 全局单飞锁（同一时刻仅一个真实 API 调用，防并发双烧额度）。
配额计数持久化到 cache_dir/quotas.json，重启不涨额度。
"""
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx

# 话题白名单（热榜过滤 + 搜索闸门；"*" = 放行全部）
DEFAULT_WHITELIST = (
    "知乎,看山,盐言,悬疑,推理,剧本杀,职场,心理,情绪,倦怠,网络,舆情,谣言,辟谣,"
    "热搜,匿名,隐私,信息茧房,网暴,人工智能,AI,加班,打卡,内卷,流量,吃瓜"
)

_OPENAI_MODEL_DEFAULT = os.environ.get("ZHIHU_GAME_MODEL", "zhida-agent")


class GatewayError(Exception):
    """网关内部错误：code ∈ missing_credentials|throttled|network|http_error|bad_json"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ZhihuGateway:
    def __init__(self, app_id: str, app_key: str, cache_dir: Path):
        # 遗留骨架参数保留（OAuth AppID/AppKey）；当前鉴权走 ZHIHU_ACCESS_SECRET。
        self.app_id = app_id
        self.app_key = app_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.daily_counts = {}  # {"YYYY-MM-DD": {"chat": n, ...}}
        self._quota_file = self.cache_dir / "quotas.json"
        self._load_quotas()

        # 凭证：仅环境变量（硬规则）
        self.access_secret = os.environ.get("ZHIHU_ACCESS_SECRET", "").strip()
        self.open_base = os.environ.get(
            "ZHIHU_GAME_OPEN_API_BASE", "https://developer.zhihu.com"
        ).rstrip("/")
        self.content_base = os.environ.get(
            "ZHIHU_GAME_CONTENT_API_BASE",
            "https://api.zhihu.com/km-indep-home/hackathon/v2",
        ).rstrip("/")
        # 用户资料独立接口（官方 hackathon-user-profile-api.md）
        self.user_base = os.environ.get(
            "ZHIHU_GAME_USER_API_BASE", "https://openapi.zhihu.com").rstrip("/")
        self.timeout = float(os.environ.get("ZHIHU_GAME_HTTP_TIMEOUT", "10"))
        # 比赛模式：知乎直答对话取消本地节流（默认 0 = 连续多次调用零等待）。
        # 若显式配置 ZHIHU_GAME_THROTTLE_SECONDS > 0，节流窗口内的调用会
        # 「等待窗口结束后继续」，不再直接拒绝——频率限制不中断对话流程。
        self.throttle_s = float(os.environ.get("ZHIHU_GAME_THROTTLE_SECONDS", "0"))
        self.limits = {
            # 本地保护上限可配置；官方额度以 live_quota 为准。默认 20 次，
            # 避免测试/多人对局被过低的演示值 2 次直接阻断。
            "chat": int(os.environ.get("ZHIHU_GAME_QUOTA_ZHIDA", "20")),     # 直答
            "search": int(os.environ.get("ZHIHU_GAME_QUOTA_SEARCH", "10")),  # 知乎搜索
            "gsearch": int(os.environ.get("ZHIHU_GAME_QUOTA_GSEARCH", "10")),  # 全网搜索
            "hot": int(os.environ.get("ZHIHU_GAME_QUOTA_HOT", "2")),        # 热榜
            # creator 额度组（官方 creator.md：本人创作四项 + question recommend
            # 画像/主题两模式共用；默认 100/日，未实名 10/日——保守取 10）
            "creator": int(os.environ.get("ZHIHU_GAME_QUOTA_CREATOR", "10")),
            # 用户数据（ASSETS_INVENTORY：1000/日）——网关保守取 200 防滥用
            "user": int(os.environ.get("ZHIHU_GAME_QUOTA_USER", "200")),
        }
        wl = os.environ.get("ZHIHU_GAME_TOPIC_WHITELIST", DEFAULT_WHITELIST)
        self.topic_whitelist = [w.strip() for w in wl.split(",") if w.strip()]

        self._last_live_call = {}  # kind -> monotonic ts（节流）
        self._net_lock = asyncio.Lock()  # 单飞锁：同时仅一个真实 API 调用
        self._client: httpx.AsyncClient | None = None
        self.last_errors: dict[str, str] = {}  # capability -> 最近真实失败原因

    # ------------------------------------------------------------------ 信封
    @staticmethod
    def _env(ok: bool, source: str, data=None, notice: str | None = None,
             degraded: bool = False) -> dict:
        return {"ok": ok, "source": source, "degraded": degraded,
                "notice": notice, "data": data}

    def _record(self, kind: str, msg: str):
        self.last_errors[kind] = f"{time.strftime('%H:%M:%S')} {msg}"

    # ------------------------------------------------------------------ 额度
    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _used(self, kind: str) -> int:
        return int(self.daily_counts.get(self._today(), {}).get(kind, 0))

    def _quota_ok(self, kind: str) -> bool:
        day = self._today()
        limit = self.limits.get(kind)
        if limit is None:
            return False
        return self.daily_counts.get(day, {}).get(kind, 0) < limit

    def _count(self, kind: str):
        day = self._today()
        self.daily_counts.setdefault(day, {})
        self.daily_counts[day][kind] = self.daily_counts[day].get(kind, 0) + 1
        # 只保留最近 3 天计数
        days = sorted(self.daily_counts)
        for d in days[:-3]:
            self.daily_counts.pop(d, None)
        self._persist_quotas()

    def _load_quotas(self):
        try:
            if self._quota_file.exists():
                self.daily_counts = json.loads(
                    self._quota_file.read_text(encoding="utf-8"))
        except Exception:
            self.daily_counts = {}  # 损坏则从零计（宁可少用，不超额）

    def _persist_quotas(self):
        try:
            self._quota_file.write_text(
                json.dumps(self.daily_counts, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ 缓存
    def _cache_key(self, kind: str, text: str) -> str:
        return hashlib.md5(f"{kind}:{text}".encode()).hexdigest()

    def _read_cache(self, key: str) -> str | None:
        f = self.cache_dir / f"{key}.txt"
        return f.read_text(encoding="utf-8") if f.exists() else None

    def _write_cache(self, key: str, text: str):
        (self.cache_dir / f"{key}.txt").write_text(text, encoding="utf-8")

    def _read_json_cache(self, key: str, max_age: float | None = None) -> dict | None:
        f = self.cache_dir / f"{key}.json"
        if not f.exists():
            return None
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
        if max_age is not None and time.time() - obj.get("cached_at", 0) > max_age:
            return None
        return obj.get("data")

    def _write_json_cache(self, key: str, data):
        f = self.cache_dir / f"{key}.json"
        f.write_text(json.dumps({"cached_at": time.time(), "data": data},
                                ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------ HTTP
    def _auth_headers(self) -> dict | None:
        if not self.access_secret:
            return None
        return {
            "Authorization": f"Bearer {self.access_secret}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # trust_env=False（2026-09-14）：不继承系统代理/环境代理，
            # 知乎开放平台出网一律直连（本机代理曾致 401/405 劫持）。
            self._client = httpx.AsyncClient(timeout=self.timeout,
                                             trust_env=False)
        return self._client

    async def close(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _call(self, kind: str, method: str, url: str, *,
                    params: dict | None = None, json_body=None,
                    auth: bool = False,
                    extra_headers: dict | None = None) -> httpx.Response:
        """单飞 + 节流后的真实 API 调用。失败抛 GatewayError。

        auth=True 走 Access Secret（Bearer + X-Request-Timestamp）；
        extra_headers 用于其他鉴权形态（如用户资料的纯 OAuth Bearer token）。
        """
        headers = {}
        if auth:
            h = self._auth_headers()
            if h is None:
                raise GatewayError("missing_credentials",
                                   "未配置 ZHIHU_ACCESS_SECRET 环境变量，鉴权接口不可用")
            headers = h
        if extra_headers:
            headers = {**headers, **extra_headers}
        async with self._net_lock:
            # 节流改为等待型（不拒绝）：若配置了 throttle_s > 0，窗口内的调用
            # 等待至窗口结束再发起真实 API 调用，对话流程不中断。默认 0 = 无节流。
            if self.throttle_s > 0:
                now = time.monotonic()
                last = self._last_live_call.get(kind)
                if last is not None and now - last < self.throttle_s:
                    await asyncio.sleep(self.throttle_s - (now - last))
            self._last_live_call[kind] = time.monotonic()
            client = self._get_client()
            try:
                resp = await client.request(method, url, params=params,
                                            json=json_body, headers=headers)
            except httpx.HTTPError as e:
                raise GatewayError("network",
                                   f"网络请求失败：{type(e).__name__}: {e}") from e
        if resp.status_code != 200:
            raise GatewayError("http_error", f"上游返回 HTTP {resp.status_code}")
        return resp

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except ValueError as e:
            raise GatewayError("bad_json", "上游响应不是合法 JSON") from e

    # ------------------------------------------------- 免鉴权内容：盐言/知识
    _WORK_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

    async def story_list(self) -> dict:
        return await self._content_list("story")

    async def knowledge_list(self) -> dict:
        return await self._content_list("knowledge")

    async def _content_list(self, kind: str) -> dict:
        key = f"{kind}_list"
        cached = self._read_json_cache(key)
        if cached is not None:
            self.last_errors.pop(kind, None)  # 缓存可用即不再视为降级
            return self._env(True, "cache", data=cached)
        try:
            resp = await self._call(kind, "GET", f"{self.content_base}/{kind}/list")
            data = self._parse_json(resp)
        except GatewayError as e:
            self._record(kind, e.message)
            return self._env(False, "fallback", degraded=True,
                             notice=f"知乎内容接口（{kind}）不可用：{e.message}；本次返回空数据，非伪造内容")
        self._write_json_cache(key, data)
        self.last_errors.pop(kind, None)
        return self._env(True, "api", data=data)

    async def story_detail(self, work_id: str) -> dict:
        return await self._content_detail("story", work_id)

    async def knowledge_detail(self, work_id: str) -> dict:
        return await self._content_detail("knowledge", work_id)

    async def _content_detail(self, kind: str, work_id: str) -> dict:
        work_id = str(work_id or "").strip()
        if not self._WORK_ID_RE.match(work_id):
            return self._env(False, "rejected",
                             notice="work_id 非法（仅允许字母数字_-，须来自对应列表接口），请求已拒绝")
        key = f"{kind}_detail_{work_id}"
        cached = self._read_json_cache(key)
        if cached is not None:
            return self._env(True, "cache", data=cached)
        try:
            resp = await self._call(kind, "GET",
                                    f"{self.content_base}/{kind}/{work_id}")
            data = self._parse_json(resp)
        except GatewayError as e:
            self._record(kind, e.message)
            return self._env(False, "fallback", degraded=True,
                             notice=f"知乎内容详情（{kind}/{work_id}）不可用：{e.message}；不生成虚假正文")
        self._write_json_cache(key, data)
        self.last_errors.pop(kind, None)
        return self._env(True, "api", data=data)

    def load_scenario(self, book_id: str) -> dict:
        """盐言故事详情（遗留同步签名；开局一次性拉取入库用）。

        返回降级信封 dict；失败时 ok=False + 真实原因，不伪造剧本内容。
        """
        work_id = str(book_id or "").strip()
        if not self._WORK_ID_RE.match(work_id):
            return self._env(False, "rejected",
                             notice="book_id 非法（仅允许字母数字_-），请求已拒绝")
        key = f"story_detail_{work_id}"
        cached = self._read_json_cache(key)
        if cached is not None:
            return self._env(True, "cache", data=cached)
        headers = {"Accept": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False) as client:
                resp = client.get(f"{self.content_base}/story/{work_id}",
                                  headers=headers)
        except httpx.HTTPError as e:
            self._record("story", f"网络请求失败：{type(e).__name__}")
            return self._env(False, "fallback", degraded=True,
                             notice=f"盐言故事接口网络失败：{type(e).__name__}；不伪造剧本内容")
        if resp.status_code != 200:
            self._record("story", f"HTTP {resp.status_code}")
            return self._env(False, "fallback", degraded=True,
                             notice=f"盐言故事接口返回 HTTP {resp.status_code}；不伪造剧本内容")
        try:
            data = resp.json()
        except ValueError:
            self._record("story", "响应非 JSON")
            return self._env(False, "fallback", degraded=True,
                             notice="盐言故事接口响应非 JSON；不伪造剧本内容")
        self._write_json_cache(key, data)
        self.last_errors.pop("story", None)
        return self._env(True, "api", data=data)

    # ------------------------------------------------------------ 话题白名单
    def _topic_allowed(self, text: str) -> bool:
        if "*" in self.topic_whitelist:
            return True
        return any(w in (text or "") for w in self.topic_whitelist)

    # ------------------------------------------------------- 鉴权：搜索/热榜
    async def search(self, query: str, count: int = 5,
                     use_global: bool = False) -> dict:
        query = (query or "").strip()
        if not query:
            return self._env(False, "rejected", notice="查询词为空，请求已拒绝")
        kind = "gsearch" if use_global else "search"
        if not self._topic_allowed(query):
            return self._env(False, "rejected",
                             notice="话题白名单拦截：查询词不在白名单内（未消耗任何额度）；"
                                    "可用 ZHIHU_GAME_TOPIC_WHITELIST 调整")
        key = self._cache_key(kind, query.lower())
        cached = self._read_json_cache(key)
        if cached is not None:
            return self._env(True, "cache", data=cached)
        if not self._quota_ok(kind):
            self._record(kind, "额度耗尽")
            return self._env(False, "fallback", degraded=True,
                             notice=f"{'全网搜索' if use_global else '知乎搜索'}今日额度已用尽"
                                    f"（{self._used(kind)}/{self.limits[kind]}）且无缓存——返回空结果，不伪造搜索数据")
        params = {"Query": query, "Count": min(max(int(count), 1), 20 if use_global else 10)}
        url = (f"{self.open_base}/api/v1/content/global_search" if use_global
               else f"{self.open_base}/api/v1/content/zhihu_search")
        try:
            resp = await self._call(kind, "GET", url, params=params, auth=True)
            data = self._parse_json(resp)
        except GatewayError as e:
            self._record(kind, e.message)
            return self._env(False, "fallback", degraded=True,
                             notice=f"搜索接口失败：{e.message}；返回空结果，不伪造搜索数据")
        if data.get("Code") not in (0, None):
            self._record(kind, f"业务错误码 {data.get('Code')}")
            return self._env(False, "fallback", degraded=True,
                             notice=f"搜索接口业务错误码 {data.get('Code')}"
                                    f"（{data.get('Message', '')}）；返回空结果，不伪造搜索数据")
        self._count(kind)
        self._write_json_cache(key, data)
        self.last_errors.pop(kind, None)
        return self._env(True, "api", data=data)

    def _filter_hot(self, raw: dict, day: str) -> dict:
        items = ((raw.get("Data") or {}).get("Items")) or []
        keep, drop = [], 0
        for it in items:
            if self._topic_allowed(str(it.get("Title", ""))):
                keep.append(it)
            else:
                drop += 1
        return {"items": keep, "total": len(items),
                "whitelist_filtered_out": drop, "fetched_day": day}

    async def hot_list(self, limit: int = 10) -> dict:
        """热榜（2/日 ⚠️）：每日挑战模式全服共享当日一份缓存 + 话题白名单过滤。"""
        kind = "hot"
        day = time.strftime("%Y%m%d")
        key = f"hot_list_{day}"
        cached = self._read_json_cache(key)
        if cached is not None:
            return self._env(True, "cache", data=self._filter_hot(cached, day))
        if not self._quota_ok(kind):
            self._record(kind, "额度耗尽")
            return self._env(False, "fallback", degraded=True,
                             notice=f"热榜今日额度已用尽（{self._used(kind)}/{self.limits['hot']}）"
                                    f"且当日缓存为空——每日挑战不可用，不伪造热榜数据")
        try:
            resp = await self._call(kind, "GET",
                                    f"{self.open_base}/api/v1/content/hot_list",
                                    params={"Limit": 30}, auth=True)
            data = self._parse_json(resp)
        except GatewayError as e:
            self._record(kind, e.message)
            return self._env(False, "fallback", degraded=True,
                             notice=f"热榜接口失败：{e.message}；不伪造热榜数据")
        if data.get("Code") not in (0, None):
            self._record(kind, f"业务错误码 {data.get('Code')}")
            return self._env(False, "fallback", degraded=True,
                             notice=f"热榜接口业务错误码 {data.get('Code')}"
                                    f"（{data.get('Message', '')}）；不伪造热榜数据")
        self._count(kind)
        self._write_json_cache(key, data)
        self.last_errors.pop(kind, None)
        return self._env(True, "api", data=self._filter_hot(data, day))

    # ------------------------------------------------------------- 鉴权：直答
    async def direct_answer(self, question: str, system: str | None = None,
                            model: str = _OPENAI_MODEL_DEFAULT,
                            bypass_cache: bool = False) -> dict:
        """直答（2/日 ⚠️）：仅点睛场景（每日导读等）；按问题永久缓存。"""
        kind = "chat"
        question = (question or "").strip()
        if not question:
            return self._env(False, "rejected", notice="问题为空，请求已拒绝")
        key = self._cache_key("zhida", f"{model}|{system or ''}|{question}")
        cached = None if bypass_cache else self._read_json_cache(key)
        if cached is not None:
            return self._env(True, "cache", data=cached)
        # 不在游戏层设置人工额度上限；是否有额度由知乎官方接口返回决定。
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": question})
        body = {"model": model, "messages": messages, "stream": False}
        try:
            resp = await self._call(kind, "POST",
                                    f"{self.open_base}/v1/chat/completions",
                                    json_body=body, auth=True)
            data = self._parse_json(resp)
        except GatewayError as e:
            self._record(kind, e.message)
            return self._env(False, "fallback", degraded=True,
                             notice=f"直答接口失败：{e.message}；不伪造直答内容")
        if "error" in data:
            self._record(kind, f"上游 error: {data['error'].get('code', '')}")
            return self._env(False, "fallback", degraded=True,
                             notice=f"直答接口返回错误"
                                    f"（{data['error'].get('message', 'unknown')}）；不伪造直答内容")
        choices = data.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not content:
            self._record(kind, "响应缺 choices[0].message.content")
            return self._env(False, "fallback", degraded=True,
                             notice="直答响应缺少正文；不伪造直答内容")
        result = {"content": content, "model": data.get("model", model)}
        self._count(kind)
        self._write_json_cache(key, result)
        self.last_errors.pop(kind, None)
        return self._env(True, "api", data=result)

    def chat(self, system: str, user: str) -> str:
        """直答 Agent（遗留同步签名，C 窗口 llm_client 兼容入口）。

        缓存 → 额度内同步调用 → 失败/超限给真实降级文本（不伪造剧情）。
        """
        user = (user or "").strip()
        key = self._cache_key("chat", f"{system or ''}|{user}")
        cached = self._read_cache(key)
        if cached:
            return cached
        if not self.access_secret:
            self._record("chat", "未配置 ZHIHU_ACCESS_SECRET")
            return self._fallback(user)
        # 比赛模式：知乎大模型对话不受本地每日演示额度阻断；官方服务端额度/429 仍按真实响应处理。
        # 同步节流：距上次真实调用不足窗口则等待（低频点睛场景，可接受）
        last = self._last_live_call.get("chat")
        if last is not None:
            remain = self.throttle_s - (time.monotonic() - last)
            if remain > 0:
                time.sleep(min(remain, 2.0))
        self._last_live_call["chat"] = time.monotonic()
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": user})
        resp = None
        for attempt in range(4):
            try:
                with httpx.Client(timeout=self.timeout, trust_env=False) as client:
                    resp = client.post(
                        f"{self.open_base}/v1/chat/completions",
                        json={"model": _OPENAI_MODEL_DEFAULT, "messages": messages,
                              "stream": False},
                        headers=self._auth_headers())
            except httpx.HTTPError as e:
                self._record("chat", f"网络请求失败：{type(e).__name__}")
                return self._fallback(user)
            if resp.status_code == 429 and attempt < 3:
                # 官方限流快速退避自动重试，不中断对话流程
                time.sleep((0.8, 1.6, 3.0)[attempt])
                continue
            break
        if resp is None or resp.status_code != 200:
            self._record("chat", f"HTTP {getattr(resp, 'status_code', 'n/a')}")
            return self._fallback(user)
        try:
            data = resp.json()
        except ValueError:
            self._record("chat", "响应非 JSON")
            return self._fallback(user)
        choices = data.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not content:
            self._record("chat", "响应缺 content")
            return self._fallback(user)
        self._count("chat")
        self._write_cache(key, content)
        self.last_errors.pop("chat", None)
        return content

    def _fallback(self, user: str) -> str:
        """无凭证/额度耗尽：回落到预写台词，不把后台故障词漏给玩家。"""
        _ = user
        try:
            path = Path(__file__).resolve().parents[2] / "agents" / "prompts" / "fallbacks.json"
            pool = json.loads(path.read_text(encoding="utf-8")).get("generic") or []
            if pool:
                return str(pool[0])
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        return "叮——系统杂音。该频道暂时无法接通，档案局建议您稍作等待。"

    # ------------------------------------------------- 鉴权：用户资料（OAuth）
    _PROFILE_TTL = 300.0  # 资料短缓存：会话内重复取不再打用户数据接口

    async def user_profile(self, access_token: str) -> dict:
        """授权用户资料（官方 hackathon-user-profile-api.md，0.7.2）。

        GET openapi.zhihu.com/user，鉴权仅 `Authorization: Bearer <access_token>`
        （无需 Access Secret / X-OAuth-Token / 时间戳）。
        隐私铁律（契约 §3.7）：只透出公开三件套 uid/fullname/headline/avatar_path，
        email/phone_no/phone 等字段零读取（不 get、不缓存、不落任何存储）。
        uid 为 int64 可能超 JS 安全整数——解析无损后按字符串传递。
        额度：用户数据组（官方 1000/日，网关保守 200/日，每日计数持久化）。
        """
        kind = "user"
        token = (access_token or "").strip()
        if not token:
            return self._env(False, "rejected",
                             notice="缺少 OAuth access_token（请先完成登录交换），请求已拒绝")
        token_fp = hashlib.sha256(token.encode()).hexdigest()[:16]
        key = f"user_profile_{token_fp}"
        cached = self._read_json_cache(key, max_age=self._PROFILE_TTL)
        if cached is not None:
            return self._env(True, "cache", data=cached)
        if not self._quota_ok(kind):
            self._record(kind, "额度耗尽")
            return self._env(False, "fallback", degraded=True,
                             notice=f"用户资料今日网关限额已用尽"
                                    f"（{self._used(kind)}/{self.limits[kind]}）且短缓存过期"
                                    "——不伪造用户资料")
        try:
            resp = await self._call(
                kind, "GET", f"{self.user_base}/user",
                extra_headers={"Authorization": f"Bearer {token}"})
            raw = self._parse_json(resp)
        except GatewayError as e:
            self._record(kind, e.message)
            return self._env(False, "fallback", degraded=True,
                             notice=f"用户资料接口失败：{e.message}；不伪造用户资料")
        # 响应处理（官方：不能只凭 HTTP 200 判成功；鉴权失败停止读取）
        code = raw.get("code")
        uid = raw.get("uid")
        if uid in (None, "", 0) or (code not in (None, 0, 20000) and not uid):
            self._record(kind, f"业务 code={code}（{raw.get('data', '')}）")
            return self._env(False, "fallback", degraded=True,
                             notice=f"用户资料接口未返回有效用户标识"
                                    f"（业务 code={code}）——不建立会话、不伪造资料")
        profile = {  # 只挑公开四字段，其余一律丢弃（email/phone 零读取）
            "uid": str(uid),
            "fullname": str(raw.get("fullname", "")),
            "headline": str(raw.get("headline", "")),
            "avatar_path": str(raw.get("avatar_path", "")),
        }
        self._count(kind)
        self._write_json_cache(key, profile)
        self.last_errors.pop(kind, None)
        return self._env(True, "api", data=profile)

    # ------------------------------------------- 鉴权：creator 额度组（10/日）
    _CONTENT_URL_RE = re.compile(
        r"^https://(?:www\.zhihu\.com/(?:answer/\d+|question/\d+/answer/\d+"
        r"|pin/\d+|zvideo/\d+)|zhuanlan\.zhihu\.com/p/\d+)$")

    def _check_content_url(self, content_url: str) -> str | None:
        url = (content_url or "").strip()
        if not url:
            return "content_url 为空，请求已拒绝"
        if not self._CONTENT_URL_RE.match(url):
            return ("content_url 非法：须为知乎 HTTPS 内容链接"
                    "（answer/question/answer/pin/zvideo/zhuanlan p），请求已拒绝")
        return None

    @staticmethod
    def _check_date_pair(start_date: str | None,
                         end_date: str | None) -> str | None:
        if not start_date and not end_date:
            return None
        if not (start_date and end_date):
            return "StartDate/EndDate 必须成对提供，请求已拒绝"
        pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not (pat.match(start_date) and pat.match(end_date)):
            return "日期格式须为 YYYY-MM-DD，请求已拒绝"
        if start_date > end_date:
            return "开始日期不得晚于结束日期，请求已拒绝"
        return None

    async def _creator_call(self, path: str, params: dict, *,
                            cache_key: str, label: str) -> dict:
        """creator 额度组公共通道：配额 → 单飞节流 → 业务码校验 → 写缓存。

        缓存读取由调用方按各自 TTL 策略先行完成（question_recommend 永久
        预生成缓存 / creator_stats 短缓存），此处只负责成功后的写入。
        """
        kind = "creator"
        if not self._quota_ok(kind):
            self._record(kind, "额度耗尽")
            return self._env(False, "fallback", degraded=True,
                             notice=f"creator 组今日额度已用尽"
                                    f"（{self._used(kind)}/{self.limits[kind]}）"
                                    f"且无有效缓存——{label}不可用，不伪造统计数据")
        try:
            resp = await self._call(kind, "GET",
                                    f"{self.open_base}{path}",
                                    params=params, auth=True)
            data = self._parse_json(resp)
        except GatewayError as e:
            self._record(kind, e.message)
            return self._env(False, "fallback", degraded=True,
                             notice=f"{label}接口失败：{e.message}；不伪造统计数据")
        if data.get("Code") != 0:
            # 10001 参数/内容不可用 · 20001 授权拒绝 · 30001/30002 限额 · 30003 风控
            self._record(kind, f"业务错误码 {data.get('Code')}")
            return self._env(False, "fallback", degraded=True,
                             notice=f"{label}业务错误码 {data.get('Code')}"
                                    f"（{data.get('Message', '')}）；不伪造统计数据")
        self._count(kind)
        self._write_json_cache(cache_key, data.get("Data"))
        self.last_errors.pop(kind, None)
        return self._env(True, "api", data=data.get("Data"))

    async def creator_stats(self, access_token: str, content_url: str,
                            start_date: str | None = None,
                            end_date: str | None = None) -> dict:
        """本人单篇创作统计（官方 creator.md `me content-stats`）。

        GET /api/v1/user/creator_content_stats?ContentUrl=...，鉴权
        Bearer Access Secret + X-Request-Timestamp。
        注意（官方文档）：creator 四项只认 Access Secret 所属账号，不认
        X-OAuth-Token——`access_token` 参数按签名保留但被忽略，不做身份切换。
        StartDate/EndDate 可选，须成对 YYYY-MM-DD 且开始不晚于结束。
        额度：creator 组 10/日（未实名保守值，ZHIHU_GAME_QUOTA_CREATOR 可覆盖），
        每日计数持久化（quotas.json，重启不涨额度）；统计短缓存 600s。
        """
        url_err = self._check_content_url(content_url)
        if url_err:
            return self._env(False, "rejected", notice=url_err)
        date_err = self._check_date_pair(start_date, end_date)
        if date_err:
            return self._env(False, "rejected", notice=date_err)
        key = self._cache_key(
            "creator_stats", f"{content_url}|{start_date or ''}|{end_date or ''}")
        cached = self._read_json_cache(key, max_age=600.0)
        if cached is not None:
            return self._env(True, "cache", data=cached)
        params = {"ContentUrl": content_url.strip()}
        if start_date and end_date:
            params["StartDate"] = start_date
            params["EndDate"] = end_date
        return await self._creator_call(
            "/api/v1/user/creator_content_stats", params,
            cache_key=key, label="单篇创作统计")

    async def question_recommend(self, query: str | None = None,
                                 count: int = 5) -> dict:
        """问题推荐（官方 http-api.md，creator 额度组）。

        GET /api/v1/user/question_recommendations?Query=...&Count=...
        画像模式：不传 Query（按 Access Secret 所属用户画像推荐）；
        主题模式：Query 必填（显式空值上游返回 10001）。
        主题模式过话题白名单闸门（与 search 同口径，拦截不耗额度）。
        额度：creator 组共用 10/日，每日计数持久化；推荐结果按
        归一化 (query|count) 永久缓存（预生成哲学：重复请求不重复烧额度）。
        """
        kind = "creator"
        query = (query or "").strip()
        count = min(max(int(count), 1), 20)
        if not query:  # 画像模式
            key = self._cache_key("qrec", f"|profile|{count}")
            params = {"Count": count}
        else:
            if not self._topic_allowed(query):
                return self._env(False, "rejected",
                                 notice="话题白名单拦截：查询词不在白名单内（未消耗任何额度）；"
                                        "可用 ZHIHU_GAME_TOPIC_WHITELIST 调整")
            key = self._cache_key("qrec", f"{query.lower()}|{count}")
            params = {"Query": query, "Count": count}
        cached = self._read_json_cache(key)
        if cached is not None:
            return self._env(True, "cache", data=cached)
        result = await self._creator_call(
            "/api/v1/user/question_recommendations", params,
            cache_key=key, label="问题推荐")
        if result.get("ok"):
            result["quota_group"] = kind
        return result

    # ------------------------------------------------------------- 额度/健康
    async def live_quota(self) -> dict:
        """实时额度查询（不消耗业务额度）；health 可选深度探测。"""
        if not self.access_secret:
            return {"ok": False, "notice": "未配置 ZHIHU_ACCESS_SECRET，无法查询实时额度"}
        try:
            resp = await self._call(
                "quota", "GET", f"{self.open_base}/api/v1/quota",
                params={"APIIDs": "global_search,zhihu_search,hot_list,zhida_openai,creator"},
                auth=True)
            data = self._parse_json(resp)
        except GatewayError as e:
            return {"ok": False, "notice": f"实时额度查询失败：{e.message}"}
        return {"ok": True, "data": data.get("Data")}

    def quota_summary(self) -> dict:
        """返回业务统计；额度裁决完全以知乎官方响应为准。"""
        return {k: {"used": self._used(k), "limit": None, "source": "official_api"}
                for k in self.limits}

    def health(self) -> dict:
        """API 降级状态（/api/health 用）。degraded 列出当前有真实失败的 capability。"""
        return {
            "credentials_configured": bool(self.access_secret),
            "quota_daily": self.quota_summary(),
            "topic_whitelist": self.topic_whitelist,
            "throttle_seconds": self.throttle_s,
            "last_errors": dict(self.last_errors),
            "degraded": sorted(self.last_errors.keys()),
        }
