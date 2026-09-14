"""DM Agent：全局主持人——刘看山伪装"系统提示音"人格。

契约：docs/CONTRACTS.md §二 C；设计：DM_BOSS_DESIGN.md（破绽计数注入 + 终极层现身演出）、
STORY_ADAPTATION.md 第一幕（叮——系统提示音腔调）、GAME_DESIGN_V3.md §四（弹幕/哦豁时刻）。

职责边界（只演不裁）：
- 播报/转述/氛围/弹幕/现身演出全部是"演"；事实与线索只来自引擎裁决结果，fact 一字不改；
- 破绽计数由引擎维护，Agent 只接收注入（set_flaw_count），不自行判定伏笔成立；
- boss_reveal 触发权归引擎（resolver boss_layer 分支），本模块只负责演出。

实现归 C 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

from pathlib import Path

try:
    from .llm_client import (call_gateway, fallback_text, read_prompt,
                             render_template)
except ImportError:                          # 直接以脚本方式运行（selftest / 调试）
    from llm_client import (call_gateway, fallback_text, read_prompt,
                            render_template)

PROMPT_DIR = Path(__file__).parent / "prompts"


class DMAgent:
    def __init__(self, gateway):
        self.gateway = gateway          # LLMClient 或 chat(system,user) 网关
        self.system = (PROMPT_DIR / "dm_system.md").read_text(encoding="utf-8")
        self.flaw_count = 0             # 看山破绽计数（引擎注入，0-5）

    # ---------------------------------------------------------------- 状态注入
    def set_flaw_count(self, count: int) -> None:
        """引擎在破绽线索解锁时调用（flaw_id flavor_1..5 → 1..5）。"""
        self.flaw_count = max(0, min(5, int(count)))

    def _persona_system(self) -> str:
        return render_template(self.system, flaw_count=self.flaw_count)

    def _flaw_suffix(self) -> str:
        """播报尾部破绽味（确定性渲染，零 LLM 成本，mock/真实双通道一致）。"""
        if self.flaw_count >= 5:
            return "（停顿 0.8 秒。该停顿是不必要的——系统自我说明。）"
        if self.flaw_count >= 3:
            return "（本条播报由系统自动生成。大概。）"
        return ""

    def _llm(self, system: str, user: str, provider: str = "zhida") -> str | None:
        try:
            out = call_gateway(self.gateway, system, user, provider=provider)
            return str(out).strip() or None
        except Exception:
            return None

    # ---------------------------------------------------------------- 契约方法
    def scene_desc(self, context: dict) -> str:
        """生成场景描写（预生成缓存优先）。"""
        pre_key = f"scene_desc:{context.get('location', '')}:{context.get('stage', '')}"
        cached_text = None
        if hasattr(self.gateway, "cached"):
            try:
                cached_text = self.gateway.cached(pre_key)  # type: ignore[attr-defined]
            except Exception:
                cached_text = None
        if cached_text:
            return cached_text
        user = render_template(
            "用系统提示音口吻描写当前场景（≤120字），只渲染氛围，不得发明事实或线索。\n"
            "上下文：{{ctx}}", ctx=context)
        text = self._llm(self._persona_system(), user)
        if not text:
            text = fallback_text("scene_desc")
        return text + self._flaw_suffix()

    def stage_announce(self, stage: str, goal: str, actions_left: int) -> str:
        """阶段播报：确定性模板（零成本 + 可测试），带破绽尾缀。"""
        base = fallback_text("stage_announce").format(
            stage=stage, goal=goal, actions_left=actions_left)
        return base + self._flaw_suffix()

    def action_feedback(self, action: str, result: dict) -> str:
        """把规则引擎的裁决结果转述为世界内反馈。

        只演不裁：result 由引擎给出；若含 clue，fact 原文转述一字不改，
        AI 最多在事实后追加一句氛围吐槽（失败则不加）。"""
        if result.get("success"):
            head = fallback_text("action_feedback_hit")
            clue = result.get("clue") or {}
            fact = clue.get("fact")
            if fact:
                body = f"{head}\n【{clue.get('name', '线索卡')}】{fact}"
                flavor = self._llm(
                    self._persona_system(),
                    "为刚命中的搜证结果追加一句 ≤25 字的系统音氛围吐槽，"
                    "只许引用 flavor_hint 的方向，不得改写或复述 fact，不得泄露真相。\n"
                    f"flavor_hint：{clue.get('flavor_hint', '')}\n"
                    f"线索名：{clue.get('name', '')}")
                if flavor:
                    body += f"\n{flavor}"
                return body + self._flaw_suffix()
            return head + f"（{action}）" + self._flaw_suffix()
        return fallback_text("action_feedback_miss") + self._flaw_suffix()

    # ---------------------------------------------------------------- 扩展演出
    def danmaku(self, context: dict, n: int = 4) -> list[str]:
        """知乎热评风弹幕 3-5 条（V3 §四 欢乐源 #1）。失败 → 预写弹幕池。"""
        system = read_prompt("dm_danmaku.md")
        user = (
            f"生成 {max(3, min(5, n))} 条弹幕，每行一条。"
            f"事件摘要：{context.get('event_summary') or context}")
        text = self._llm(system, user) or fallback_text("danmaku")
        lines = [ln.strip(" -*•\t") for ln in str(text).splitlines()]
        lines = [ln for ln in lines if ln]
        return lines[:max(3, min(5, n))] if lines else [fallback_text("danmaku")]

    def daily_briefing(self, context: dict) -> str:
        """每日案件导读：zhida 低频高光位（限额/失败由 LLMClient 自动降级）。"""
        system = render_template(
            read_prompt("dm_daily_briefing.md"),
            daily_topic=context.get("daily_topic", "#看山失踪#"),
            event_pool=context.get("event_pool", "监控室删除记录/鱼干失窃/横幅抽风"))
        text = self._llm(system, "生成今日导读。", provider="zhida")
        return (text or fallback_text("daily_briefing")) + self._flaw_suffix()

    def boss_reveal(self, context: dict) -> str:
        """终极层现身演出（触发判定归引擎；本方法只演出，不判定是否触发）。

        context: {flaw_list: [...], counsel_count: int, accuse_target: str, ...}"""
        system = render_template(
            read_prompt("dm_boss_reveal.md"),
            flaw_list="、".join(context.get("flaw_list") or
                                ["鱼干口味口误", "最高权限删除", "主人级签名",
                                 "唤醒词彩蛋", "策划签名"]))
        user = ("生成终极层现身演出。当前破绽已集齐，引擎已判定触发。"
                f"补充语境：{context}")
        text = self._llm(system, user)
        return text or fallback_text("boss_reveal")
