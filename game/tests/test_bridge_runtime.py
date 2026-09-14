"""G × A 交办：bridge 接线测试 pytest 化（源：agents/_bridge_test.py S0-S6，17 断言）。

C 侧运行时（AgentRuntime）× 真实 kanshan 内容 × engine 七模块 × mock LLM（零网络）。
每用例自足建局（不再依赖脚本式共享顺序态），断言与脚本逐条对齐。
"""
from __future__ import annotations

import pytest

from agents.bridge import AgentRuntime
from agents.llm_client import LLMClient
from tests.conftest import SCENARIO_DIR

pytestmark = pytest.mark.bridge

SINK = "char_05"          # 沉底君（kc_06 binds 对象）
CULPRIT = "char_01"


@pytest.fixture()
def rt(tmp_path, monkeypatch):
    """全新 AgentRuntime（mock LLM、独立缓存目录、强制零网络）。"""
    # server.main 导入时 load_dotenv 会注入 game/.env 的真实凭证；
    # 本 fixture 契约是 mock LLM 零网络，故隔离全部 ZHIHU/LLM 凭证。
    for k in ("ZHIHU_APP_KEY", "ZHIHU_ACCESS_SECRET",
              "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    return AgentRuntime(llm=LLMClient(cache_dir=tmp_path / "agents_cache"))


def _card_binds(rt: AgentRuntime, char_id: str) -> str | None:
    for i in range(1, 11):
        c = rt.knowledge.card(f"kc_{i:02d}")
        if c and c.get("binds") == char_id:
            return c["id"]
    return None


class TestAssembly:
    def test_s0_assembly_and_round_event(self, rt):
        assert len(rt.npcs) == 8
        assert len(rt.evidence.pool) >= 30
        assert len(rt.knowledge.held_cards() or []) == 0
        assert len(rt.truth.get("truth_nodes", [])) >= 10
        ev = rt.begin_round()
        assert ev["type"] == "system" and ev["actor"] == "dm"
        assert "叮" in ev["payload"]["text"]


class TestMemoryWiring:
    def test_s1_dual_layer_lifecycle(self, rt):
        # 初始：said 注入 / heart 锁死
        sync0 = rt.sync_memory(SINK)
        npc = rt.npcs[SINK]
        heart0 = next((b.text for b in npc.memory_blocks if b.layer == "heart"), "")
        assert sync0["synced"] and sync0["version"] >= 1
        assert not sync0["heart_unlocked"] and not heart0
        # 未解锁对话零心声外泄
        chat0 = rt.npc_chat(SINK, "你当晚到底在哪？", trust=30)
        assert "heart_unlocked" in chat0 and not chat0["heart_unlocked"]
        assert not heart0 or heart0[:8] not in chat0["reply"]
        # 引擎解锁 → 篡改点入证据链
        unlock = rt.unlock_memory(SINK, "memory_fix")
        assert unlock.get("status") == "ok"
        assert len(unlock.get("tamper_points", [])) >= 1
        assert rt.heart_unlocked(SINK)
        # 解锁后 heart 注入 NPC 状态
        sync1 = rt.sync_memory(SINK)
        heart1 = next((b.text for b in rt.npcs[SINK].memory_blocks
                       if b.layer == "heart"), "")
        assert sync1["heart_unlocked"] and bool(heart1)
        tp_clues = [c for c in rt.evidence.pool if c.startswith("clue_tp_")]
        assert len(tp_clues) >= 1


class TestCounselChain:
    def test_s2_success_and_fail_branches(self, rt):
        kc_ok = _card_binds(rt, SINK)
        assert kc_ok, "SINK 无绑定卡"
        ok = rt.counsel_flow("player:1", SINK, kc_ok)
        assert ok["verdict"]["matched"] and ok["performance"].strip()
        # counsel 条件线索联动（kc_06 → clue_030）
        cond = [c for c in rt.evidence.pool.values()
                if str(c.get("unlock_condition", "")).startswith(f"counsel:{kc_ok}")]
        if cond:
            assert rt.evidence.release(cond[0]["id"], rt.player_id) is not None
        # 失败分支：错配卡 → 尬聊演出
        wrong = next((f"kc_{i:02d}" for i in range(1, 11)
                      if (rt.knowledge.card(f"kc_{i:02d}") or {}).get("binds", "")
                      .startswith("char_")
                      and (rt.knowledge.card(f"kc_{i:02d}") or {}).get("binds") != SINK),
                     None)
        if wrong:
            bad = rt.counsel_flow("player:1", SINK, wrong)
            assert not bad["verdict"]["matched"] and bad["performance"].strip()


class TestSearchAndFlaws:
    def test_s3_s4_search_and_five_flaws(self, rt):
        # 开导 kc_06 → counsel_cards 上下文（clue_030 前置）
        assert rt.counsel_flow("player:1", SINK, "kc_06")["verdict"]["matched"]
        # 彩蛋触发（kanshan 扩展语法）先于破绽链
        rt.npc_chat("char_04", "看山，关门", trust=50)
        rt.enter_review("credits")
        # 搜证链：反馈含 fact 原文 / 弹幕 3-5 条
        hits = [(c.get("location"), c.get("tags", [None])[0])
                for c in rt.evidence.pool.values()
                if c.get("location") and c.get("tags")]
        loc, kw = hits[0]
        sr = rt.search_flow(loc, kw)
        assert sr["feedback"] and 3 <= len(sr["danmaku"]) <= 5
        # 破绽 5 枚随收集同步至 DM
        flaws = sorted([c for c in rt.evidence.pool.values()
                        if c.get("tier") == "boss_flaw" or c.get("flaw_id")],
                       key=lambda c: c["id"])
        released = 0
        for c in flaws:
            if rt.evidence.release(c["id"], rt.player_id):
                released += 1
                rt.sync_flaws()
        assert released == 5
        assert rt.dm.flaw_count == 5 and rt.evidence.boss_ready()


class TestAccusationChain:
    def test_s5_weak_strong_dm_clinic(self, rt):
        # 心晴铺垫：char_05 + char_02 各开导成功一次
        for ch in (SINK, "char_02"):
            card = _card_binds(rt, ch)
            assert card, f"{ch} 无绑定卡"
            res = rt.counsel_flow("player:1", ch, card)
            assert res["verdict"]["matched"]
        # 表层：1 张证据卡 → 引擎判无效
        for cid in ("clue_002", "clue_003", "clue_004"):
            rt.evidence.release(cid, rt.player_id)
        card1 = rt.evidence.try_compose(rt.player_id)
        weak = rt.accuse_flow(CULPRIT, {"motive_statement": "流量焦虑",
                                        "method_statement": "水军"})
        assert card1 and weak["verdict"]["valid"] is False
        assert weak["verdict"]["hit"] is False and weak["verdict"]["ending"] == "wrong"
        # 表层：补 tn_05 组 → 2/2 指认真凶命中
        for cid in ("clue_005", "clue_012", "clue_014"):
            rt.evidence.release(cid, rt.player_id)
        card2 = rt.evidence.try_compose(rt.player_id)
        strong = rt.accuse_flow(CULPRIT, {
            "motive_statement": rt.truth["culprit"].get("motive", "")[:40],
            "method_statement": "马甲号水军矩阵"})
        assert card2 and strong["verdict"]["valid"] is True
        assert strong["verdict"]["hit"] is True
        # 终极：指认 DM（破绽 5 + 心晴 2）→ 看山还是山 + 现身演出
        # 彩蛋触发（031 唤醒词 / 032 复盘页）——脚本 S3 的顺序依赖在此自足补齐
        rt.npc_chat("char_04", "看山，关门", trust=50)
        rt.enter_review("credits")
        flaws = [c for c in rt.evidence.pool.values()
                 if c.get("tier") == "boss_flaw" or c.get("flaw_id")]
        for c in flaws:
            rt.evidence.release(c["id"], rt.player_id)
            rt.sync_flaws()
        dm = rt.accuse_flow("dm")
        assert dm["boss_accusal"] and dm["verdict"].get("allowed")
        assert dm["verdict"]["ending"] == "kanshan_still_mountain"
        assert "刘看山" in (dm["performance"] or "")
        # 心晴诊室结算链
        clinic = rt.clinic_flow()
        assert clinic["settlement"]["counsel_count"] >= 2
        assert clinic["clinic"]["clinic_text"].strip()


class TestGuardFallback:
    def test_s6_heart_injection_blocked(self, rt):
        rt.unlock_memory(SINK, "memory_fix")   # 产出真实 kanshan heart 块
        heart_blocks = [b for b in rt.memory.visible_blocks(SINK, include_heart=True)
                        if b.layer == "heart"]
        if not heart_blocks:
            pytest.skip("该角色无 heart 块可探")
        hb = {"layer": "heart", "text": heart_blocks[0].text}
        leak = hb["text"].strip("（）()")[:20]
        viol = rt.guard.check(rt.npcs[SINK].character, leak,
                              {"memory_state": {"heart_unlocked": False,
                                                "blocks": [hb]}})
        assert any("心声泄露" in v for v in viol)
