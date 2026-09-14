"""共享的 Agent 状态、动作校验与本地规划器。

LLM 只提出意图；本模块把意图收敛到可执行动作，避免模型输出破坏剧情状态。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    stage: str = "break_ice"
    ap: int = 0
    goals: list[str] = field(default_factory=list)
    beliefs: dict[str, float] = field(default_factory=dict)
    relations: dict[str, int] = field(default_factory=dict)
    stress: int = 0
    recent_actions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    held_cards: list[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict | None) -> "AgentState":
        raw = raw or {}
        return cls(stage=str(raw.get("stage") or "break_ice"),
                   ap=int(raw.get("ap") or 0), goals=list(raw.get("goals") or []),
                   beliefs=dict(raw.get("beliefs") or {}), relations=dict(raw.get("relations") or {}),
                   stress=int(raw.get("stress") or 0), recent_actions=list(raw.get("recent_actions") or []),
                   evidence=list(raw.get("evidence") or []), held_cards=list(raw.get("held_cards") or []))

    def remember(self, action: str) -> None:
        self.recent_actions = (self.recent_actions + [action])[-8:]


ACTION_COST = {"search": 1, "chat": 1, "private_chat": 1, "counsel": 2,
               "skill": 1, "vote": 1, "accuse": 1, "advance": 0}


def validate_action(action: dict, allowed: list[str], state: AgentState) -> tuple[bool, str]:
    """轻量动作校验；剧情真相仍由 engine 裁决。"""
    typ = str((action or {}).get("type") or "")
    if typ not in set(allowed):
        return False, "动作不在当前阶段白名单"
    if typ == "advance" and len([a for a in allowed if a != "advance"]) > 0:
        return False, "当前仍有可执行动作，禁止提前推进"
    if state.ap and ACTION_COST.get(typ, 0) > state.ap:
        return False, "行动力不足"
    payload = action.get("payload") or {}
    if typ in ("chat", "introduce") and not str(payload.get("text") or "").strip():
        return False, "缺少台词"
    if typ == "search" and not payload.get("location"):
        return False, "缺少搜证地点"
    if typ == "counsel" and (not payload.get("card") or not payload.get("target")):
        return False, "开导缺少卡牌或目标"
    if typ == "vote" and len(payload.get("evidence") or state.evidence) < 2:
        return False, "至少需要两张证据卡"
    return True, ""


def rank_actions(allowed: list[str], state: AgentState, hints: dict | None = None) -> list[str]:
    """确定性本地排序，给重复行为和无效行动降权。"""
    hints = hints or {}
    preferred = list(hints.get("prefer_actions") or [])
    scores: dict[str, float] = {a: 0.0 for a in allowed}
    for i, action in enumerate(preferred):
        if action in scores:
            scores[action] += 4 - i * .4
    stage_bonus = {"investigate": {"search": 4, "skill": 2},
                   "round_table": {"counsel": 3, "skill": 2, "vote": 1},
                   "accuse": {"vote": 4, "accuse": 4}}
    for action, value in stage_bonus.get(state.stage, {}).items():
        if action in scores: scores[action] += value
    for action in state.recent_actions[-3:]:
        if action in scores: scores[action] -= 2.5
    if not state.held_cards and "counsel" in scores: scores["counsel"] -= 5
    if len(state.evidence) < 2 and "vote" in scores: scores["vote"] -= 5
    return sorted(allowed, key=lambda a: (-scores[a], a))
