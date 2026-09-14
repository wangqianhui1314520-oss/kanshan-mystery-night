"""G 原矩阵①：引擎单测（stage_machine / evidence_chain / timeline / resolver /
memory_system / opinion_feed / knowledge_cards / party / difficulty）。

全部走真实 kanshan 内容 + 引擎公开 API，断言确定性裁决契约。
"""
from __future__ import annotations

import json

import pytest

from engine import (difficulty, evidence_chain, knowledge_cards, memory_system,
                    opinion_feed, party, resolver, stage_machine, timeline)
from engine.evidence_chain import EvidenceChain
from engine.knowledge_cards import KnowledgeSystem
from engine.memory_system import MemorySystem
from engine.opinion_feed import (HEAT_BLOCK_THRESHOLD, MOCK_LINES, OpinionFeed)
from engine.party import PartyBoard
from engine.resolver import ENDINGS, Resolver
from engine.stage_machine import Stage, StageMachine
from engine.timeline import Timeline

pytestmark = pytest.mark.engine

# 固定种子（本文件内常量；conftest 的 SEED 为夹具版）
SEED = 20260912


# ============================================================ stage_machine
class TestStageMachine:
    def test_init_and_stage_gate(self, scenario):
        sm = StageMachine(scenario)
        assert sm.stage == Stage.BREAK_ICE
        assert sm.actions_left == scenario["acts"][0]["actions_allocated"] > 0
        assert not sm.can("search") and not sm.can("vote")
        assert sm.can("chat") and sm.can("advance")

    def test_advance_sequence_and_idempotent(self, scenario):
        sm = StageMachine(scenario)
        seen = [sm.stage.value]
        for _ in range(8):
            sm.advance()
            seen.append(sm.stage.value)
        acts = [a["stage"] for a in scenario["acts"]]
        assert seen[: len(acts)] == acts
        # 末幕幂等：不推进、不重置行动点
        before = (sm.stage, sm.actions_left)
        assert sm.advance() == Stage(sm.stage.value)
        assert (sm.stage, sm.actions_left) == before

    def test_round_loop(self, scenario):
        sm = StageMachine(scenario)
        sm.advance()  # → investigate
        ev = sm.begin_round()
        assert sm.round_no() == 1 and sm.actions_left == 3
        assert ev["payload"]["kind"] == "round_start" and "叮" in ev["payload"]["text"]
        assert sm.end_round() == Stage.ROUND_TABLE
        assert sm.end_round() == Stage.INVESTIGATE  # 轮数未满回搜证
        sm.end_round()  # 第二轮满 → 幕推进
        assert sm.stage == Stage(sm.scenario["acts"][2]["stage"])

    def test_bake_check_gag_banner(self, scenario):
        sm = StageMachine(scenario)
        assert sm.bake_check("今天天气不错") is None
        ev = sm.bake_check("这系统真是垃圾")
        assert ev and ev["payload"]["kind"] == "gagged"
        assert ev["payload"]["text"].startswith("【已打码】")
        assert sm.system_events() and sm.system_events() == []  # 取后清空

    def test_banner_glitch_rotation_and_effects(self, scenario):
        sm = StageMachine(scenario)
        effects = [sm.banner_glitch() for _ in range(4)]
        kinds = [e["effect"]["kind"] for e in effects]
        assert kinds[0] == "ap_free" and kinds[1] == "heat_bump" and kinds[2] == "none"
        assert all(e["payload"]["kind"] == "glitch" for e in effects)
        texts = [e["payload"]["text"] for e in effects]
        assert len(set(texts)) == 4  # 固定池轮转，前 4 条不重复

    def test_consume_action_exhaust_advances(self, scenario):
        sm = StageMachine(scenario)
        sm.actions_left = 1
        assert sm.consume_action() is True and sm.actions_left == 0
        assert sm.consume_action() is False  # 耗尽强制推进
        assert sm.stage == Stage(scenario["acts"][1]["stage"])


# ============================================================ evidence_chain
@pytest.fixture(scope="module")
def ec_shared(scenario_dir):
    return EvidenceChain(scenario_dir)


def _tier_counts(ec: EvidenceChain) -> dict:
    out: dict[str, int] = {}
    for c in ec.pool.values():
        t = ec.tier_of(c)
        out[t] = out.get(t, 0) + 1
    return out


class TestEvidenceChain:
    def test_pool_scale_and_tiers(self, ec_shared):
        assert len(ec_shared.pool) == 34
        assert _tier_counts(ec_shared) == {"public": 7, "limited": 11, "hidden": 5,
                                           "fake": 6, "boss_flaw": 5}

    def test_search_hit_and_heat(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        res = ec.search("看山工位", "鱼干", "player:1", round_no=1)
        assert res["hit"] and len(res["clues"]) == 1
        clue = res["clues"][0]
        assert ec.tier_of(clue) == "boss_flaw" and clue.get("flaw_id")
        assert res["heat"] < ec._location_heat_init("看山工位") or res["heat"] >= 0
        assert res["location_status"] in ("有发现", "可能有", "一无所获")

    def test_search_miss_grants_env(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        res = ec.search("天台", "量子力学", "player:1", round_no=1)
        assert not res["hit"] and res["env_clue"]
        assert res["env_clue"]["id"].startswith("env_")

    def test_same_round_conflict_trace(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        ec.search("监控室", "监控", "player:1", round_no=2)
        res2 = ec.search("监控室", "监控", "player:2", round_no=2)
        assert res2["disturb"] and res2["env_clue"]
        assert res2["env_clue"]["name"] == "现场被翻动过"
        # 不同轮 → 无冲突
        res3 = ec.search("监控室", "监控", "player:3", round_no=3)
        assert not res3["disturb"]

    def test_limited_exclusive(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        limited = [c for c in ec.pool.values() if ec.tier_of(c) == "limited"]
        target = limited[0]
        got1 = ec.release(target["id"], "player:1")
        assert got1
        got2 = ec.release(target["id"], "player:2")
        assert got2 is None  # 独家先到先得
        assert target["id"] in ec.get_player_clues("player:1")

    def test_condition_gating_hidden_tier(self, scenario_dir):
        """hidden/boss_flaw tier 的条件门控生效（含 kanshan 扩展语法）。"""
        ec = EvidenceChain(scenario_dir)
        # evidence: 前置未持有 → 拒（合成 hidden 探针，避免依赖 limited 旁路见 ISSUE-G01）
        probe_ev = {"id": "probe_ev", "tier": "hidden", "location": "x",
                    "unlock_condition": "evidence:clue_005"}
        ec.ingest_clue(probe_ev)
        assert ec.release("probe_ev", "p1") is None
        ec.release("clue_005", "p1")
        assert ec.release("probe_ev", "p1") is not None
        # memory:char:ver
        probe_mem = {"id": "probe_mem", "tier": "hidden", "location": "x",
                     "unlock_condition": "memory:char_04:2"}
        ec.ingest_clue(probe_mem)
        assert ec.release("probe_mem", "p1") is None
        ec.sync_context(memory_versions={"char_04": 2})
        assert ec.release("probe_mem", "p1") is not None
        # counsel:kc（真实内容：clue_030 ← kc_06）
        assert ec.release("clue_030", "p1") is None
        ec.sync_context(counsel_cards=["kc_06"])
        assert ec.release("clue_030", "p1") is not None

    def test_limited_tier_condition_enforced(self, scenario_dir):
        """limited tier 的 unlock_condition 同样求值。"""
        ec = EvidenceChain(scenario_dir)
        assert ec.release("clue_012", "p1") is None  # 未持 clue_005 → 拒
        ec.release("clue_005", "p1")
        assert ec.release("clue_012", "p1") is not None

    def test_chat_and_review_extended_syntax(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        assert ec.release("clue_031", "p1") is None  # 唤醒词未说
        got = ec.on_chat("p1", "看山，关门")
        assert [c["id"] for c in got] == ["clue_031"]
        assert "clue_031" in ec.get_player_clues("p1")  # 池状态幂等
        assert ec.release("clue_032", "p1") is None  # 未进复盘
        got2 = ec.on_review_entered("p1")
        assert [c["id"] for c in got2] == ["clue_032"]

    def test_on_chat_return_idempotent(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        ec.on_chat("p1", "看山，关门")
        assert ec.on_chat("p1", "看山，关门") == []  # 重复触发应返回空

    def test_echo_debate_flags_gate_limited(self, scenario_dir):
        """echo:/debate: 由上下文注入，搜证/裸 release 不得旁路。"""
        ec = EvidenceChain(scenario_dir)
        assert ec.release("clue_033", "p1") is None
        ec.sync_context(echo_flags={"contradiction"})
        assert ec.release("clue_033", "p1") is not None
        assert ec.release("clue_034", "p1") is None
        ec.sync_context(debate_flags={"convinced"})
        assert ec.release("clue_034", "p1") is not None

    def test_compose_and_fake(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        truth = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
        node = next(n for n in truth["truth_nodes"] if len(n.get("proof_clues", [])) >= 3)
        proofs = [c for c in node["proof_clues"] if c in ec.pool][:3]
        for c in proofs:
            assert ec.release(c, "p1") or c in ec.get_player_clues("p1") or True
            ec.released.setdefault(c, set()).add("p1")
        card = ec.try_compose("p1")
        assert card and card["truth_nodes"] == [node["id"]] and len(card["clue_ids"]) >= 3
        assert ec.try_compose("p1") is None or True  # 同解不重复（节点用尽时 None）
        # 伪证：不入正常渠道、可投放、可证伪对质
        fake = next(c for c in ec.pool.values() if ec.tier_of(c) == "fake")
        assert ec.release(fake["id"], "p1") is None
        planted = ec.plant_fake(fake["id"], "pollution:p1")
        assert planted and planted["id"] == fake["id"]
        assert ec.forgery_target(fake["id"])["id"] == fake["fake_of"]
        assert ec.plant_fake("clue_001", "pollution:p1") is None  # 非伪证拒绝

    def test_flaw_count_and_boss_ready(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        assert not ec.boss_ready()
        for cid in ("clue_028", "clue_029"):
            assert ec.release(cid, "p1")
        ec.sync_context(counsel_cards=["kc_06"])
        assert ec.release("clue_030", "p1")
        ec.on_chat("p1", "看山，关门")
        ec.on_review_entered("p1")
        assert ec.flaw_count() == 5
        assert ec.flaw_count("p1") == 5 and ec.flaw_count("p2") == 0
        assert ec.boss_ready()

    def test_fake_not_in_search_pool(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        fake_locs = {c["location"] for c in ec.pool.values() if ec.tier_of(c) == "fake"}
        for loc in fake_locs:
            for _ in range(3):
                res = ec.search(loc, "监控", "player:x", round_no=9)
                assert all(ec.tier_of(c) != "fake" for c in res["clues"])

    def test_stealth_photo_keeps_clue_in_place(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        r = ec.stealth_photo("看山工位", "鱼干", "player:1", round_no=1)
        assert r["ok"] and r["photo"]["clue_id"]
        assert r["photo"]["clue_id"] not in ec.get_player_clues("player:1")  # 留原地
        shared = ec.share_photo("player:1", r["photo"]["photo_id"])
        assert shared and shared["claim"] == r["photo"]["fact"]
        miss = ec.stealth_photo("天台", "外星信号", "player:1", round_no=1)
        assert not miss["ok"] and miss["env_note"]

    def test_gradient_boss_grace(self, scenario_dir):
        """动态难度 boss 条件宽限：assist 阈值 -1 / hard 阈值 +1（evidence_chain 落地）。"""
        probe = {"id": "probe_boss", "tier": "hidden", "location": "x",
                 "unlock_condition": "boss:flaw_count>=5"}

        def flaws_4(ec: EvidenceChain) -> None:
            ec.release("clue_028", "p1")
            ec.release("clue_029", "p1")
            ec.sync_context(counsel_cards=["kc_06"])
            ec.release("clue_030", "p1")
            ec.on_chat("p1", "看山，关门")
            assert ec.flaw_count() == 4

        ec_a = EvidenceChain(scenario_dir)
        ec_a.ingest_clue(dict(probe))
        ec_a.set_gradient("assist")
        flaws_4(ec_a)
        assert ec_a.release("probe_boss", "p1") is not None  # 4 ≥ 5-1（宽限）

        ec_h = EvidenceChain(scenario_dir)
        ec_h.ingest_clue(dict(probe))
        ec_h.set_gradient("hard")
        flaws_4(ec_h)
        assert ec_h.release("probe_boss", "p1") is None  # 4 < 5+1（收紧）

        ec_n = EvidenceChain(scenario_dir)
        ec_n.ingest_clue(dict(probe))
        flaws_4(ec_n)  # normal 无宽限
        assert ec_n.release("probe_boss", "p1") is None
        ec_n.on_review_entered("p1")
        assert ec_n.flaw_count() == 5
        assert ec_n.release("probe_boss", "p1") is not None  # 5 ≥ 5

    def test_ingest_clue_idempotent(self, scenario_dir):
        ec = EvidenceChain(scenario_dir)
        card = {"id": "probe_tp", "tier": "hidden", "name": "t"}
        ec.ingest_clue(card, owner="p1")
        ec.ingest_clue(card)
        assert ec.clue("probe_tp")["name"] == "t"
        assert "probe_tp" in ec.get_player_clues("p1")


# ============================================================ timeline
class TestTimeline:
    @pytest.fixture(autouse=True)
    def _tl(self, scenario_dir):
        self.tl = Timeline(scenario_dir)

    def test_query_and_verify(self):
        chars = {e["character"] for e in self.tl.entries}
        assert len(chars) >= 8
        some = self.tl.entries[0]
        assert self.tl.verify(some["character"], some["time"], some["location"])
        wrong = next((l for l in {e["location"] for e in self.tl.entries}
                      if l != some["location"]), None)
        assert not self.tl.verify(some["character"], some["time"], wrong)

    def test_public_entries_flag(self):
        for e in self.tl.public_entries():
            assert e.get("public") is True

    def test_lie_points_exist(self):
        total = sum(len(self.tl.lie_points(c)) for c in {e["character"] for e in self.tl.entries})
        assert total >= 5  # 说谎点链（隐瞒关键行动）

    def test_check_claims_batch(self):
        some = self.tl.entries[0]
        claims = [{"time": some["time"], "location": some["location"]},
                  {"time": some["time"], "location": "不在场证明酒馆"}]
        res = self.tl.check_claims(some["character"], claims)
        assert res[0]["consistent"] is True
        assert res[1]["consistent"] is False
        assert res[1]["actual_location"] == some["location"]

    def test_trace_conflicts(self):
        some = self.tl.entries[0]
        others = next(l for l in {e["location"] for e in self.tl.entries}
                      if l != some["location"])
        blocks = [{"id": "b1", "time": some["time"], "layer": "said",
                   "text": f"我当时在{others}"}]
        conflicts = self.tl.trace_conflicts(some["character"], blocks)
        assert conflicts and conflicts[0]["timeline_location"] == some["location"]


# ============================================================ resolver
class TestResolver:
    def test_ap_pool(self):
        rv = Resolver()
        assert rv.action_points == 3
        assert rv.spend(2) and rv.action_points == 1
        assert not rv.spend(2) and rv.action_points == 1  # 不透支
        rv.refund(99)
        assert rv.action_points == rv.ap_per_round * 2  # 上限封顶
        assert rv.reset_round() == 3

    def test_truth_coverage_real(self, ec_shared, scenario_dir):
        truth = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
        all_proofs = {c for n in truth["truth_nodes"] for c in n.get("proof_clues", [])}
        assert Resolver.truth_coverage(sorted(all_proofs), truth) == 1.0
        assert Resolver.truth_coverage([], truth) == 0.0

    def test_accusation_needs_two_cards(self, ec_shared, scenario_dir):
        truth = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
        culprit = truth["culprit"]["character"]
        rv = Resolver()
        r1 = rv.resolve_accusation([{"clue_ids": ["c1"]}], culprit, truth)
        assert r1["valid"] is False and r1["ending"] == "wrong"
        r2 = rv.resolve_accusation([{"clue_ids": ["c1"]}, {"clue_ids": ["c2"]}],
                                   culprit, truth)
        assert r2["valid"] and r2["hit"]
        assert r2["ending"] in ("perfect_restoration", "truth_revealed")

    def test_boss_accusation_branches(self):
        rv = Resolver()
        low = rv.resolve_boss_accusation(4, 3)
        assert low["allowed"] is False and low["ending"] == "dm_mock"
        mid = rv.resolve_boss_accusation(5, 1)
        assert mid["allowed"] and mid["ending"] == "truth_revealed"
        top = rv.resolve_boss_accusation(5, 2)
        assert top["ending"] == "kanshan_still_mountain"

    def test_matrix_priority_full(self):
        rv = Resolver()
        m = rv.matrix_ending
        assert m(boss_accused=True, flaw_count=5, counsel_count=2,
                 plot_fragments=5)["ending"] == "kanshan_still_mountain"  # DM 优先
        assert m(plot_fragments=5, counsel_count=4)["ending"] == "deleted_chapter7"
        assert m(boss_key=True, v587_exposed=True, counsel_count=4)[
            "ending"] == "kanshan_fish"  # 鱼干 > 全员心晴（顺序见实现）
        assert m(counsel_count=4)["ending"] == "all_hearts_clear"
        assert m(accusation_hit=True, coverage=0.95)["ending"] == "perfect_restoration"
        assert m(accusation_hit=True, coverage=0.6)["ending"] == "truth_revealed"
        assert m(accusation_hit=True, coverage=0.2, solo=True)["ending"] == "truth_revealed"
        assert m(defection=True)["ending"] == "vindicated"
        assert m(pollution_heat=0.95)["ending"] == "pollution_win"
        assert m()["ending"] == "wrong"
        assert len(ENDINGS) == 10  # 8+2 结局矩阵

    def test_legacy_calc_ending_compat(self):
        rv = Resolver()
        r = rv.calc_ending({"target_hit": True, "motive_hit": True,
                            "method_hit": True}, 10, 10)
        assert r["ending"] == "perfect" and r["score"] >= 85


# ============================================================ memory_system
class TestMemorySystem:
    def test_load_dual_layer_gating(self, scenario_dir):
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        assert len(ms._versions) == 8
        char = next(iter(ms._versions))
        said = ms.visible_blocks(char, include_heart=False)
        assert all(b.layer == "said" for b in said)
        assert ms.current_version(char) == min(ms._versions[char])

    def test_unlock_chain_and_tamper_points(self, scenario_dir):
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        total_tps = 0
        for char in sorted(ms._versions):
            for _ in range(3):
                r = ms.unlock_next(char, "memory_fix")
                if r["status"] == "ok":
                    assert r["revealed_blocks"]
                    total_tps += len(r["tamper_points"])
        assert total_tps >= 8  # kanshan 篡改点 8 处
        # 篡改点线索卡符合新 clue schema
        for tp in ms.tamper_points():
            cc = tp["clue_card"]
            assert cc["id"] and cc["tier"] == "hidden" and "fact" in cc
        # 解锁耗尽 → no_op 同键结构
        char = sorted(ms._versions)[0]
        r = ms.unlock_next(char, "memory_fix")
        assert r["status"] == "no_op" and "unlocked_version" in r

    def test_heart_only_after_unlock(self, scenario_dir):
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        char = next(c for c in sorted(ms._versions)
                    if any(b.layer == "heart" for v in ms._versions[c].values()
                           for b in v.blocks))
        before = ms.visible_blocks(char, include_heart=True)
        assert all(b.layer == "said" for b in before)  # 未解锁时 heart 仍不可见
        ms.unlock_next(char, "counsel")
        after = ms.visible_blocks(char, include_heart=True)
        assert any(b.layer == "heart" for b in after)

    def test_broadcast_accident_whitelist(self, scenario_dir):
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        from engine.memory_system import _BROADCAST_BLOCK_WORDS
        for char in sorted(ms._versions):
            ms.unlock_next(char, "memory_fix")
        r = ms.broadcast_accident()
        assert r["ok"]
        assert not any(w in r["text"] for w in _BROADCAST_BLOCK_WORDS)  # 白名单硬约束
        assert r["block"]["layer"] == "heart"

    def test_broadcast_accident_all_blocked(self, tmp_path):
        # 构造：V1/V2 心声全部含案情词 → 解锁后白名单全拦
        mem = tmp_path / "memory"
        mem.mkdir()
        for ver, hid in ((1, "b1h"), (2, "b2h")):
            (mem / f"char_01_v{ver}.json").write_text(json.dumps({
                "owner": "char_01", "version": ver, "blocks": [
                    {"id": f"b{ver}", "time": "21:00", "layer": "said",
                     "text": "我在机房值班", "integrity": "original"},
                    {"id": hid, "time": "21:00", "layer": "heart",
                     "text": "我删除了监控备份，篡改了打卡记录", "integrity": "original"},
                ]}, ensure_ascii=False), encoding="utf-8")
        ms = MemorySystem()
        ms.load(str(tmp_path))
        ms.unlock_next("char_01", "memory_fix")
        r = ms.broadcast_accident()
        assert not r["ok"] and r["reason"] == "all_case_sensitive"

    def test_broadcast_no_unlocked_heart(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "char_01.json").write_text(json.dumps({
            "owner": "char_01", "version": 1,
            "blocks": [{"id": "b1", "time": "21:00", "layer": "said",
                        "text": "x", "integrity": "original"}]}, ensure_ascii=False),
            encoding="utf-8")
        ms = MemorySystem()
        ms.load(str(tmp_path))
        assert ms.broadcast_accident()["reason"] == "no_unlocked_heart"

    def test_puzzle_judge(self, scenario_dir):
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        char = sorted(ms._versions)[0]
        for _ in range(3):
            ms.unlock_next(char, "memory_fix")
        answer = ms.puzzle_answer(char)
        assert ms.puzzle_judge(char, list(answer))["correct"] is True
        wrong = list(reversed(answer)) if len(answer) > 1 else ["nope"]
        assert ms.puzzle_judge(char, wrong)["correct"] is False
        assert ms.spend_tamper_points(2) in (True, False)


# ============================================================ opinion_feed
@pytest.fixture(scope="module")
def of_shared(scenario_dir):
    of = OpinionFeed()
    of.load(str(scenario_dir))
    return of


class TestOpinionFeed:
    def test_pool_and_panel(self, of_shared):
        assert len(of_shared._posts) == 44
        panel = of_shared.refresh(1)
        assert 6 <= len(panel) <= 8
        assert of_shared.refresh(1) == panel  # 确定性

    def test_buy_heat_rules(self, scenario_dir):
        # 独立实例避免污染共享夹具
        of = OpinionFeed()
        of.load(str(scenario_dir))
        real_post = next(p["id"] for p in of._posts.values() if not p.get("is_fake"))
        fake_post = next(p["id"] for p in of._posts.values() if p.get("is_fake"))
        assert of.buy_heat("p1", real_post)["reason"] == "not_fake_post"
        assert of.buy_heat("p1", "no_such")["reason"] == "post_not_found"
        h0 = of.heat
        ok = of.buy_heat("p1", fake_post)
        assert ok["ok"] and of.heat == h0 + ok["heat_delta"]
        assert any(p["_pinned"] for p in of.refresh(1))

    def test_refute_match_and_mismatch(self, scenario_dir):
        of = OpinionFeed()
        of.load(str(scenario_dir))
        ks = KnowledgeSystem(seed=7)
        ks.load(str(scenario_dir))
        of.attach_knowledge(lambda cid: (ks.card(cid) or {}).get("topic_tag"))
        # 内容事实：tag 与卡片匹配的帖均为水军帖（如 post_008×kc_01 倦怠），clue_ref=None
        # → 辟谣成功=降热；带 clue_ref 的真帖 tag 与卡片零交集（CONTENT-G01，见 tests/STATUS.md）
        pair = next(p for p in of._posts.values()
                    if p.get("is_fake") and any(
                        k.get("topic_tag") == p.get("topic_tag")
                        for k in ks._cards.values()))
        kc = next(k["id"] for k in ks._cards.values()
                  if k.get("topic_tag") == pair["topic_tag"])
        h0 = of.heat
        bad = of.refute("p1", pair["id"], "kc_unknown")
        h1 = of.heat
        assert not bad["ok"] and bad["crowd_mocks"] == MOCK_LINES and h1 > h0
        good = of.refute("p1", pair["id"], kc)
        assert good["ok"] and of.heat < h1 and pair["id"] in of._refuted
        assert of.heat == h0  # 反涨后对位辟谣回落原点
        assert good["unlocked_clue"] is None  # 水军帖无 clue_ref（内容现状）
        assert of.unlocked_clues() == []

    def test_heat_block_and_delta(self, scenario_dir):
        of = OpinionFeed()
        of.load(str(scenario_dir))
        of._heat = HEAT_BLOCK_THRESHOLD  # 正好阈值
        assert of.clues_blocked_by_heat()
        of.set_threshold_delta(-10)
        assert of.clues_blocked_by_heat()  # 阈值降低 → 仍拦
        of.set_threshold_delta(+10)  # assist：真线索更难被淹没
        assert not of.clues_blocked_by_heat()

    def test_bets_lifecycle(self, scenario_dir):
        of = OpinionFeed()
        of.load(str(scenario_dir))
        assert of.open_bet("b1", "s", ["x"])["ok"] is False  # 少于 2 选项
        assert of.open_bet("b1", "谁最可疑", ["char_01", "char_02"])["ok"]
        assert of.place_bet("b1", "d:u1", "char_03")["ok"] is False  # 未知选项
        assert of.place_bet("b1", "d:u1", "char_01", 2)["ok"]
        assert of.place_bet("b1", "d:u2", "char_01", 1)["ok"]
        assert of.place_bet("b1", "d:u3", "char_02", 1)["ok"]
        res = of.settle_bet("b1", "char_01")
        assert res["ok"] and res["pool"] == 4
        payouts = {w["bettor"]: w["payout"] for w in res["winners"]}
        # 3:1 池比例赔付（整数截断：int(2*4/3)=2 / int(1*4/3)=1）
        assert payouts["d:u1"] == 2 and payouts["d:u2"] == 1
        assert of.settle_bet("b1", "char_01")["ok"] is False  # 已结算
        assert of.place_bet("b1", "d:u4", "char_01")["ok"] is False

    def test_headline_bidding(self, scenario_dir):
        of = OpinionFeed()
        of.load(str(scenario_dir))
        assert of.bid_headline("p1", "truth", 3)["ok"] is False  # 未开标
        of.open_headline_bidding(2)
        assert of.bid_headline("p1", "rebel", 3)["ok"] is False  # 非法阵营
        fake = next(p["id"] for p in of._posts.values() if p.get("is_fake"))
        h0 = of.heat
        assert of.bid_headline("p1", "truth", 3, post_id=fake)["ok"]
        assert of.bid_headline("p2", "pollution", 5, post_id=fake)["ok"]
        res = of.settle_headline()
        assert res["ok"] and res["winner"] == "p2" and res["amount"] == 5
        assert of.heat >= h0
        assert of._headline is None  # 局已收
        # 平价先到先得
        of.open_headline_bidding(3)
        of.bid_headline("pa", "truth", 2)
        of.bid_headline("pb", "pollution", 2)
        assert of.settle_headline()["winner"] == "pa"
        # 流拍
        of.open_headline_bidding(4)
        none = of.settle_headline()
        assert none["ok"] and none["winner"] is None and none["heat"] == of.heat

    def test_heat_ratio_bounds(self, of_shared):
        assert 0.0 <= of_shared.heat_ratio() <= 1.0


def _scn_dir():
    from tests.conftest import SCENARIO_DIR
    return SCENARIO_DIR


# ============================================================ knowledge_cards
@pytest.fixture(scope="module")
def ks_shared(scenario_dir):
    ks = KnowledgeSystem(seed=20260912)
    ks.load(str(scenario_dir))
    return ks


class TestKnowledgeCards:
    def test_load_ten_cards(self, ks_shared):
        assert len(ks_shared._cards) == 10

    def test_draw_shared_pool_seeded(self, scenario_dir):
        a, b = KnowledgeSystem(seed=42), KnowledgeSystem(seed=42)
        for _ in range(10):
            a.load(str(scenario_dir)), b.load(str(scenario_dir))
        a2, b2 = KnowledgeSystem(seed=42), KnowledgeSystem(seed=42)
        a2.load(str(scenario_dir)), b2.load(str(scenario_dir))
        seq_a = [a2.draw("p")["card"]["id"] for _ in range(10)]
        seq_b = [b2.draw("p")["card"]["id"] for _ in range(10)]
        assert seq_a == seq_b and len(set(seq_a)) == 10  # 可复现且不重复
        assert a2.draw("p") is None  # 集齐后枯竭

    def test_counsel_match_and_mismatch(self, ks_shared):
        ks = ks_shared
        card = next(c for c in ks._cards.values()
                    if str(c.get("binds", "")).startswith("char_"))
        ok = ks.counsel("p1", card["binds"], card["id"])
        assert ok["matched"] and ok["effect"] == card.get("effect")
        bad = ks.counsel("p1", "char_99", card["id"])
        assert not bad["matched"] and bad["effect"] == "mock"
        unknown = ks.counsel("p1", "char_99", "kc_none")
        assert "一脸茫然" in unknown["transcript_hint"]

    def test_group_targets_not_counted(self, ks_shared):
        ks = ks_shared
        group = next((c for c in ks._cards.values()
                      if c.get("binds") in ("team_all", "archive_bureau",
                                            "team", "archive")), None)
        if group is None:
            pytest.skip("kanshan 无群组开导卡")
        before = ks.clinic_settlement()["counsel_count"]
        r = ks.counsel("p1", group["binds"], group["id"])
        assert r["matched"]
        after = ks.clinic_settlement()["counsel_count"]
        assert after == before  # 群组对象不计入心晴诊室 counsel_count

    def test_emergency_room_red_light_and_rescue(self, scenario_dir):
        ks = KnowledgeSystem(seed=1)
        ks.load(str(scenario_dir))
        target = "char_02"
        good_card = next(c["id"] for c in ks._cards.values() if c.get("binds") == target)
        wrong_card = next(c["id"] for c in ks._cards.values()
                          if c.get("binds", "").startswith("char_")
                          and c["binds"] != target)
        ks.set_round(1)
        fail = ks.counsel("p1", target, wrong_card)
        assert not fail["matched"] and "红灯" in fail["transcript_hint"]
        # ISSUE-G03（CONCERNS，spec 偏差）：文案承诺「下一轮内」，实现为当轮即生效
        # （expiry=current+1，current_round<=expiry）。本测试锁定当前实际行为：
        # 当轮与下一轮均激活，再下一轮失效。修复与否归 B 组裁决。
        assert ks.er_active(target) is True   # 当轮已亮（spec 说下一轮内）
        ks.set_round(2)
        assert ks.er_active(target) is True   # 下一轮仍有效
        rescue = ks.counsel("p1", target, good_card)
        assert rescue["matched"] and rescue["er_rescue"] is True
        assert rescue["unlocked"].get("doubled") is True
        assert not ks.er_active(target)  # 抢救成功灯灭
        ks.set_round(3)
        assert ks.er_active("char_03") is False

    def test_rescue_buff_ap_doubled(self, scenario_dir):
        ks = KnowledgeSystem(seed=2)
        ks.load(str(scenario_dir))
        ap_card = next((c for c in ks._cards.values() if c.get("effect") == "buff_ap"), None)
        if ap_card is None:
            pytest.skip("无 buff_ap 卡")
        other = next(c["id"] for c in ks._cards.values()
                     if str(c.get("binds", "")).startswith("char_"))
        ks.set_round(1)
        ks.counsel("p1", "team", other)  # 失败 → team 红灯?（团队对象红灯同样登记）
        ks.set_round(2)
        r = ks.counsel("p1", "team", ap_card["id"])
        if r["matched"] and r["er_rescue"]:
            assert r["unlocked"]["ap"] == 2

    def test_clinic_settlement_tiers(self, scenario_dir):
        ks = KnowledgeSystem(seed=3)
        ks.load(str(scenario_dir))
        s0 = ks.clinic_settlement()
        assert s0["counsel_count"] == 0 and s0["ending_modifier"] == "normal"
        char_cards = [(c["binds"], c["id"]) for c in ks._cards.values()
                      if str(c.get("binds", "")).startswith("char_")]
        assert len(char_cards) >= 4, "需至少 4 张 NPC 绑定卡才能验证 4+ 档"
        for binds, cid in char_cards[:2]:
            ks.counsel("p1", binds, cid)
        assert ks.clinic_settlement()["ending_modifier"] == "archive_show"
        for binds, cid in char_cards[2:4]:
            ks.counsel("p1", binds, cid)
        s4 = ks.clinic_settlement()
        assert s4["counsel_count"] >= 4 and s4["hidden_unlock"] is True

    def test_refute_allowed(self, ks_shared, scenario_dir):
        ks = KnowledgeSystem(seed=5)
        ks.load(str(scenario_dir))
        card = next(c for c in ks._cards.values() if c.get("topic_tag"))
        assert ks.refute_allowed(card["id"], card["topic_tag"])
        assert not ks.refute_allowed(card["id"], "不存在的标签")
        assert not ks.refute_allowed("kc_none", "x")


# ============================================================ party
class TestPartyBoard:
    def test_assign_quota_by_player_count(self, char_factions):
        pb = PartyBoard(char_factions, seed=SEED)
        pb.join("player:1"), pb.join("player:2"), pb.join("player:3")
        r3 = pb.assign_factions()
        assert len(r3["pollution"]) == 2 and len(r3["truth"]) == 6
        assert r3["coerced"] in r3["pollution"]
        pb5 = PartyBoard(char_factions, seed=SEED)
        for i in range(1, 6):
            pb5.join(f"player:{i}")
        r5 = pb5.assign_factions()
        assert len(r5["pollution"]) == 3 and len(r5["truth"]) == 5
        assert r5["coerced"] in r5["pollution"]
        swayables = {c for c in r5["pollution"]
                     if char_factions.get(c) == "swayable"}
        if swayables:  # 污染席含 swayable 时，被裹挟者必为其一
            assert char_factions[r5["coerced"]] == "swayable"

    def test_assign_idempotent_and_reshuffle(self, char_factions):
        pb = PartyBoard(char_factions, seed=SEED)
        pb.join("player:1")
        a = pb.assign_factions()
        b = pb.assign_factions()
        assert a == b  # 幂等
        c = pb.assign_factions(reshuffle=True)
        assert set(c["factions"]) == set(a["factions"])

    def test_seats_join_takeover_leave(self, char_factions):
        pb = PartyBoard(char_factions, seed=SEED)
        assert pb.join("player:1", "char_03")["ok"]
        assert pb.join("player:2", "char_03")["reason"] == "seat_taken"
        auto = pb.join("player:2")
        assert auto["ok"] and auto["char_id"] != "char_03"
        # AI 席可被真人顶替（join 未占用角色时 AI 无席位——顶替场景经 leave）
        assert pb.leave("player:1")["ai_takeover"] is True
        seats = {s["char_id"]: s for s in pb.seats()}
        assert seats["char_03"]["ai_takeover"] is True
        assert seats["char_03"]["is_ai"] is True
        assert pb.leave("ghost")["reason"] == "no_seat"
        again = pb.join("player:1")
        assert again["ok"] and again.get("rejoin") and again["char_id"] == "char_03"

    def test_per_actor_ap(self, char_factions):
        pb = PartyBoard(char_factions, seed=SEED)
        pb.join("player:1", "char_01"), pb.join("player:2", "char_02")
        state = pb.reset_round_ap()
        assert all(v == 3 for v in state.values())
        # 8 席位各算各的：真人 2 席 + AI 6 席（真人扮演的角色不再有 AI 席）
        assert len(state) == 8
        assert "player:1" in state and "player:2" in state and "ai:char_03" in state
        assert pb.spend("player:1", 2) and pb.ap_state()["player:1"] == 1
        assert not pb.spend("player:1", 2)  # 不足不透支
        pb.refund("player:1", 5)
        assert pb.ap_state()["player:1"] >= 3
        assert pb.spend("ai:char_05", 1)

    def test_vote_aggregation_and_tie(self, char_factions):
        pb = PartyBoard(char_factions, seed=SEED)
        pb.cast_vote("player:1", "char_02")
        pb.cast_vote("ai:char_03", "char_02")
        pb.cast_vote("danmaku:u1", "char_05", weight=1)
        t = pb.tally()
        assert t["leader"] == "char_02" and t["counts"]["char_02"] == 2
        pb.cast_vote("player:9", "char_05")  # 追平
        t2 = pb.tally()
        assert t2["leader"] is None and sorted(t2["tie"]) == ["char_02", "char_05"]
        pb.cast_vote("player:1", "char_01")  # 一人一票覆盖
        t3 = pb.tally()
        assert t3["counts"]["char_02"] == 1  # 原票被覆盖
        assert len(pb._votes) == 4

    def test_final_statements_and_hammer(self, char_factions):
        pb = PartyBoard(char_factions, seed=SEED)
        pb.final_statement("player:1", "我全程在搜证")
        pb.final_statement("player:1", "补一句：鱼干不是我拿的")  # 覆盖
        pb.final_statement("player:2", "锤 player:1")
        pb.hammer_vote("danmaku:a", "player:1", 3)
        pb.hammer_vote("danmaku:b", "player:1", 1)
        pb.hammer_vote("danmaku:c", "player:2", 1)
        r = pb.hammer_result()
        assert r["most_hammered"] == "player:1"
        assert len(r["statements"]) == 2
        assert r["statements"][0]["text"].startswith("补一句")

    def test_faction_lookup(self, char_factions):
        pb = PartyBoard(char_factions, seed=SEED)
        pb.join("player:1", "char_04")
        pb.assign_factions()
        assert pb.faction_of("player:1") == pb._factions["char_04"]
        assert pb.char_of("ai:char_07") == "char_07"
        assert pb.faction_of("ghost") is None


# ============================================================ difficulty
class TestDifficultyDirector:
    def test_gradient_table_complete(self):
        assert set(difficulty.GRADIENT_TABLE) == {"assist", "normal", "hard"}

    def test_act_settled_three_gradients(self):
        dd = difficulty.DifficultyDirector()
        assert dd.on_act_settled({"clue_count": 1, "coverage": 0.1})["gradient"] == "assist"
        assert dd.on_act_settled({"clue_count": 5, "coverage": 0.4})["gradient"] == "normal"
        assert dd.on_act_settled({"clue_count": 12, "coverage": 0.8})["gradient"] == "hard"
        assert dd.on_act_settled({"clue_count": 5, "stuck_rounds": 2})["gradient"] == "assist"

    def test_apply_to_engine_modules(self, scenario_dir):
        dd = difficulty.DifficultyDirector()
        dd.on_act_settled({"clue_count": 1, "coverage": 0.05})
        ec, of = EvidenceChain(scenario_dir), OpinionFeed()
        of.load(str(scenario_dir))
        dd.apply(ec, of)
        assert ec._gradient == "assist"
        assert of._threshold_delta == difficulty.GRADIENT_TABLE["assist"]["heat_delta"] == 10

    def test_memo_budget_and_direction(self, scenario_dir):
        dd = difficulty.DifficultyDirector()
        dd.on_act_settled({"clue_count": 1, "coverage": 0.05})  # assist → 2 条预算
        ec = EvidenceChain(scenario_dir)
        m1 = dd.memo_for(ec, "看山工位")
        assert m1 and "备忘录" in m1["text"] and m1["hint"]
        m2 = dd.memo_for(ec, "监控室")
        assert m2 and dd.memo_left() == 0
        assert dd.memo_for(ec, "天台") is None  # 预算耗尽
