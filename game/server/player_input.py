"""玩家聊天的保守本地适配；仅产出候选，裁决和状态修改仍归引擎。"""
from __future__ import annotations

import re
from collections.abc import Mapping

from engine.stage_machine import action_allowed


def parse_player_intent(text: str, *, stage: str | None = None,
                        locations: Mapping[str, str] | None = None) -> dict | None:
    """只识别完整搜证命令；地点来自本局公开场景，未知或歧义表达保留聊天。"""
    if not isinstance(text, str) or not action_allowed(stage, "search"):
        return None
    match = re.fullmatch(
        r"(?:我要|我想|请帮我|帮我)?(?:去|到|在)\s*(.+?)\s*(?:搜证|调查|查找|搜索|搜查)\s*[：:]?\s*(.+?)[。！!]?",
        text.strip(),
    )
    if not match:
        return None
    location, keyword = (part.strip() for part in match.groups())
    # 问句、复合命令、否定表达不执行，避免误消费行动力。
    if not keyword or any(mark in text for mark in ("？", "?", "，", ",", "；", ";", "然后", "不要", "别去", "是否", "吗", "能否", "可否", "不想", "不去", '"', "'", "“", "”", "‘", "’", "「", "」")):
        return None
    candidates = {key for key, name in (locations or {}).items()
                  if location in (key, name)}
    if len(candidates) != 1:
        return None
    return {"action_type": "search", "payload": {
        "location": candidates.pop(), "keyword": keyword}}
