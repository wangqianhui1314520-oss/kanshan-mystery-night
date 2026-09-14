"""裁决器：行动成功率判定与结局结算。

行动判定：骰子(d20) + 属性 vs 难度（沿用 Demo 的判定模型）。
结局结算：裁判 Agent 的评分 + 线索覆盖率 → 真相达成度 → 结局档位。

V3 升级（docs/GAME_DESIGN_V3.md §五、docs/DM_BOSS_DESIGN.md §四、
docs/KNOWLEDGE_SYSTEM.md §3.4）：
- 行动力池：每轮 3AP，search=1 / counsel=2 / refute=2 / skill=1，spend/can_afford/reset；
- 8+2 结局矩阵（matrix_ending）：含 boss_layer 与「指认：DM」分支
  （终极·看山还是山 / 群嘲·你连 DM 都想锤? / 隐藏·被删的第 7 章 /
  隐藏·看山的鱼干 / 隐藏·全员心晴 / 沉冤得雪 / 污染胜利）；
- truth_coverage：按 truth_nodes.proof_clues 计算证据覆盖度（Judge 打分依据）；
- resolve_accusation：指认必须 ≥2 张证据卡支撑（V3 §3.6）；
- resolve_boss_accusation：破绽 ≥5 才允许指认 DM。

旧骨架签名与语义保留：__init__ / resolve_action / calc_ending。
"""
import random

# ---------------------------------------------------------------- 结局矩阵定义
# key -> (中文标题, 达成条件描述)；旧 perfect/partial/wrong 保留兼容 calc_ending
ENDINGS = {
    "perfect_restoration": ("完美还原", "指认命中 + truth_node 覆盖 ≥90%"),
    "truth_revealed": ("真相大白", "指认命中 + 覆盖 60-89%"),
    "vindicated": ("沉冤得雪", "错误指认但「被裹挟者」跳反成功"),
    "pollution_win": ("污染胜利", "污染阵营成功把热度带偏至终局"),
    "deleted_chapter7": ("隐藏·被删的第 7 章", "集齐盐言彩蛋线 5 碎片"),
    "kanshan_fish": ("隐藏·看山的鱼干", "沉底君好感拉满（boss_key）+ V587 真身揭穿——看山把最后一袋彩虹鳟鱼味鱼干留在工位：真相要追，鱼干也要吃"),
    "all_hearts_clear": ("隐藏·全员心晴", "知识开导成功 4+（看山自己推门回来）"),
    "kanshan_still_mountain": ("终极·看山还是山", "指认 DM 成功 + 心晴诊室 2+"),
    "dm_mock": ("你连 DM 都想锤?", "破绽不足 5 就想指认 DM（欢乐群嘲，不惩罚）"),
    "wrong": ("全员喷子结局", "指认错误，DM 逐个锐评推理翻车现场"),
}


class Resolver:
    def __init__(self, stats: dict = None, dc: int = 12):
        self.stats = stats or {"str": 10, "dex": 10, "int": 10, "cha": 10}
        self.dc = dc
        # ---- V3 新增：行动力池 ----
        self.action_points = 3
        self.ap_per_round = 3

    # -------------------------------------------------------------- 旧骨架 API
    def resolve_action(self, attr: str, dc: int = None) -> dict:
        """行动裁决：返回骰面、总值与成败。"""
        target = dc or self.dc
        d20 = random.randint(1, 20)
        total = d20 + self.stats.get(attr, 10)
        return {
            "d20": d20,
            "bonus": self.stats.get(attr, 10),
            "total": total,
            "dc": target,
            "success": total >= target,
        }

    def calc_ending(self, judge_result: dict, clue_count: int, truth_total: int) -> dict:
        """结局结算：综合裁判评分与证据覆盖（旧 Demo 模型，保留兼容）。"""
        target = 1 if judge_result.get("target_hit") else 0
        motive = 1 if judge_result.get("motive_hit") else 0
        method = 1 if judge_result.get("method_hit") else 0
        coverage = min(1.0, clue_count / max(1, truth_total))
        score = (target * 0.5 + motive * 0.2 + method * 0.2 + coverage * 0.1) * 100

        if score >= 85:
            ending = "perfect"
        elif score >= 50:
            ending = "partial"
        else:
            ending = "wrong"
        return {"score": round(score, 1), "ending": ending,
                "detail": {"target": target, "motive": motive,
                           "method": method, "coverage": round(coverage, 2)}}

    # -------------------------------------------------------------- V3 行动力
    def can_afford(self, n: int) -> bool:
        """当前行动点是否足够（counsel/refute=2，search/skill=1）。"""
        return self.action_points >= n

    def spend(self, n: int) -> bool:
        """扣行动力；不足时返回 False（不透支）。"""
        if not self.can_afford(n):
            return False
        self.action_points -= n
        return True

    def refund(self, n: int) -> None:
        """返还行动力（技能结算失败回滚等场景）。"""
        self.action_points = min(self.ap_per_round * 2, self.action_points + n)

    def reset_round(self) -> int:
        """新轮开始：行动力重置为每轮额度（3），返回重置后的值。"""
        self.action_points = self.ap_per_round
        return self.action_points

    # -------------------------------------------------------------- V3 结局
    @staticmethod
    def truth_coverage(clue_ids: list[str], truth: dict) -> float:
        """truth_node 覆盖度：已持线索命中的节点数 / 总节点数（Judge 打分依据）。"""
        nodes = truth.get("truth_nodes", [])
        if not nodes:
            return 0.0
        held = set(clue_ids)
        covered = sum(1 for n in nodes if held & set(n.get("proof_clues", [])))
        return round(covered / len(nodes), 2)

    def resolve_accusation(self, evidence_cards: list[dict], target_char: str,
                           truth: dict, counsel_count: int = 0) -> dict:
        """指认结算（表层真相）：≥2 张证据卡支撑才有效。

        返回 {valid, hit, coverage, grade, ending, title}。
        grade: perfect(≥90%) / partial(60-89%，<60% 亦归此档) / wrong。
        """
        # 证据卡必须是两张不同的卡；同一张卡重复提交不能绕过门槛。
        cards = [ev for ev in (evidence_cards or []) if isinstance(ev, dict)]
        unique_cards = []
        seen_cards = set()
        for ev in cards:
            card_key = ev.get("id") or tuple(sorted(set(ev.get("clue_ids", []))))
            if card_key in seen_cards:
                continue
            seen_cards.add(card_key)
            unique_cards.append(ev)
        clue_ids = []
        for ev in unique_cards:
            clue_ids.extend(ev.get("clue_ids", []))
        clue_ids = sorted(set(clue_ids))
        coverage = self.truth_coverage(clue_ids, truth)
        valid = len(unique_cards) >= 2
        hit = bool(valid) and target_char == truth.get("culprit", {}).get("character")

        if not hit:
            grade, ending = "wrong", "wrong"
        elif coverage >= 0.9:
            grade, ending = "perfect", "perfect_restoration"
        else:
            grade, ending = "partial", "truth_revealed"
        title, desc = ENDINGS[ending]
        reason = ("evidence_ready" if valid else "need_two_distinct_evidence_cards")
        return {"valid": valid, "hit": hit, "coverage": coverage, "grade": grade,
                "ending": ending, "title": title, "desc": desc,
                "counsel_count": counsel_count,
                "detail": {"evidence_count": len(evidence_cards or []),
                           "distinct_evidence_count": len(unique_cards),
                           "reason": reason,
                           "target": target_char,
                           "culprit": truth.get("culprit", {}).get("character", "")}}

    def resolve_boss_accusation(self, flaw_count: int, counsel_count: int = 0) -> dict:
        """指认 DM 分支（里层真相）：破绽 ≥5 才解锁「指认：DM」选项。

        破绽不足 → 群嘲结局「你连 DM 都想锤?」（欢乐向，不惩罚）；
        指认成功 + 心晴诊室 2+ → 终极结局「看山还是山」；
        指认成功但心晴不足 → 归「真相大白」（里层真相揭晓）。
        """
        if flaw_count < 5:
            title, desc = ENDINGS["dm_mock"]
            return {"allowed": False, "ending": "dm_mock", "title": title,
                    "desc": desc, "flaw_count": flaw_count}
        if counsel_count >= 2:
            title, desc = ENDINGS["kanshan_still_mountain"]
            return {"allowed": True, "ending": "kanshan_still_mountain", "title": title,
                    "desc": desc, "flaw_count": flaw_count}
        title, desc = ENDINGS["truth_revealed"]
        return {"allowed": True, "ending": "truth_revealed", "title": title,
                "desc": "里层真相揭晓：这一局的局，正是看山设的局（心晴诊室不足 2）",
                "flaw_count": flaw_count}

    def matrix_ending(self, *, accusation_hit: bool = False, coverage: float = 0.0,
                      boss_accused: bool = False, flaw_count: int = 0,
                      counsel_count: int = 0, plot_fragments: int = 0,
                      boss_key: bool = False, v587_exposed: bool = False,
                      defection: bool = False, pollution_heat: float = 0.0,
                      heat_threshold: float = 0.9, solo: bool = False) -> dict:
        """8+2 结局矩阵终裁（优先级从特殊到普通，确定性）。

        pollution_heat：热度带偏程度 0.0-1.0（OpinionFeed.heat_ratio()），
        ≥ heat_threshold 视为污染阵营把热度带偏至终局。
        solo：历史参数，保留以免破调用方。命中真凶不再因覆盖度不够打成 wrong。
        返回 {ending, title, desc, detail}。
        """
        _ = solo
        # 1) DM 分支优先（终极层最特殊）
        if boss_accused:
            if flaw_count < 5:
                ending = "dm_mock"
            elif counsel_count >= 2:
                ending = "kanshan_still_mountain"
            else:
                ending = "truth_revealed"
        # 2) 隐藏结局
        elif plot_fragments >= 5:
            ending = "deleted_chapter7"
        elif boss_key and v587_exposed:
            ending = "kanshan_fish"
        elif counsel_count >= 4:
            ending = "all_hearts_clear"
        # 3) 表层：≥2 证指认真凶至少「真相大白」，覆盖度只分完美档
        elif accusation_hit and coverage >= 0.9:
            ending = "perfect_restoration"
        elif accusation_hit:
            ending = "truth_revealed"
        elif defection:
            ending = "vindicated"
        elif pollution_heat >= heat_threshold:
            ending = "pollution_win"
        else:
            ending = "wrong"
        title, desc = ENDINGS[ending]
        return {"ending": ending, "title": title, "desc": desc,
                "detail": {"accusation_hit": accusation_hit, "coverage": coverage,
                           "boss_accused": boss_accused, "flaw_count": flaw_count,
                           "counsel_count": counsel_count,
                           "plot_fragments": plot_fragments, "boss_key": boss_key,
                           "v587_exposed": v587_exposed, "defection": defection,
                           "pollution_heat": pollution_heat}}

    # --------------------------------------------- P2 终局陈词 / 成就（MEGA §三）
    def achievements(self, *, boss_accused_success: bool = False,
                     counsel_count: int = 0, pollution_win: bool = False,
                     clues_collected: int = 0, clues_total: int = 0,
                     photos_shared: int = 0, refuted: int = 0,
                     listen_full: int = 0,
                     most_hammered: str | None = None,
                     hammered_is_self: bool = False,
                     clean_stealth_shots: int = 0,
                     hammered_votes: int = 0) -> list[str]:
        """成就徽章判定（确定性，MEGA_MODE §三 枚举 + D 成就库 v2 合并口径）。

        - clean_stealth_shots：干净暗拍数（CONTRACTS §3.5b stealth_photo_clean——
          photos_of(pid) 中非 fake 线索照片计数，数据源 EvidenceChain.clean_photo_counts()）
          ≥3 → 暗房大师；
        - listen_full ≥3 → 防折叠斗士（D 成就库 v2 口径：char_06 听全文）；
        - refuted ≥3 → 热搜质检员（G07 修正：原误判为防折叠斗士）；
        - hammered_votes：终局陈词「最想锤的人」被锤票数 ≥3（D v2：群嘲免死金牌
          并入全场公敌，判定类型不变）→ 全场公敌；most_hammered+hammered_is_self
          组合路径保留兼容。
        终局陈词锤票只影响群嘲类成就，不影响指认（GAMEPLAY_V31 §五）。
        """
        out = []
        if boss_accused_success:
            out.append("看山还是山")
        if counsel_count >= 4:
            out.append("心晴医师")
        if pollution_win:
            out.append("带节奏之王")
        if clues_total and clues_collected >= clues_total:
            out.append("鱼干守护者")
        if listen_full >= 3:
            out.append("防折叠斗士")
        if refuted >= 3:
            out.append("热搜质检员")
        if photos_shared >= 3 or clean_stealth_shots >= 3:
            out.append("暗房大师")
        if hammered_votes >= 3 or (most_hammered and hammered_is_self):
            out.append("全场公敌")
        return out
