"""pollution_check — 污染对照引擎（S2 创新机制：真实回答 vs 水军改写版）

契约：docs/CONTRACTS.md §3.4（知识卡系）；设计：本文件头部注释即最新口径。
职责（确定性裁决，禁止 AI 参与）：
- 5 道「污染对照」题（content/scenarios/kanshan/pollution/pc_*.json）；
  每题给出同一篇知乎真实回答的 original（作者原句）与 polluted（水军植入操纵话术后）；
- 玩家在 polluted 段落中圈出被植入的片段 → 引擎确定性比对 span.changed；
- 全对：辟谣弹药 +1、返还 1 AP、热度 -2（打击水军声量）；
  误选：热度 +3（被水军察觉，反噬）；部分对：只提示漏掉的处数，不直接给答案；
- summary() 供心晴诊室/求真相结算使用（污染识别率）。

为什么是 AI 原生 + 知乎独有：素材为知乎真实回答原句，玩法本体是「识别 AI 如何篡改
专业内容」——没有大模型就没有这个篡改样本，没有知乎社区就没有这些原文。
"""
from __future__ import annotations

import json
import random
from pathlib import Path


class PollutionCheck:
    #: 全对 / 误选 的热度反馈（由上层 OpinionFeed 应用，本模块只裁决不改热度）
    HEAT_REWARD = -2
    HEAT_PENALTY = 3

    def __init__(self, seed: int | None = None) -> None:
        self._cases: dict[str, dict] = {}
        self._rng = random.Random(seed)
        self._done: dict[str, dict] = {}   # pc_id -> {passed, picks, attempts}
        self._order: list[str] = []        # 出题顺序（确定性）
        self._cursor = 0
        self._ammo = 0
        self._ammo_earned = 0

    # ------------------------------------------------------------------ load
    def load(self, scenario_dir: str) -> None:
        """加载 content/scenarios/kanshan/pollution/ 题目（容错：目录缺失静默空载）。"""
        pdir = Path(scenario_dir) / "pollution"
        self._cases = {}
        if not pdir.is_dir():
            return
        for f in sorted(pdir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict) and data.get("id") and data.get("spans"):
                self._cases[data["id"]] = data
        self._order = sorted(self._cases)
        self._rng.shuffle(self._order)
        self._cursor = 0

    # ------------------------------------------------------------------ open
    def open_case(self, actor: str) -> dict | None:
        """取一道未完成的题（按顺序，确定性）。返回 None 表示已全部做完。

        返回结构：{id, title, author, card_id, topic_tag, original, polluted,
                   spans:[{id,text}], changed_total, source_note}
        spans 已洗牌（确定性 seed），前端直接按顺序渲染为可点选片段。
        """
        for pc_id in self._order[self._cursor:]:
            if pc_id in self._done:
                continue
            self._cursor = self._order.index(pc_id)
            case = self._cases[pc_id]
            spans = [dict(s) for s in case.get("spans", [])]
            self._rng.shuffle(spans)
            return {
                "id": case["id"],
                "title": case.get("title", ""),
                "author": case.get("author", ""),
                "card_id": case.get("card_id", ""),
                "topic_tag": case.get("topic_tag", ""),
                "original": case.get("original", ""),
                "polluted": case.get("polluted", ""),
                "source_note": case.get("source_note", ""),
                "manipulation": case.get("manipulation", []),
                "spans": [{"id": s["id"], "text": s.get("text", "")} for s in spans],
                "changed_total": sum(1 for s in case.get("spans", []) if s.get("changed")),
            }
        return None

    # ------------------------------------------------------------------ mark
    def mark(self, actor: str, pc_id: str, picks: list[str]) -> dict:
        """提交圈选结果（确定性裁决）。

        picks: 玩家认为「被植入」的 span_id 列表。
        返回 {ok, correct, missed, wrong, passed, ammo, ap_refund, heat_delta,
              first_try, transcript_hint, revealed:[{text, why}]}
        """
        case = self._cases.get(pc_id)
        if not case:
            return {"ok": False, "reason": "case_not_found",
                    "transcript_hint": "（这道题不存在——档案局没有这份对照记录）"}
        spans = case.get("spans", [])
        changed_ids = {s["id"] for s in spans if s.get("changed")}
        picked = {str(p) for p in (picks or [])}
        correct = sorted(picked & changed_ids)
        wrong = sorted(picked - changed_ids)
        missed = sorted(changed_ids - picked)
        passed = not missed and not wrong
        first_try = pc_id not in self._done

        ap_refund = 0
        heat_delta = 0
        if passed and first_try:
            self._ammo += 1
            self._ammo_earned += 1
            ap_refund = 1
            heat_delta = self.HEAT_REWARD
        elif wrong:
            heat_delta = self.HEAT_PENALTY

        # 已通过的成绩不可被后续失败覆盖（最好成绩锁定，防止刷分误伤结算）
        prev = self._done.get(pc_id, {})
        passed_effective = bool(passed or prev.get("passed"))
        self._done[pc_id] = {"passed": passed_effective, "picks": sorted(picked),
                             "attempts": prev.get("attempts", 0) + 1,
                             "actor": actor}

        revealed = [{"text": s.get("text", ""), "why": s.get("why", "")}
                    for s in spans if s.get("changed")]
        hint = self._hint(case, correct, missed, wrong, passed, first_try)
        return {"ok": True, "correct": len(correct), "missed": len(missed),
                "wrong": len(wrong), "passed": passed, "first_try": first_try,
                "changed_total": len(changed_ids), "ammo": self._ammo,
                "ap_refund": ap_refund, "heat_delta": heat_delta,
                "transcript_hint": hint, "revealed": revealed}

    def _hint(self, case: dict, correct: list, missed: list,
              wrong: list, passed: bool, first_try: bool) -> str:
        title = case.get("title", "")
        if passed and first_try:
            return (f"对照完成：《{title}》{len(correct)} 处操纵全部识别。"
                    f"辟谣弹药 +1（当前 {self._ammo}），行动力返还 1 点，热度 {self.HEAT_REWARD}——"
                    "你刚刚亲手拆掉了一条水军话术。")
        if passed:
            return f"《{title}》复核通过：{len(correct)} 处操纵全部命中（本题已计过分，不再重复给弹药）。"
        parts = [f"《{title}》命中 {len(correct)}/{len(correct) + len(missed)} 处。"]
        if wrong:
            parts.append(f"误判 {len(wrong)} 处——有些话刺耳，但它是作者原句；"
                         "判断操纵不能只靠语感。")
        if missed:
            parts.append(f"还漏了 {len(missed)} 处没圈出来，再对照原文读一遍。")
        return " ".join(parts)

    # --------------------------------------------------------------- summary
    def summary(self) -> dict:
        """结算用：{total, done, passed, ammo, accuracy}。"""
        total = len(self._cases)
        done = len(self._done)
        passed = sum(1 for v in self._done.values() if v.get("passed"))
        return {"total": total, "done": done, "passed": passed, "ammo": self._ammo,
                "ammo_earned": self._ammo_earned,
                "accuracy": round(passed / total, 3) if total else 0.0,
                "cases": {k: {"passed": v.get("passed")} for k, v in self._done.items()}}

    def ammo(self) -> int:
        return self._ammo

    def ammo_earned(self) -> int:
        return self._ammo_earned

    def spend_ammo(self, n: int = 1) -> int:
        """消耗辟谣弹药。返回实际消耗数量（库存不足则耗尽）。"""
        n = max(0, int(n))
        spent = min(n, self._ammo)
        self._ammo -= spent
        return spent
