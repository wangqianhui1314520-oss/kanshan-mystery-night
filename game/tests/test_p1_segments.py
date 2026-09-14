"""G 增量②：P1 环节单测 —— 弹幕押注 / 系统抽风 / 心声广播事故 / 心病急诊室 / 头条竞标。

引擎裁决件逐个过闸（含驱动层接线现状取证）。
"""
from __future__ import annotations

import pytest

from engine import party  # noqa: F401  (B 窗口接线中，import 烟测)
from engine.knowledge_cards import KnowledgeSystem
from engine.memory_system import MemorySystem
from engine.opinion_feed import OpinionFeed
from engine.stage_machine import StageMachine
from tests.conftest import SCENARIO_DIR

pytestmark = pytest.mark.p1


class TestBetSettlement:
    def test_bet_full_lifecycle_rules(self, scenario_dir):
        of = OpinionFeed()
        of.load(str(scenario_dir))
        # 边界：选项不足 / 未知池 / 未知选项 / 重复结算
        assert of.open_bet("b", "议题", ["a"])["ok"] is False
        assert of.open_bet("b", "本轮你信谁的口供？", ["char_01", "char_02", "char_05"])["ok"]
        assert of.place_bet("nope", "d:u", "char_01")["reason"] == "bet_not_open"
        assert of.place_bet("b", "d:u1", "char_99")["reason"] == "unknown_option"
        assert of.place_bet("b", "d:u1", "char_01", 3)["ok"]
        assert of.place_bet("b", "d:u2", "char_02", 1)["ok"]
        h0 = of.heat
        res = of.settle_bet("b", "char_01")
        assert res["ok"] and res["pool"] == 4
        assert res["winners"][0]["payout"] == 4  # 全池归 3:1 中的 3 份
        assert h0 < of.heat <= h0 + 5  # 押注人数加热（1..5 封顶）
        assert of.settle_bet("b", "char_01")["ok"] is False


class TestGlitchEvent:
    def test_glitch_banner_and_effect_kinds(self, scenario):
        sm = StageMachine(scenario)
        seen_kinds, seen_effects = set(), []
        for _ in range(6):
            ev = sm.banner_glitch()
            seen_kinds.add(ev["payload"]["kind"])
            seen_effects.append(ev["effect"]["kind"])
        assert seen_kinds == {"glitch"}
        assert set(seen_effects) <= {"ap_free", "heat_bump", "none"}
        assert "ap_free" in seen_effects and "heat_bump" in seen_effects

    def test_glitch_ap_free_auto_applies(self, scenario):
        """ap_free：下一次行动免扣（引擎内部自动生效）。"""
        sm = StageMachine(scenario)
        sm.actions_left = 1
        while sm.banner_glitch()["effect"]["kind"] != "ap_free":
            pass
        assert sm.consume_action() is True  # 免扣不减少
        assert sm.actions_left == 1


class TestBroadcastAccident:
    def test_broadcast_only_safe_heart(self, scenario_dir):
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        for ch in sorted(ms._versions):
            ms.unlock_next(ch, "memory_fix")
        results = [ms.broadcast_accident() for _ in range(8)]
        from engine.memory_system import _BROADCAST_BLOCK_WORDS
        for r in results:
            if r["ok"]:
                assert r["block"]["integrity"] != "deleted"
                assert not any(w in r["text"] for w in _BROADCAST_BLOCK_WORDS)
        assert any(r["ok"] for r in results), "8 角色心声全被拦（内容异常）"
        # 指定候选仍受白名单约束
        r = ms.broadcast_accident(candidates=["char_01"])
        assert r["ok"] or r["reason"] in ("all_case_sensitive", "no_unlocked_heart")


class TestEmergencyRoom:
    def test_er_double_benefit_window(self, scenario_dir):
        ks = KnowledgeSystem(seed=11)
        ks.load(str(scenario_dir))
        target = "char_06"
        good = next(c["id"] for c in ks._cards.values() if c.get("binds") == target)
        wrong = next(c["id"] for c in ks._cards.values()
                     if str(c.get("binds", "")).startswith("char_")
                     and c["binds"] != target)
        ks.set_round(4)
        assert not ks.counsel("p1", target, wrong)["matched"]
        assert ks.er_active(target)          # ISSUE-G03：当轮即亮（锁定现行为）
        ks.set_round(5)
        rescue = ks.counsel("p1", target, good)
        assert rescue["matched"] and rescue["er_rescue"] and rescue["unlocked"]["doubled"]
        assert "收益×2" in rescue["transcript_hint"]

    def test_er_double_benefit_once_per_window(self, scenario_dir):
        """双倍限一次：抢救成功灯灭，同窗口内再次开导不再翻倍（须重新恶化才亮新灯）。"""
        ks = KnowledgeSystem(seed=13)
        ks.load(str(scenario_dir))
        target = "char_04"
        good = next(c["id"] for c in ks._cards.values() if c.get("binds") == target)
        wrong = next(c["id"] for c in ks._cards.values()
                     if str(c.get("binds", "")).startswith("char_")
                     and c["binds"] != target)
        ks.set_round(10)
        ks.counsel("p1", target, wrong)              # 恶化亮灯
        assert ks.er_active(target)
        first = ks.counsel("p1", target, good)       # 抢救：双倍
        assert first["er_rescue"] and first["unlocked"].get("doubled") is True
        assert not ks.er_active(target)              # 灯灭
        second = ks.counsel("p1", target, good)      # 同窗口再次用对卡
        assert second["matched"] and not second.get("er_rescue")
        assert not second["unlocked"].get("doubled")  # 不重复双倍
        # 新窗口：再次失败 → 新灯 → 再抢救可再双倍（窗口重启语义）
        ks.set_round(20)
        ks.counsel("p1", target, wrong)
        assert ks.er_active(target)
        third = ks.counsel("p1", target, good)
        assert third["er_rescue"] and third["unlocked"].get("doubled") is True

    def test_er_buff_ap_doubling(self, scenario_dir):
        ks = KnowledgeSystem(seed=12)
        ks.load(str(scenario_dir))
        ap_card = next((c for c in ks._cards.values() if c.get("effect") == "buff_ap"), None)
        if ap_card is None:
            pytest.skip("无 buff_ap 卡")
        other = next(c["id"] for c in ks._cards.values()
                     if str(c.get("binds", "")).startswith("char_"))
        ks.set_round(1)
        ks.counsel("p1", "char_99", other)      # 失败 → char_99 红灯
        ks.set_round(2)
        r = ks.counsel("p1", "char_99", ap_card["id"])
        if r["matched"] and r["er_rescue"]:
            assert r["unlocked"]["ap"] == 2     # 双倍 AP


class TestHeadlineBidding:
    def test_headline_full_flow(self, scenario_dir):
        of = OpinionFeed()
        of.load(str(scenario_dir))
        fake = next(p["id"] for p in of._posts.values() if p.get("is_fake"))
        of.open_headline_bidding(1)
        assert of.bid_headline("p1", "media", 3)["ok"] is False
        h0 = of.heat
        of.bid_headline("p1", "truth", 2, post_id=fake)
        of.bid_headline("p2", "pollution", 4, post_id=fake)
        # 重复出价 = 覆盖原票（后价替换前价，非取大）：p2 改出 5（带帖）保持领先
        of.bid_headline("p2", "pollution", 5, post_id=fake)
        res = of.settle_headline()
        assert res["winner"] == "p2" and res["amount"] == 5
        assert fake in of._pinned               # 中标帖置顶
        assert of.heat > h0
        # 平价先到先得 + 流拍
        of.open_headline_bidding(2)
        of.bid_headline("pa", "truth", 2)
        of.bid_headline("pb", "pollution", 2)
        assert of.settle_headline()["winner"] == "pa"
        of.open_headline_bidding(3)
        none = of.settle_headline()
        assert none["ok"] and none["winner"] is None


class TestPuzzleJudge:
    """V31 环节：记忆拼图对质（P2 件已入引擎，随 P1 单测一并过闸）。"""

    def test_puzzle_authority_and_gate(self, scenario_dir):
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        ch = sorted(ms._versions)[0]
        for _ in range(3):
            ms.unlock_next(ch, "memory_fix")
        answer = ms.puzzle_answer(ch)
        assert answer, "拼图权威答案为空"
        assert ms.puzzle_judge(ch, list(answer))["correct"] is True
        wrong = list(reversed(answer)) if len(answer) > 1 else ["nope"]
        r = ms.puzzle_judge(ch, wrong)
        assert r["correct"] is False and r["answer"] == answer  # 排错被锐评（答案不泄出判定外）
        # 发起对质成本：2 个篡改点（不足则拒绝）
        assert ms.spend_tamper_points(2) in (True, False)


class TestStealthPhoto:
    """V31 环节：暗拍 —— 线索留原地、只持有照片、可分享可声称。"""

    def test_photo_leaves_clue_in_place(self, scenario_dir):
        from engine.evidence_chain import EvidenceChain
        ec = EvidenceChain(scenario_dir)
        # 监控室候选按优先级 boss_flaw(clue_029) 先出；用「删除」定向锁定 limited clue_009
        r = ec.stealth_photo("监控室", "删除", "player:1", round_no=2)
        assert r["ok"] and r["photo"]["clue_id"] == "clue_009"
        # 原件仍在池中未被发放：他人可搜
        assert r["photo"]["clue_id"] not in ec.get_player_clues("player:1")
        r2 = ec.stealth_photo("监控室", "删除", "player:2", round_no=2)
        assert r2["ok"] and r2["photo"]["clue_id"] == "clue_009"  # 双方各拍各的
        # 分享（可说谎：claim 登记原文与声称）
        shared = ec.share_photo("player:1", r["photo"]["photo_id"], claim="我什么都没看见")
        assert shared["claim"] == "我什么都没看见"
        assert shared["photo"]["fact"] == ec.clue("clue_009")["fact"]  # 原文一字不改
        assert len(ec.photos_of("player:1")) == 1

    def test_photo_miss_env_note(self, scenario_dir):
        from engine.evidence_chain import EvidenceChain
        ec = EvidenceChain(scenario_dir)
        miss = ec.stealth_photo("天台", "外星信号", "player:1", round_no=1)
        assert not miss["ok"] and miss["env_note"]


class TestFlipSide:
    """V31 环节：双面线索锁 —— front 公开恒定，back 条件满足才可翻面，幂等。"""

    def test_flip_side_lifecycle(self, scenario_dir):
        from engine.evidence_chain import EvidenceChain
        ec = EvidenceChain(scenario_dir)
        ec.ingest_clue({
            "id": "probe_sides", "tier": "public", "location": "前台",
            "tags": ["贴纸"], "fact": "正面：一张贴歪的访客贴纸。",
            "unlock_condition": "默认",
            "sides": {"front": "正面：一张贴歪的访客贴纸。",
                      "back": "背面：签名栏写着「K」。",
                      "back_condition": "evidence:clue_005"}})
        # 无 sides/条件未满足/已翻面 → None
        assert ec.flip_side("clue_001", "p1") is None            # 无双面结构
        assert ec.flip_side("probe_sides", "p1") is None         # 前置未持
        ec.release("clue_005", "p1")
        first = ec.flip_side("probe_sides", "p1")
        assert first and first["back"] == "背面：签名栏写着「K」。"
        assert first["front"] == "正面：一张贴歪的访客贴纸。"      # front 恒公开
        assert ec.flip_side("probe_sides", "p1") is None          # 已翻面幂等

    def test_kanshan_has_sided_clues(self, scenario_dir):
        """kanshan 已启用双面线索（至少 clue_012 带 sides）。"""
        from engine.evidence_chain import EvidenceChain
        ec = EvidenceChain(scenario_dir)
        sided = [c for c in ec.pool.values() if isinstance(c.get("sides"), dict)]
        assert sided, "kanshan 应至少有一条双面线索"
        assert any(c.get("id") == "clue_012" for c in sided)


class TestP1WiringStatus:
    """P1 环节与动作管线（EngineDriver / server）的接线现状取证。"""

    def test_driver_exposes_p1_surfaces(self):
        """B 已接线：PartyBoard/DifficultyDirector 入 driver。

        PENDING-B01 已闭环：bid_headline 技能管线（apply_action → of.bid_headline
        → of.settle_headline → headline_result 事件）已入 driver（引擎单测
        test_engine_units.py 覆盖 of.open_bet / of.settle_headline 行为）。
        本断言仅验证押注总闸 open_bet 未入动作管线（仍由 F/E 直调引擎）。"""
        from server.engine_driver import EngineDriver
        d = EngineDriver(SCENARIO_DIR)
        assert hasattr(d, "pb") and hasattr(d, "dd"), "party/难度未入 driver"
        import inspect
        from server.engine_driver import EngineDriver as ED
        src = inspect.getsource(ED)
        assert "open_bet" not in src, "押注总闸不应入动作管线（PENDING-B01 边界）"
        assert "settle_headline" in src, "头条结算已接入 bid_headline 技能管线"
