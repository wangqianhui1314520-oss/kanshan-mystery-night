"""Judge Agent：指认阶段评估 + 心晴诊室结算（V3 版）。

契约：docs/CONTRACTS.md §二 C；设计：GAME_DESIGN_V3.md §3.6、KNOWLEDGE_SYSTEM.md §3.4、
DM_BOSS_DESIGN.md §四（指认 DM 分支）。

只演不裁的实现方式：
- target_hit / motive_hit / method_hit / evidence_coverage 由本模块对 truth.json 做
  **确定性比对**（不做语义自由发挥），LLM 只补充 logic_quality / misleading_points 软评分；
- 结局档位由 resolver（引擎）依据这些字段裁决，Agent 无权裁定结局；
- 心晴诊室：开导记录与档位由引擎统计，本模块只生成结算演出文案。

实现归 C 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

from pathlib import Path

import json
import re

try:
    from .llm_client import call_gateway, fallback_text, read_prompt, render_template
except ImportError:                          # 直接以脚本方式运行（selftest / 调试）
    from llm_client import call_gateway, fallback_text, read_prompt, render_template

PROMPT_DIR = Path(__file__).parent / "prompts"

_DM_TARGETS = {"dm", "kanshan", "刘看山", "看山", "dm_kanshan", "系统提示音"}


def _cjk_ngrams(text: str, n: int = 2) -> set[str]:
    han = re.findall(r"[\u4e00-\u9fff]+", str(text or ""))
    grams: set[str] = set()
    for seg in han:
        if len(seg) < n:
            grams.add(seg)
            continue
        for i in range(len(seg) - n + 1):
            grams.add(seg[i:i + n])
    return grams


class JudgeAgent:
    def __init__(self, gateway, truth: dict):
        self.gateway = gateway
        self.truth = truth
        self.system = (PROMPT_DIR / "judge_system.md").read_text(encoding="utf-8")

    # ---------------------------------------------------------------- 指认评分
    def judge(self, accusation: dict, player_clues: list) -> dict:
        """accusation: {target, motive_statement, method_statement}；clue 需含
        linked_truth_nodes（V3）或以 truth_node.proof_clues 反查（模板兼容）。
        返回字段与骨架一致：target_hit/motive_hit/method_hit/evidence_coverage/
        logic_quality/misleading_points；指认 DM 时附加 boss_accusal 分支字段。"""
        target = str(accusation.get("target") or "")
        clues = [c for c in (player_clues or []) if isinstance(c, dict)]

        if target.strip().lower() in _DM_TARGETS or "刘看山" in target:
            return self._judge_boss(accusation, clues)

        culprit = self.truth.get("culprit") or {}
        culprit_id = str(culprit.get("character") or "")
        culprit_name = str(culprit.get("name") or "")
        norm = target.strip().lower().replace("npc:", "").replace("char:", "")
        target_hit = bool(norm) and (
            norm == culprit_id.lower()
            or (bool(culprit_name) and culprit_name.split("（")[0] in target)
            or (culprit_id and culprit_id in norm))

        motive_hit = self._statement_hit(accusation.get("motive_statement"),
                                         culprit.get("motive"))
        method_hit = self._statement_hit(accusation.get("method_statement"),
                                         culprit.get("method"))

        covered, coverage = self._coverage(clues)

        soft = self._soft_scores(accusation, clues, target_hit,
                                 motive_hit, method_hit, coverage)
        return {
            "target_hit": target_hit,
            "motive_hit": motive_hit,
            "method_hit": method_hit,
            "evidence_coverage": round(coverage, 3),
            "logic_quality": soft["logic_quality"],
            "misleading_points": soft["misleading_points"],
            "summary": soft.get("summary", ""),
            "covered_truth_nodes": covered,          # 附加诊断字段，供 resolver/复盘
        }

    # ---------------------------------------------------------------- 心晴诊室
    def heart_clinic(self, counsel_records: list, ending: str = "normal") -> dict:
        """诊室结算演出。counsel_records: [{npc, card, success, golden_line}]；
        ending: normal | pollution_win | boss_reveal 等（引擎给定）。
        档位映射：0-1 normal / 2-3 archive / 4+ all_clear / 污染胜利 roast。"""
        ok = [r for r in counsel_records or [] if r.get("success")]
        if ending == "pollution_win":
            tier = "roast"
        elif len(ok) >= 4:
            tier = "all_clear"
        elif len(ok) >= 2:
            tier = "archive"
        else:
            tier = "normal"

        system = render_template(
            read_prompt("clinic_system.md"),
            tier=tier,
            counsel_records=json.dumps(counsel_records or [], ensure_ascii=False),
            ending_tone=ending)
        try:
            text = str(call_gateway(self.gateway, system,
                                    "生成心晴诊室结算文案。")).strip()
        except Exception:
            text = ""
        if not text:
            text = fallback_text("clinic_" + ("roast" if tier == "roast"
                                              else "all_clear" if tier == "all_clear"
                                              else "archive" if tier == "archive"
                                              else "normal"))
        return {
            "tier": tier,
            "counsel_success_count": len(ok),
            "clinic_text": text,
            "golden_lines": [r.get("golden_line") for r in ok if r.get("golden_line")],
        }

    # ---------------------------------------------------------------- 内部
    def _judge_boss(self, accusation: dict, clues: list) -> dict:
        """指认 DM 分支：破绽证据（tier=boss_flaw）≥5 才算命中（DM_BOSS_DESIGN §四），
        是否进入「终极·看山还是山」结局由 resolver 结合心晴数裁决。"""
        flaw_clues = [c for c in clues if c.get("tier") == "boss_flaw" or c.get("flaw_id")]
        flaw_ids = {c.get("flaw_id") or c.get("id") for c in flaw_clues}
        flaw_count = len(flaw_ids)
        soft = self._soft_scores(accusation, flaw_clues, flaw_count >= 5,
                                 None, None, min(1.0, flaw_count / 5))
        return {
            "target_hit": flaw_count >= 5,
            "motive_hit": flaw_count >= 5,       # 里层动机=设局钓鱼，与破绽集齐同判
            "method_hit": None,
            "evidence_coverage": round(min(1.0, flaw_count / 5), 3),
            "logic_quality": soft["logic_quality"],
            "misleading_points": soft["misleading_points"],
            "summary": soft.get("summary", ""),
            "boss_accusal": True,
            "flaw_evidence_count": flaw_count,
            "covered_truth_nodes": sorted(f for f in flaw_ids if f),
        }

    def _statement_hit(self, statement, reference) -> bool | None:
        """陈述命中判定（确定性启发：≥2 个 2-gram 重叠即算命中核心要素）。
        reference 缺失时返回 None（不得臆造）。"""
        if not statement or not reference:
            return None
        ref_grams = {g for g in _cjk_ngrams(reference, 2) if len(g) == 2}
        if not ref_grams:
            return None
        overlap = ref_grams & _cjk_ngrams(statement, 2)
        return len(overlap) >= 2

    def _coverage(self, clues: list) -> tuple[list[str], float]:
        nodes = self.truth.get("truth_nodes") or []
        if not nodes:
            return [], 0.0
        clue_ids = {str(c.get("id")) for c in clues if c.get("id")}
        linked: set[str] = set()
        for c in clues:
            linked |= {str(n) for n in (c.get("linked_truth_nodes") or [])}
        covered = []
        for node in nodes:
            nid = str(node.get("id"))
            proof = {str(p) for p in (node.get("proof_clues") or [])}
            if nid in linked or (proof & clue_ids):
                covered.append(nid)
        return covered, len(covered) / len(nodes)

    def _soft_scores(self, accusation, clues, target_hit, motive_hit,
                     method_hit, coverage) -> dict:
        """LLM 补充 logic_quality / misleading_points（JSON 失败 → 保守降级 0）。"""
        user = render_template(
            read_prompt("judge_system.md"),
            target_hit=target_hit, motive_hit=motive_hit,
            method_hit=method_hit, evidence_coverage=f"{coverage:.0%}",
            accusation=json.dumps(accusation or {}, ensure_ascii=False),
            statements=json.dumps(
                {k: accusation.get(k) for k in
                 ("motive_statement", "method_statement")} if accusation else {},
                ensure_ascii=False),
            clues=json.dumps(clues, ensure_ascii=False))
        try:
            raw = str(call_gateway(self.gateway, self.system, user)).strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
            data = json.loads(raw)
            quality = data.get("logic_quality")
            quality = int(quality) if isinstance(quality, (int, float)) else 0
            quality = max(0, min(5, quality))
            misleading = [str(m) for m in (data.get("misleading_points") or [])][:3]
            return {"logic_quality": quality,
                    "misleading_points": misleading,
                    "summary": str(data.get("summary", ""))[:60]}
        except Exception:
            # 降级：依据线索覆盖做保守判定，保证流程可继续
            return {"logic_quality": 0, "misleading_points": [], "summary": ""}
