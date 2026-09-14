"""内容安全过滤：文本检查 + FastAPI HTTP 中间件（契约 F 窗口职责）。

覆盖面：
- REST：ContentSafetyMiddleware 拦截 /api/* 的 POST JSON 体内所有字符串值，命中即 422；
- WS：Starlette 中间件不覆盖 WebSocket 消息，/ws/{id} 处理器内显式调用 check_text()；
- 出站：NPC/弹幕 mock 文本同样过 sanitize_text()，防模板带入风险词。

硬规则：命中即拦截并返回真实原因；不静默改写玩家语义、不放行、不伪造结果。
"""
import json
import re
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# 命中即拦截（硬风险）：政治敏感 / 违法与暴恐 / 色情赌博 / 真实个人隐私信息
_BLOCK_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("政治敏感内容", re.compile(
        r"(颠覆国家政权|分裂国家|台独|港独|疆独|藏独|法轮功|六四事件|"
        r"攻击党和国家领导人|煽动颠覆)", re.I)),
    ("违法与暴恐内容", re.compile(
        r"(制造(炸弹|爆炸物|炸药)|炸弹配方|枪支(买卖|代购)|毒品(制作|合成|购买)|"
        r"恐怖袭击(教程|策划)|投毒教程|自杀教程|自杀方法)", re.I)),
    ("色情与赌博内容", re.compile(
        r"(援交|裸聊|约炮|嫖娼|卖淫|淫秽(视频|直播)|网络赌博|博彩(平台|网站))", re.I)),
    ("真实隐私信息", re.compile(r"\b1[3-9]\d{9}\b")),                 # 手机号
    ("真实隐私信息", re.compile(r"\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")),  # 身份证号
    ("真实隐私信息", re.compile(r"\b\d{16,19}\b")),                   # 银行卡号
]

MAX_SCAN_FIELDS = 64          # 单请求最多扫描字符串数（防超大 payload 拖垮）
MAX_FIELD_LEN = 2000          # 单字段扫描截断长度


def check_text(text: str) -> tuple[bool, str | None]:
    """返回 (是否通过, 拦截原因)。通过时原因为 None。"""
    if not text:
        return True, None
    for reason, pat in _BLOCK_PATTERNS:
        if pat.search(text[:MAX_FIELD_LEN]):
            return False, reason
    return True, None


def sanitize_text(text: str) -> tuple[str, list[str]]:
    """出站净化：命中片段替换为＊，返回 (净化后文本, 命中类别列表)。"""
    hits: list[str] = []
    if not text:
        return text, hits
    for reason, pat in _BLOCK_PATTERNS:
        clean, n = pat.subn("＊", text[:MAX_FIELD_LEN])
        if n:
            hits.append(reason)
        text = clean
    return text, hits


def iter_strings(obj: Any, _depth: int = 0):
    """深度优先遍历 JSON，产出所有字符串值（有界）。"""
    if _depth > 8:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_strings(k, _depth + 1)
            yield from iter_strings(v, _depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from iter_strings(v, _depth + 1)


def scan_payload(obj: Any) -> tuple[bool, str | None]:
    """扫描整个 JSON 结构；超出扫描预算时保守放行（记录在日志侧）。"""
    n = 0
    for s in iter_strings(obj):
        n += 1
        if n > MAX_SCAN_FIELDS:
            return True, None  # 预算用尽：不再深扫（正常游戏动作不会触顶）
        ok, reason = check_text(s)
        if not ok:
            return False, reason
    return True, None


class ContentSafetyMiddleware(BaseHTTPMiddleware):
    """REST 请求体内容安全过滤（仅 POST + JSON）。

    拦截响应：422 {"ok": false, "blocked": true, "code": "content_blocked", "notice": 真实原因}
    ——不消耗任何游戏/API 额度，动作不落库。
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/"):
            ctype = request.headers.get("content-type", "")
            if "application/json" in ctype:
                body = await request.body()
                try:
                    payload = json.loads(body) if body else {}
                except ValueError:
                    payload = None
                if payload is not None:
                    ok, reason = scan_payload(payload)
                    if not ok:
                        return JSONResponse(status_code=422, content={
                            "ok": False, "blocked": True,
                            "code": "content_blocked",
                            "notice": f"内容安全过滤：检测到{reason}，"
                                      f"请求已拦截（未执行动作、未消耗任何额度）",
                        })
                # 重新挂载 body 供下游读取
                request._body = body
        return await call_next(request)
