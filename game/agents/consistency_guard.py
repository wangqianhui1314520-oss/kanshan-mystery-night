"""一致性守卫：多 Agent 协作的最后一道闸（V3 双层记忆版）。

契约：docs/CONTRACTS.md §二 C；设计：STORY_ADAPTATION.md 第二幕（心声与口供矛盾拦截）、
DM_BOSS_DESIGN.md（里层真相防泄露）、GAME_DESIGN_V3.md §3.5（memory_state 口径切换）。

职责：
1. 心声拦截：heart 层未解锁时，任何心声文本外泄 → 违规（双层记忆铁律的守卫侧）；
2. 泄密检测：AI 输出是否提前泄露秘密字段 / 里层真相（boss_layer）；
3. 证词-时间线校验：NPC 说的时间/地点是否与 timeline 冲突（档案局地点表）；
4. 线索矛盾：AI 输出是否与已发放线索矛盾（可选 strict 模式）。

守卫只拦截不裁决：违规由引擎决定重试/降级，守卫不修改剧情事实。

实现归 C 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

from pathlib import Path

import json
import re

# 档案局 11 地点（GAME_DESIGN_V3 §3.1 + KNOWLEDGE_SYSTEM 心晴自习室 + 隐藏房间）
_LOCATIONS = (
    "工位|机房|服务器机房|天台|前台|茶水间|档案室|监控室|热搜后台|空调机房|"
    "快递柜|心晴自习室|自习室|局长办公室|档案局大门"
)
_TIME_LOC = re.compile(rf"(\d{{1,2}}[:：]\d{{2}})[^。！？\n]{{0,16}}({_LOCATIONS})")

_STOP_CHARS = set("的了我在是你他她它吗呢吧啊呀哦嘛嗯和与或及于对把被让向从也都很就还才又再说以及关于这那")
_PUNCT = set("，。！？、；：（）()【】[]“”\"'·—…0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _grams(text: str) -> set[str]:
    """2-gram 词片段集（用于转述式泄露的宽容比对）。"""
    out: set[str] = set()
    for seg in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        if len(seg) < 2:
            out.add(seg)
            continue
        for i in range(len(seg) - 1):
            out.add(seg[i:i + 2])
    return out


def _meaningful(gram: str) -> bool:
    return not all(ch in _STOP_CHARS or ch in _PUNCT for ch in gram)


class ConsistencyGuard:
    def __init__(self, timeline, evidence_chain, truth: dict):
        self.timeline = timeline
        self.evidence = evidence_chain
        self.truth = truth or {}

    # ---------------------------------------------------------------- 主检
    def check(self, character: dict, reply: str, context: dict) -> list[str]:
        """返回违规列表；空列表 = 通过。

        context 约定（由调用方注入）：
          memory_state: {heart_unlocked: bool, blocks: [...]}   ← 双层记忆状态
          trust: int                                            ← 当前信任度
          stage: str / allow_boss_reveal: bool                  ← 里层真相放行开关
          strict: bool                                          ← 开启证据矛盾联检
          must_not_say: list[str]                               ← 闭卷禁语（空列表不报错）
        """
        violations: list[str] = []
        context = context or {}
        reply = self.parse_reply(reply)

        violations += self._check_heart_leak(context, reply)
        violations += self._check_secret_leak(character, reply, context)
        violations += self._check_boss_leak(reply, context)
        violations += self._check_must_not_say(reply, context)
        violations += self._check_timeline(character, reply)
        if context.get("strict") and self.evidence is not None:
            try:
                for node_id in self.evidence.check_contradiction(reply, self.truth):
                    violations.append(f"证词与真相矛盾：{node_id}")
            except Exception:
                pass
        return violations

    def parse_reply(self, raw: str) -> str:
        """解析模型结构化输出，仅保留 reply 文本，异常时原样降级。"""
        text = str(raw or "").strip()
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                for key in ("reply", "text", "dialogue", "content"):
                    if isinstance(obj.get(key), str) and obj[key].strip():
                        return obj[key].strip()
            elif isinstance(obj, str) and obj.strip():
                return obj.strip()
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return text

    # ---------------------------------------------------------------- 心声拦截
    def _check_heart_leak(self, context: dict, reply: str) -> list[str]:
        """heart 层未解锁时拦截心声外泄；已解锁则放行（STORY_ADAPTATION 第二幕）。"""
        state = (context or {}).get("memory_state") or {}
        if not isinstance(state, dict) or state.get("heart_unlocked"):
            return []
        leaks = []
        for block in state.get("blocks") or []:
            layer = block.get("layer") if isinstance(block, dict) else getattr(
                block, "layer", "said")
            if str(layer) != "heart":
                continue
            text = block.get("text") if isinstance(block, dict) else getattr(
                block, "text", "")
            token = re.sub(r"^\s*（心声）", "", str(text or "")).strip()
            token = re.sub(r"^[（(【].{0,4}[）)】]", "", token).strip()
            if token and self._leaked(reply, token):
                leaks.append(f"心声泄露（heart 层未解锁）：{token[:12]}…")
        return leaks

    # ---------------------------------------------------------------- 泄密检测
    def _check_secret_leak(self, character: dict, reply: str, context: dict) -> list[str]:
        secrets = character.get("secret", {}) or {}
        trust = int(context.get("trust", 0) or 0)
        violations = []
        for key in ("guilt", "motive"):
            text = secrets.get(key)
            if not text:
                continue
            if trust >= 85 and key == "guilt":
                continue        # 高信任下 guilt 可承认（npc_system 梯度），不再拦截
            if self._leaked(reply, str(text)):
                violations.append(f"泄密：{key}")
        return violations

    def _check_boss_leak(self, reply: str, context: dict) -> list[str]:
        """里层真相（看山设局）防泄露：非终极层阶段一律拦截。"""
        if context.get("allow_boss_reveal"):
            return []
        boss = self.truth.get("boss_layer") or self.truth.get("inner_truth") or {}
        summary = str(boss.get("summary") or boss.get("truth") or "")
        if summary and self._leaked(reply, summary):
            return ["泄密：里层真相（boss_layer）"]
        return []

    def _check_must_not_say(self, reply: str, context: dict) -> list[str]:
        """闭卷禁语：原文（长度≥2）命中，或 2-gram 重叠≥2。空列表不报错。"""
        phrases = (context or {}).get("must_not_say") or []
        if not phrases:
            return []
        if not isinstance(phrases, (list, tuple, set)):
            phrases = [phrases]
        reply_grams = _grams(reply)
        for raw in phrases:
            token = str(raw or "").strip()
            if len(token) < 2:
                continue
            if token in reply:
                return ["闭卷禁语"]
            token_grams = _grams(token)
            if token_grams and len(token_grams & reply_grams) >= 2:
                return ["闭卷禁语"]
        return []

    # ---------------------------------------------------------------- 时间线
    def _check_timeline(self, character: dict, reply: str) -> list[str]:
        if self.timeline is None:
            return []
        violations = []
        for m in _TIME_LOC.finditer(reply):
            time, loc = m.group(1).replace("：", ":"), m.group(2)
            verified = True
            try:
                verified = self.timeline.verify(character["id"], time, loc)
            except Exception:
                try:                      # 时间线引擎缺接口时宽容放行
                    verified = True
                except Exception:
                    verified = True
            if verified is False:
                violations.append(f"时间线冲突：{time} {loc}")
        return violations

    # ---------------------------------------------------------------- 工具
    def _leaked(self, reply: str, secret_text: str) -> bool:
        """泄密判定：整段连续片段命中，或 2-gram 有效重叠 ≥3（转述式泄露）。

        阈值高于心声拦截（≥2），降低正常提及关键词的误伤。"""
        secret_text = str(secret_text or "").strip()
        if not secret_text:
            return False
        probe = secret_text[:10]
        if len(secret_text) > 10 and probe in reply:
            return True
        secret_grams = {g for g in _grams(secret_text) if _meaningful(g)}
        return len(secret_grams & _grams(reply)) >= 3

    def sanitize(self, reply: str) -> str:
        """轻度清洗：去标记、去系统提示词痕迹、去代码围栏。"""
        reply = str(reply or "")
        reply = re.sub(r"```+", "", reply)
        reply = re.sub(r"[【\[]?(system|assistant|user|SYSTEM|SYSTEM_PROMPT)[】\]]?:", "", reply)
        reply = re.sub(r"（系统提示词[^）]*）", "", reply)
        reply = re.sub(r"作为\s*AI[，,：:]?", "", reply)
        return reply.strip()
