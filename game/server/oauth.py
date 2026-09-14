"""知乎 OAuth 登录 + 隐私三件套（MEGA_MODE §一 / 契约 v2.1 §3.7）。

流程（zhihu-skill hackathon-oauth.md 为事实源）：
  1. 前端跳转 GET https://openapi.zhihu.com/authorize?redirect_uri=..&app_id=..&response_type=code
  2. 回调 {redirect_uri}?authorization_code=..（兼容 code）
  3. 后端 POST https://openapi.zhihu.com/access_token（form: app_id/app_key/
     grant_type=authorization_code/redirect_uri/code）→ access_token（成功以
     响应含 access_token 为准；code:20000 仅表示成功，不能仅凭它判失败）
  4. GET https://openapi.zhihu.com/user（0.7.2 新接口）：
     Authorization: Bearer <ZHIHU_ACCESS_SECRET> + X-OAuth-Token: <token>
     → fullname / headline / avatar_path / uid

隐私铁律（MEGA_MODE §一 / 契约 v2.1）：
  只取公开三件套（昵称/头像/headline）+ uid；email/phone_no 等字段一律忽略丢弃；
  OAuth token 仅存服务端内存（不落盘、不进前端响应/日志）；
  profile 三件套缓存在 session 内（避免重复调用户数据 API）。
凭证仅环境变量：ZHIHU_OAUTH_APP_ID / ZHIHU_OAUTH_APP_KEY / ZHIHU_OAUTH_REDIRECT_URI。
"""
import os
import time
from pathlib import Path

import httpx

# 警衔花名占位表（确定性映射；AI 个性化生成是 C 组接入点，接入后替换）
RANK_KEYWORDS = [
    ("码农", "调试人生司司长"), ("程序员", "调试人生司司长"), ("开发", "调试人生司司长"),
    ("学生", "见习档案员"), ("设计", "像素炼金术士"), ("产品", "需求粉碎机"),
    ("运营", "热搜冲浪冠军"), ("老师", " chief 键证官"), ("医生", "心晴急诊科主任"),
    ("律师", "条款破译专家"), ("记者", "真相 Tracking 科"),
]


class ZhihuOAuth:
    def __init__(self, access_secret: str = ""):
        self.app_id = os.environ.get("ZHIHU_OAUTH_APP_ID", "").strip()
        self.app_key = os.environ.get("ZHIHU_OAUTH_APP_KEY", "").strip()
        self.redirect_uri = os.environ.get("ZHIHU_OAUTH_REDIRECT_URI", "").strip()
        self.openapi_base = os.environ.get(
            "ZHIHU_OPENAPI_BASE", "https://openapi.zhihu.com").rstrip("/")
        self.access_secret = (access_secret or os.environ.get(
            "ZHIHU_ACCESS_SECRET", "")).strip()
        self.timeout = float(os.environ.get("ZHIHU_GAME_HTTP_TIMEOUT", "10"))
        self.last_error: str | None = None

    # ------------------------------------------------------------------ 状态
    def configured(self) -> bool:
        return bool(self.app_id and self.app_key and self.redirect_uri)

    def authorize_url(self) -> str:
        """前端跳转用授权 URL（App ID 为公开配置，可回传前端）。"""
        if not self.app_id:
            return ""
        return (f"{self.openapi_base}/authorize?response_type=code"
                f"&app_id={self.app_id}&redirect_uri={self.redirect_uri}")

    @staticmethod
    def _diag(secret: str) -> str:
        """诊断信息只展示来源/长度/SHA-256 短前缀，不展示完整值（文档要求）。"""
        import hashlib
        if not secret:
            return "未配置"
        return f"len={len(secret)} sha256={hashlib.sha256(secret.encode()).hexdigest()[:8]}…"

    # -------------------------------------------------------------- token 交换
    async def exchange(self, code: str) -> dict:
        """authorization_code → OAuth access_token。返回降级信封（同网关口径）。"""
        code = str(code or "").strip()
        if not code:
            return {"ok": False, "source": "rejected",
                    "notice": "缺少授权码（回调参数 authorization_code/code 为空）"}
        if not self.configured():
            self.last_error = "未配置 ZHIHU_OAUTH_APP_ID/ZHIHU_OAUTH_APP_KEY/ZHIHU_OAUTH_REDIRECT_URI"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": f"OAuth 凭证未配置（App Key {self._diag(self.app_key)}）"
                              f"——登录不可用，不伪造登录态"}
        form = {"app_id": self.app_id, "app_key": self.app_key,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri, "code": code}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.openapi_base}/access_token",
                                         data=form)
        except httpx.HTTPError as e:
            self.last_error = f"网络失败：{type(e).__name__}"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": f"OAuth token 交换网络失败：{type(e).__name__}；不伪造登录态"}
        if resp.status_code != 200:
            self.last_error = f"HTTP {resp.status_code}"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": f"OAuth token 交换返回 HTTP {resp.status_code}；不伪造登录态"}
        try:
            data = resp.json()
        except ValueError:
            self.last_error = "响应非 JSON"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": "OAuth token 交换响应非 JSON；不伪造登录态"}
        token = str(data.get("access_token", "")).strip()
        if not token:
            self.last_error = f"无 access_token（code={data.get('code')}）"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": (f"OAuth 交换失败（业务 code={data.get('code')}，"
                               f"msg={data.get('error_description') or data.get('msg') or '无 access_token'}）"
                               "；常见原因：回调地址与登记值不完全一致 / code 已使用或过期；不伪造登录态")}
        return {"ok": True, "source": "api",
                "data": {"access_token": token,
                         "expires_in": int(data.get("expires_in", 0)),
                         "obtained_at": time.time()}}

    # ------------------------------------------------------------- 用户资料
    async def fetch_profile(self, oauth_token: str) -> dict:
        """GET /user（0.7.2）：Bearer Access Secret + X-OAuth-Token → 公开三件套。"""
        if not self.access_secret:
            self.last_error = "未配置 ZHIHU_ACCESS_SECRET"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": "未配置 ZHIHU_ACCESS_SECRET，无法鉴权用户数据接口；不伪造资料"}
        if not oauth_token:
            return {"ok": False, "source": "rejected",
                    "notice": "无 OAuth token（请先完成登录交换）"}
        headers = {"Authorization": f"Bearer {self.access_secret}",
                   "X-OAuth-Token": oauth_token,
                   "X-Request-Timestamp": str(int(time.time()))}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.openapi_base}/user", headers=headers)
        except httpx.HTTPError as e:
            self.last_error = f"网络失败：{type(e).__name__}"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": f"用户资料接口网络失败：{type(e).__name__}；不伪造资料"}
        if resp.status_code != 200:
            self.last_error = f"HTTP {resp.status_code}"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": f"用户资料接口返回 HTTP {resp.status_code}"
                              f"（token 过期或鉴权失败时停止读取，不回退其他账号）；不伪造资料"}
        try:
            raw = resp.json()
        except ValueError:
            self.last_error = "响应非 JSON"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": "用户资料响应非 JSON；不伪造资料"}
        # 隐私三件套 + uid：只挑公开字段，其余（email/phone_no/...）一律丢弃
        profile = {
            "uid": str(raw.get("uid", "")),
            "fullname": str(raw.get("fullname", "")),
            "headline": str(raw.get("headline", "")),
            "avatar_path": str(raw.get("avatar_path", "")),
        }
        if not profile["uid"]:
            self.last_error = "响应缺 uid"
            return {"ok": False, "source": "fallback", "degraded": True,
                    "notice": "用户资料响应缺少 uid；不伪造资料"}
        return {"ok": True, "source": "api", "data": profile}

    # ------------------------------------------------------------- 侦探证
    @staticmethod
    def dossier(profile: dict) -> dict:
        """《求真档案局特聘侦探证》：编号=uid 后 6 位、警衔=headline 欢乐花名。

        花名当前为确定性关键词映射（占位）；AI 个性化生成由 C 组接入后替换。
        """
        uid = profile.get("uid", "")
        headline = profile.get("headline", "")
        badge_no = uid[-6:] if len(uid) >= 6 else (uid or "000000").zfill(6)
        rank = next((r for kw, r in RANK_KEYWORDS if kw in headline),
                    "荣誉见习侦探")
        return {
            "badge_no": badge_no,
            "rank": rank,
            "owner": profile.get("fullname", "匿名侦探"),
            "headline": headline,
            "avatar": profile.get("avatar_path", ""),
            "generator": "deterministic-placeholder",  # C 组 AI 生成接入点
        }
