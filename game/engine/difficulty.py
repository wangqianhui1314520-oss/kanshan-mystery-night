"""difficulty — 动态难度导演（幕结算钩子 → 下幕线索梯度 + 热度阈值微调）

契约：docs/GAMEPLAY_V31.md B.2；设计：docs/MEGA_MODE.md §四.1（动态难度正式化）、
§四.2（防卡死提示：同一线索 2 轮无进展 → DM 发「档案局备忘录」，点方向不泄底）。
职责（确定性裁决，禁止 AI 参与）：
- 幕结算钩子 on_act_settled(metrics)：按本幕推进度判定下幕梯度三档
  assist（新手多提示）/ normal / hard（老手模糊化）；
- 线索梯度落地：suggest_keywords 提示数（5/3/2）、hidden/boss 条件宽限（±1）、
  未命中备忘录预算（2/1/0 条/幕）；
- 热度阈值微调：assist +10（真线索更难被水军淹没）/ hard -10 / normal 0；
- 备忘录生成 memo_for(evidence_chain, location)：取该地点候选 tags 方向词，
  只点方向不泄底。

实现归 B 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

# 梯度 → (suggest_keywords 数量, boss 条件宽限, 每幕备忘录预算, 热度阈值增量)
GRADIENT_TABLE = {
    "assist": {"suggest_limit": 5, "boss_grace": 1, "memo_budget": 2, "heat_delta": 10},
    "normal": {"suggest_limit": 3, "boss_grace": 0, "memo_budget": 1, "heat_delta": 0},
    "hard": {"suggest_limit": 2, "boss_grace": -1, "memo_budget": 0, "heat_delta": -10},
}


class DifficultyDirector:
    def __init__(self) -> None:
        self.gradient = "normal"
        self._memo_left = GRADIENT_TABLE["normal"]["memo_budget"]

    # ------------------------------------------------------------- 幕结算钩子
    def on_act_settled(self, metrics: dict) -> dict:
        """幕结算钩子。metrics（本幕累计，缺项按 0）：
        {act, clue_count, coverage, counsel_count, stuck_rounds, refutes}。

        判定（确定性）：
        - assist：线索 <3 或 coverage <0.2 或卡死轮 ≥2（推进受阻）；
        - hard：coverage >0.7 且 clue_count >8（推进过快，模糊化）；
        - 其余 normal。
        """
        clue = int(metrics.get("clue_count", 0) or 0)
        cov = float(metrics.get("coverage", 0.0) or 0.0)
        stuck = int(metrics.get("stuck_rounds", 0) or 0)
        if clue < 3 or cov < 0.2 or stuck >= 2:
            g = "assist"
        elif cov > 0.7 and clue > 8:
            g = "hard"
        else:
            g = "normal"
        self.gradient = g
        self._memo_left = GRADIENT_TABLE[g]["memo_budget"]
        return {"gradient": g,
                "heat_threshold_delta": GRADIENT_TABLE[g]["heat_delta"],
                "suggest_limit": GRADIENT_TABLE[g]["suggest_limit"],
                "boss_grace": GRADIENT_TABLE[g]["boss_grace"],
                "memo_budget": GRADIENT_TABLE[g]["memo_budget"]}

    # ------------------------------------------------------------- 落地应用
    def apply(self, evidence_chain=None, opinion_feed=None) -> dict:
        """把当前梯度落到引擎：evidence_chain.set_gradient() / opinion_feed.set_threshold_delta()。"""
        table = GRADIENT_TABLE[self.gradient]
        if evidence_chain is not None:
            evidence_chain.set_gradient(self.gradient)
        if opinion_feed is not None:
            opinion_feed.set_threshold_delta(table["heat_delta"])
        return {"gradient": self.gradient, "applied": True}

    # ------------------------------------------------------------- 防卡死备忘录
    def memo_left(self) -> int:
        return self._memo_left

    def memo_for(self, evidence_chain, location: str, player_id: str | None = None) -> dict | None:
        """「档案局备忘录」：未命中搜证时点方向不泄底（预算内）。

        取该地点候选线索 tags 并集首词作为方向词（确定性）；预算耗尽返回 None。
        """
        if self._memo_left <= 0:
            return None
        hints = evidence_chain.suggest_keywords(location) if evidence_chain else []
        if not hints:
            return None
        self._memo_left -= 1
        return {"kind": "memorandum",
                "text": f"【档案局备忘录】有人在「{hints[0]}」的方向查过点什么……门没锁，去看看？",
                "location": location, "hint": hints[0]}
