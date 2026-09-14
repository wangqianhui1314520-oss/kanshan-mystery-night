"""llm_client — LLM Provider 抽象（AI 层统一入口）

契约：docs/CONTRACTS.md §二 C；设计：docs/GAME_DESIGN_V3.md §四、API_INTEGRATION.md、KNOWLEDGE_SYSTEM.md。
Provider 策略：
- main（自建 LLM，OpenAI 兼容协议）：环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL——NPC 对话、
  DM 叙事、开导演出的主力通道；
- zhida（知乎直答 Agent）：全量 AI 对话与决策的统一通道；不设置每日调用次数限制，
  环境变量 ZHIHU_APP_KEY（可选 ZHIHU_ZHIDA_URL 覆盖端点）；
- mock：无任何真实 key 时的离线人设回放（腔调表来自 V3 §二 角色表），保证全链路可跑通；
- 全量预生成缓存：开场白/固定证词/金句演出开局批量生成入库（pregenerate），运行时优先命中缓存；
- 降级链：zhida 不可用 → main → mock；任何 Provider 异常 → fallback(scene) 预写兜底文本，对局不断流；
- 安全：API Key 仅从环境变量读取，严禁硬编码/入库/入前端；缓存目录默认 agents/cache/（LLM_CACHE_DIR 可覆盖）。

实现归 C 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

AGENTS_DIR = Path(__file__).resolve().parent
PROMPT_DIR = AGENTS_DIR / "prompts"
CACHE_DIR = Path(os.environ.get("LLM_CACHE_DIR") or (AGENTS_DIR / "cache"))

_ZHIDA_DEFAULT_URL = "https://developer.zhihu.com/v1/chat/completions"

# 比赛模式（2026-09-14）：知乎直答官方无硬性 QPS 限制——取消本地强制最小
# 调用间隔（默认 0 = 连续多次调用零等待，支持一席一句的串联调用流）；
# 官方偶发 429 仍保留短退避自动重试，保证频率限制不中断对话流程。
# 如需恢复本地节流，可设环境变量 LLM_MIN_INTERVAL（秒）。
_LAST_CALL = {"ts": 0.0}
_MIN_CALL_INTERVAL = float(os.environ.get("LLM_MIN_INTERVAL", "0"))
_RETRY_DELAYS = (0.8, 1.6, 3.0, 5.0)

# 出网强制直连（2026-09-14 压测取证）：Windows 注册表系统代理
# （ProxyEnable=1）会被 urllib 默认继承（getproxies → 注册表），本机代理
# 对 developer.zhihu.com 的 POST 会返回 401/405/异常秒回，直接导致
# NPC 聊天全军覆没。LLM 出网一律绕过任何代理直连上游。
_STRAIGHT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post_with_rate_limit(req, timeout: float) -> dict:
    """统一 POST+JSON：本地节流默认关闭；429 快速退避重试（main/zhida 共用）。"""
    for attempt in range(len(_RETRY_DELAYS) + 1):
        gap = time.time() - _LAST_CALL["ts"]
        if gap < _MIN_CALL_INTERVAL:
            time.sleep(_MIN_CALL_INTERVAL - gap)
        try:
            with _STRAIGHT_OPENER.open(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            _LAST_CALL["ts"] = time.time()
            return data
        except urllib.error.HTTPError as exc:
            _LAST_CALL["ts"] = time.time()
            if exc.code == 429 and attempt < len(_RETRY_DELAYS):
                # 官方限流退避：0.8s→1.6s→3s→5s 自动重试，对话流程不中断
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            raise


# ---------------------------------------------------------------- 模板与工具

def render_template(text: str, **fields) -> str:
    """prompts/*.md 统一用 {{token}} 占位，逐个替换（缺失 token 保留原样便于排查）。"""
    for key, value in fields.items():
        text = text.replace("{{" + key + "}}", "" if value is None else str(value))
    return text


def read_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _short(text: str, n: int = 8) -> str:
    text = re.sub(r"^\s*（心声）", "", str(text or "")).strip()
    return text[:n]


# ---------------------------------------------------------------- 缓存层

class LLMCache:
    """预生成缓存：内存 + JSON 落盘（agents/cache/llm_cache.json，运行时产物）。"""

    def __init__(self, cache_dir: Path | str | None = None):
        self.dir = Path(cache_dir) if cache_dir else CACHE_DIR
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._file = self.dir / "llm_cache.json"
        except OSError:                     # 只读环境：退化为纯内存缓存
            self._file = None
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self._file and self._file.exists():
            try:
                self._data = json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        if not self._file:
            return
        try:
            self._file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def auto_key(provider: str, system: str, user: str, temperature: float) -> str:
        raw = f"{provider}|{temperature:.2f}|{system}|{user}"
        return "auto_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self._save()


class DailyBudget:
    """调用统计。保留落盘统计字段以兼容旧数据，但不再阻断请求。"""

    def __init__(self, limit: int | None = None, cache_dir: Path | str | None = None):
        self.limit = limit if limit is not None else int(
            os.environ.get("ZHIDA_DAILY_LIMIT") or 2)
        self.dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self._file = self.dir / "zhida_budget.json"
        self._state = {"date": "", "used": 0}
        self._load()

    def _load(self) -> None:
        try:
            if self._file.exists():
                self._state = json.loads(self._file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._state = {"date": "", "used": 0}
        today = time.strftime("%Y-%m-%d")
        if self._state.get("date") != today:
            self._state = {"date": today, "used": 0}

    def _save(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(self._state, ensure_ascii=False),
                                  encoding="utf-8")
        except OSError:
            pass

    def allow(self) -> bool:
        self._load()
        return True

    def consume(self) -> None:
        self._load()
        self._state["used"] += 1
        self._save()

    def remaining(self) -> int:
        self._load()
        return max(0, self.limit - self._state["used"])


# ---------------------------------------------------------------- Provider 抽象

class Provider:
    """Provider 最小协议：available() + chat(system, user, temperature, stream)。"""
    name = "base"

    def available(self) -> bool:
        return True

    def chat(self, system: str, user: str, temperature: float = 0.8,
             stream: bool = False) -> str:
        raise NotImplementedError


class OpenAICompatProvider(Provider):
    """main：OpenAI 兼容 /chat/completions（Moonshot Kimi / DeepSeek 等自建 LLM）。
    凭证只来自环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。"""
    name = "main"

    def __init__(self):
        # 显式凭证锁：设置面板探针等场景直接注入 api_key/base_url/model 后，
        # 后续 chat() 的 _sync_env() 不得再用进程 env 覆盖（否则面板填的
        # DeepSeek 等自建端点会被 env 值静默顶替，探针假阳性/连接失败）。
        self._explicit_creds = False
        self._sync_env()

    def use_credentials(self, api_key: str, base_url: str, model: str) -> None:
        """注入显式凭证并锁定（此后 _sync_env 不再覆盖实例属性）。"""
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").rstrip("/")
        self.model = (model or "").strip()
        try:
            self.timeout = float(os.environ.get("LLM_TIMEOUT") or 60)
        except ValueError:
            self.timeout = 60.0
        self._explicit_creds = True

    def _sync_env(self) -> None:
        """会话级 header / 设置面板会晚于进程启动写入 env，每次调用重读。"""
        if self._explicit_creds:
            return
        self.api_key = os.environ.get("LLM_API_KEY") or ""
        self.base_url = (os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        self.model = os.environ.get("LLM_MODEL") or ""
        try:
            self.timeout = float(os.environ.get("LLM_TIMEOUT") or 30)
        except ValueError:
            self.timeout = 30.0

    def available(self) -> bool:
        self._sync_env()
        return bool(self.api_key and self.base_url and self.model)

    def chat(self, system: str, user: str, temperature: float = 0.8,
             stream: bool = False) -> str:
        self._sync_env()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "stream": False,
        }
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.api_key}"}
        if "zhihu" in self.base_url:
            # 知乎开放平台鉴权要求携带秒级时间戳，缺该头一律 401 invalid_api_key
            headers["X-Request-Timestamp"] = str(int(time.time()))
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST")
        data = _post_with_rate_limit(req, self.timeout)
        return data["choices"][0]["message"]["content"]


class ZhidaProvider(Provider):
    """zhida：知乎直答 Agent（全量 AI 通道）。凭证来自环境变量 ZHIHU_APP_KEY；
    不设置每日调用上限。"""
    name = "zhida"

    def __init__(self):
        self.app_key = (os.environ.get("ZHIHU_APP_KEY") or
                        os.environ.get("ZHIHU_ACCESS_SECRET") or "")
        self.url = os.environ.get("ZHIHU_ZHIDA_URL") or _ZHIDA_DEFAULT_URL
        self.budget = DailyBudget()
        try:
            self.timeout = float(os.environ.get("LLM_TIMEOUT") or 30)
        except ValueError:
            self.timeout = 30.0

    def available(self) -> bool:
        return bool(self.app_key) and self.budget.allow()

    def chat(self, system: str, user: str, temperature: float = 0.8,
             stream: bool = False) -> str:
        payload = {"model": os.environ.get("ZHIHU_LLM_MODEL", "zhida-agent"),
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}],
                   "stream": False}
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.app_key}",
                     "X-Request-Timestamp": str(int(time.time()))},
            method="POST")
        data = _post_with_rate_limit(req, self.timeout)
        self.budget.consume()
        for path in (("data", "answer"), ("answer",),
                     ("choices", 0, "message", "content"), ("content",)):
            node = data
            try:
                for key in path:
                    node = node[key]
                if isinstance(node, str) and node.strip():
                    return node
            except (KeyError, IndexError, TypeError):
                continue
        raise RuntimeError("zhida 响应格式无法解析")


# ---------------------------------------------------------------- Mock Provider

class MockProvider(Provider):
    """mock：零 key 离线回放。识别提示词中的任务标记与角色腔调锚点，产出
    结构正确的占位演出（JSON 任务返回合法 JSON），保证 Agent 链路全流程可测。"""
    name = "mock"

    _QUIRKS = {  # V3 §二 角色腔调锚点
        "知之者": "先问是不是，再问为什么：",
        "笔上仙": "欲知后事如何——且听下回分解。",
        "流量酱": "家人们谁懂啊，#看山失踪# 还在热搜第一！",
        "路人甲": "我好像看到过……啊不对，我记不清了，反正就是那样。",
        "看山Bot": "检索中……答案置信度 37%，仅供参考。",
        "沉底君": "[该发言已被折叠]",
        "盐值君": "您好，关于您反馈的情况，小管家已记录并上报（鞠躬）。",
        "V587": "昨天刚注册不太懂规矩，但这题我会！……吧？",
    }

    _DANMAKU = [
        "前方高能", "这波在大气层", "建议查查，但不至于删号",
        "#谁动了我的鱼干# 热搜第一预定", "档案局空调为什么这么冷（战术后仰）",
        "谢邀，人在档案局，刚被锁门", "这瓜保熟吗？先蹲一个后续",
        "折叠区居民表示情绪稳定",
    ]

    _BOSS_REVEAL = (
        "【系统提示音】叮——检测到异常请求：请求对象……是本系统。\n"
        "（电流杂音。全息横幅的字符开始抖动、重组。）\n"
        "【系统提示音】这个请求超出权限范围……不，等等。它恰恰是唯一有权限的请求。\n"
        "（横幅熄灭三秒。重新亮起时，字变成了手写体：）\n"
        "【不出真相，不出此门——落款：刘看山，手书】\n"
        "【刘看山】（从档案柜的阴影里走出来，尾巴上还挂着监控室的静电）"
        "恭喜，也可能恭喜不了。你们破的局，正是我设的局。\n"
        "【刘看山】失踪？我只是出去买了袋鱼干。大门是我锁的，系统提示音是我配的，"
        "第一幕那条横幅是我亲手写的。\n"
        "【刘看山】污染源已经在你们中间现形了。剩下的，交给结局矩阵。"
        "（咬一口鱼干）复盘之前，先说好——谁也不许动我的鱼干。"
    )

    @staticmethod
    def _find_role(system: str, user: str) -> str:
        for hay in (system, user):
            m = re.search(r"角色[:：]\s*([^\n，。｜|]{1,12})", hay)
            if m:
                return m.group(1).strip()
        return ""

    def chat(self, system: str, user: str, temperature: float = 0.8,
             stream: bool = False) -> str:
        text = system + "\n" + user
        role = self._find_role(system, user)
        quirk = next((v for k, v in self._QUIRKS.items() if k in text), "")
        if role:
            quirk = next((v for k, v in self._QUIRKS.items() if k in role or k in text), quirk)

        if "终极层" in text or "现身演出" in text or "看山现身" in text:
            return self._BOSS_REVEAL
        m = re.search(r"演出位[:：]\s*([a-z_0-9]+)", text)  # Showtime 演出位 → 预写兜底
        if m:                                   # 仅识别 ASCII kind，避开模板中文小节名
            return fallback_text("show_" + m.group(1))
        if "导读" in text:
            return ("叮——今日导读：昨夜 #谁动了我的鱼干# 冲上榜首，"
                    "监控室多了一段没人承认的删除记录。今日份真相，限时供应。")
        if "吐槽" in text:
            return "（系统音）检索结果过于顺利，系统表示警惕。"
        if "弹幕" in text:
            return "\n".join(self._DANMAKU[:4])
        if "只输出 JSON" in text or '"logic_quality"' in text:
            depth = 1 + sum(1 for w in ("因为", "所以", "证据", "线索", "时间线") if w in user)
            return json.dumps({
                "logic_quality": min(5, depth),
                "misleading_points": [],
                "summary": f"（mock）依据证据覆盖度保守评分，引用证据词 {min(5, depth) - 1} 处。",
            }, ensure_ascii=False)
        if "心晴诊室" in text or "诊室结算" in text:
            if "污染胜利" in text:
                return ("诊室灯牌闪了两下，切成了红色：扎心大会开始。"
                        "本局心晴档案 0 人——但至少，大家学会了互相甩锅。")
            return ("诊室灯牌亮起：本局心晴档案已归档。"
                    "愿信息污染远离每一个人。（鱼干味彩蛋：看山在某处默默点了赞。）")
        if "counsel_success" in text or "counsel_fail" in text or "尬聊" in text:
            if "匹配失败" in text or "尬聊" in text:
                return (f"（{role or 'NPC'} 愣住了三秒）……你说的这个，跟监控片段有什么关系？"
                        "（弹幕：答非所问预警）")
            return ("（沉默两秒，情绪松动）……你这么一说，好像也不是我一个人的问题。"
                    "「先接纳，再改变」——行吧，这句我记下了。")
        if "系统提示音" in text or "播报" in text:
            flaw_hint = ""
            m = re.search(r"破绽计数[:：]\s*(\d)", text)
            if m and int(m.group(1)) >= 3:
                flaw_hint = "（本条播报由系统自动生成。大概。）"
            return ("叮——系统检索完成。档案局各区域运行正常，"
                    "温度略低属正常现象，鱼干库存……属正常范围。" + flaw_hint)
        head = f"（{role}）" if role else ""
        return f"{head}{quirk or '我？我当时在忙别的，没太看清。'} 至于细节……你得先拿出证据。"


# ---------------------------------------------------------------- 兜底文案

_FALLBACKS: dict | None = None


def _fallback_data() -> dict:
    global _FALLBACKS
    if _FALLBACKS is None:
        try:
            _FALLBACKS = json.loads(
                (PROMPT_DIR / "fallbacks.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _FALLBACKS = {"generic": ["（系统杂音）该频道暂时无法接通，请稍后再试。"]}
    return _FALLBACKS


_fb_counter = {"n": 0}


def fallback_text(scene: str) -> str:
    """按场景取预写兜底文本；未知场景落回 generic；轮转取样避免复读。"""
    data = _fallback_data()
    pool = data.get(scene) or data.get("generic") or ["……"]
    _fb_counter["n"] += 1
    return pool[_fb_counter["n"] % len(pool)]


# ---------------------------------------------------------------- 统一入口

def call_gateway(gateway, system: str, user: str, *, provider: str = "zhida",
                 temperature: float = 0.8, stream: bool = False):
    """Agent ↔ gateway 兼容层。支持三种形态：
    1) LLMClient 实例（走 Provider 抽象，provider 参数生效）；
    2) chat(system, user) 双参网关（F 窗口 zhihu_gateway 风格）；
    3) chat(messages=[...]) 消息数组网关。"""
    if isinstance(gateway, LLMClient):
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        return gateway.chat(messages, provider=provider,
                            temperature=temperature, stream=stream)
    try:
        return gateway.chat(system, user)
    except TypeError:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        return gateway.chat(messages)


class LLMClient:
    """Provider 抽象统一入口（缓存 + 故障降级）。"""

    def __init__(self, cache_dir: Path | str | None = None,
                 providers: dict[str, Provider] | None = None,
                 cache_enabled: bool | None = None):
        # 磁盘缓存默认关闭（避免命中历史旧文本导致回复与上下文无关）；
        # 仅当 LLM_CACHE=1（或显式传入 cache_enabled=True）时启用读+写。
        if cache_enabled is None:
            cache_enabled = os.environ.get("LLM_CACHE", "") == "1"
        self.cache_enabled = bool(cache_enabled)
        self.cache = LLMCache(cache_dir)
        self.providers: dict[str, Provider] = providers or {
            "main": OpenAICompatProvider(),
            "zhida": ZhidaProvider(),
            "mock": MockProvider(),
        }
        self.degrade_log: list[str] = []   # 诊断：降级路径记录
        self.last_provider: str = ""       # 诊断：最近一次实际使用的 provider
        self.last_error: str = ""

    # -- 内部 ------------------------------------------------------------
    @staticmethod
    def _split(messages: list[dict]) -> tuple[str, str]:
        system = next((m.get("content", "") for m in messages
                       if m.get("role") == "system"), "")
        user = next((m.get("content", "") for m in messages
                     if m.get("role") == "user"), "")
        return system, user

    def _pick(self, provider: str) -> Provider:
        """优先知乎直答；其次用户自建 LLM（main）；最后降级本地 mock。"""
        tried = []
        order = ("zhida", "main", "mock") if provider == "zhida" \
            else (provider, "zhida", "main", "mock")
        for name in order:
            p = self.providers.get(name)
            if p is None:
                continue
            if p.available():
                if name != provider:
                    self.degrade_log.append(f"{provider} → {name}")
                return p
            tried.append(name)
        # 测试/自定义注入的 Provider 可能没有显式注册 mock；不要因此把
        # 一次真实模型失败升级成 KeyError，返回一个可用的确定性兜底。
        return self.providers.get("mock") or next(iter(self.providers.values()), MockProvider())

    def _note(self, provider: str, reason: str) -> None:
        self.degrade_log.append(f"{provider}: {reason}")

    # -- 契约方法（签名即契约）--------------------------------------------
    def chat(self, messages: list[dict], *, provider: str = "zhida",
             temperature: float = 0.8, stream: bool = False) -> str | Iterator[str]:
        """主对话入口。provider: "main" | "zhida"。自动走缓存层。
        stream=True 返回分片迭代器（当前实现为全量取回后切片，SSE 由网关层按需升级）。"""
        system, user = self._split(messages)
        self.last_error = ""
        key = ""
        hit = None
        if self.cache_enabled:
            key = LLMCache.auto_key(provider, system, user, temperature)
            hit = self.cache.get(key)
        if hit is not None and hit != fallback_text("generic"):
            self.last_provider = provider + "(cache)"
            return self._as_stream(hit) if stream else hit

        p = self._pick(provider)
        failed = False
        try:
            text = p.chat(system, user, temperature=temperature, stream=False)
        except Exception as exc:            # 网络/协议/限额任何异常 → 兜底
            self._note(provider, f"chat 失败已兜底: {exc}")
            # 保留具体原因（如 HTTP Error 401: Unauthorized / 402 欠费），
            # 供探针与对局诊断把真实失败原因透给用户，而不是只有异常类名。
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            text = fallback_text("generic")
            failed = True
        if not failed and p.name != "mock" and self.cache_enabled:
            self.cache.set(key, text)
        self.last_provider = "fallback" if failed else p.name
        return self._as_stream(text) if stream else text

    def pregenerate(self, jobs: list[dict]) -> dict:
        """开局批量预生成（固定证词/开场白/金句演出），写入缓存库。
        job 字段：cache_key* / system / user / provider / temperature。
        返回 {done: n, failed: [cache_key...], errors: {cache_key: reason}}。"""
        done, failed, errors = 0, [], {}
        for job in jobs:
            ck = str(job.get("cache_key") or "")
            if not ck:
                failed.append("(missing_cache_key)")
                continue
            try:
                p = self._pick(job.get("provider", "main"))
                text = p.chat(job.get("system", ""), job.get("user", ""),
                              temperature=float(job.get("temperature", 0.8)))
                self.cache.set(ck, text)
                done += 1
            except Exception as exc:
                failed.append(ck)
                errors[ck] = str(exc)
                self._note("pregenerate", f"{ck}: {exc}")
        return {"done": done, "failed": failed, "errors": errors}

    def cached(self, cache_key: str) -> str | None:
        """命中预生成缓存；未命中返回 None（调用方决定是否降级兜底）。"""
        return self.cache.get(cache_key)

    def fallback(self, scene: str) -> str:
        """降级兜底文本（预写剧本片段），保证对局不断流。"""
        return fallback_text(scene)

    # -- 辅助 --------------------------------------------------------------
    @staticmethod
    def _as_stream(text: str) -> Iterator[str]:
        for i in range(0, len(text), 24):
            yield text[i:i + 24]

    def status(self) -> dict:
        return {
            "providers": {name: p.available() for name, p in self.providers.items()},
            "zhida_remaining": getattr(
                self.providers.get("zhida"), "budget", DailyBudget()).remaining(),
            "cache_entries": len(self.cache._data),
            "degrade_log": self.degrade_log[-10:],
        }


_client: LLMClient | None = None


def get_client() -> LLMClient:
    """进程级单例，供 server/F 窗口与各 Agent 共用。"""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
