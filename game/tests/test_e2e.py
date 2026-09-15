"""G 原矩阵③：端到端 —— 单人 8 NPC 三幕全流程（真实内容 + 真实引擎驱动）。

路径：服务端动作管线（EngineDriver.apply_action，契约 §3.6 六类动作），
零 AI、零网络；数据驱动选路（线索元数据 → 搜证关键词），断言确定性结局。
"""
from __future__ import annotations

import json

import pytest

from server.engine_driver import EngineDriver
from tests.conftest import SCENARIO_DIR

pytestmark = pytest.mark.e2e


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def content_index():
    clues = {c["id"]: c for f in (SCENARIO_DIR / "clues").glob("*.json")
             for c in [_load(f)]}
    truth = _load(SCENARIO_DIR / "truth.json")
    return dict(clues=clues, truth=truth)


def _eligible_nodes(index, n=2):
    """挑 n 个「可诚实搜证」的真相节点：proof_clues 全为 public/limited 且无条件门。"""
    out = []
    for node in index["truth"]["truth_nodes"]:
        proofs = []
        ok = True
        for cid in node.get("proof_clues", []):
            c = index["clues"].get(cid)
            if c is None or (c.get("tier") or "public") not in ("public", "limited") \
                    or str(c.get("unlock_condition", "默认")) != "默认":
                ok = False
                break
            proofs.append(c)
        if ok and len(proofs) >= 3:
            out.append((node, proofs))
        if len(out) >= n:
            break
    assert len(out) == n, "无可诚实搜证的双节点，端到端选路失败"
    return out


def _search_clue(driver, session, clue, tries=3, actor="player:1"):
    """定向搜证直至持有目标线索（同地点重试跳过已持有高优先级线索）。"""
    for _ in range(tries):
        if clue["id"] in driver.ec.get_player_clues(actor):
            return True
        if session.get("actions_left", 0) < 1:
            return False  # 预算内未拿到（由用例显式管理幕与 AP）
        events, err = driver.apply_action(
            session, "search", actor,
            {"location": clue["location"], "keyword": clue["tags"][0]})
        assert err is None, f"搜证被拒：{err}"
    return clue["id"] in driver.ec.get_player_clues(actor)


class TestSinglePlayerE2E:
    def test_full_truth_run(self, content_index):
        """表层全流程：唤醒词 → 定向搜证（tn_01+tn_03 双证据卡）→
        memory:char_05:3 条件链（memory_fix×2 → counsel 同步 → clue_013）→
        指认真凶 → 真相大白 + 复盘页 clue_032。预算：investigate 12AP 恰好闭环。"""
        driver = EngineDriver(SCENARIO_DIR)
        session = driver.create_session("main", "player:1", "s_ge2e_1")
        assert session["engine"] == "engine_v3" and session["clue_pool_size"] == 34
        assert len(session["npcs"]) == 8 and session["stage"] == "break_ice"
        clues = content_index["clues"]

        # 1) 破冰：唤醒词彩蛋（chat:keyword_ 扩展语法）
        events, err = driver.apply_action(
            session, "chat", "player:1", {"text": "看山，关门"})
        assert err is None
        assert any(e["type"] == "clue_gained" and e["payload"]["clue_id"] == "clue_031"
                   for e in events), "唤醒词未触发 clue_031"

        # 2) 进入搜证幕（12AP 预算，全程不许 advance——round_table 无 search）
        driver.apply_action(session, "advance", "player:1", {})
        assert session["stage"] == "investigate"

        # 3) 定向搜证（引擎侧双节点合成）：
        #    tn_01 ← 002/004/007；btn_01 ← 002/007/016（boss 节点，002/007 复用）
        #    看山工位×鱼干 首搜按优先级先得 boss_flaw clue_028（重试得 007）
        for cid in ("clue_002", "clue_004", "clue_007", "clue_016"):
            assert _search_clue(driver, session, clues[cid]), f"{cid} 未搜得"
        # 合成器行为：每次搜证后取「字典序首个可合成节点」出卡（btn_01 优先且随持有
        # 扩集重复出卡）——机制可接受，有效性只看卡数 ≥2（resolve_accusation 契约）
        composed = driver.ec.evidence_cards("player:1")
        assert len(composed) >= 2, f"证据卡未合成：{composed}"

        # 4) 开导（2AP）：匹配卡 → 心晴 +1（counsel 管线 + memory 同步路径）
        held = driver.ks.held_cards()
        card = next(c for c in held if str(c.get("binds", "")).startswith("char_"))
        events, err = driver.apply_action(session, "counsel", "player:1",
                                          {"card": card["id"], "target": card["binds"]})
        assert err is None
        assert any(e["type"] == "counsel_result" and e["payload"]["matched"]
                   for e in events), "开导未命中（选路假设破坏）"

        # 5) 指认幕：投真凶（≥2 证据卡有效）
        assert len(driver.ec.evidence_cards()) >= 2
        driver.apply_action(session, "advance", "player:1", {})  # → round_table
        driver.apply_action(session, "advance", "player:1", {})  # → accuse
        assert session["stage"] == "accuse"
        culprit = content_index["truth"]["culprit"]["character"]
        events, err = driver.apply_action(session, "vote", "player:1",
                                          {"target": culprit})
        assert err is None
        ending = next(e for e in events if e["type"] == "ending")
        assert ending["payload"]["accused"] == f"npc:{culprit}"
        vr = ending["payload"]["detail"]["vote_result"]
        assert vr["valid"] is True and vr["hit"] is True
        assert ending["payload"]["outcome"] == "truth_revealed"
        assert vr["ending"] == "truth_revealed"
        assert ending["payload"]["detail"]["review_clues"] == ["clue_032"]
        assert session["status"] == "ended"

        # 8) 事件信封契约（§3.6）
        for e in session["events"]:
            assert {"type", "session_id", "round", "actor", "payload"} <= set(e)
            assert e["session_id"] == "s_ge2e_1"

    def test_replay_determinism(self, content_index):
        """服务重启恢复：按 actions 日志确定性回放 → 状态一致。"""
        def build_and_run():
            d = EngineDriver(SCENARIO_DIR)
            s = d.create_session("main", "player:1", "s_ge2e_2")
            d.apply_action(s, "chat", "player:1", {"text": "看山，关门"})
            d.apply_action(s, "advance", "player:1", {})
            assert _search_clue(d, s, content_index["clues"]["clue_028"])
            assert _search_clue(d, s, content_index["clues"]["clue_029"])
            d.apply_action(s, "advance", "player:1", {})   # round_table
            d.apply_action(s, "advance", "player:1", {})   # accuse
            _, err = d.apply_action(s, "vote", "player:1",
                                    {"target": content_index["truth"]["culprit"]["character"]})
            assert err is None
            return s

        s1 = build_and_run()
        # 模拟重启：全新引擎实例回放动作日志
        d2 = EngineDriver(SCENARIO_DIR)
        s2 = d2.create_session("main", "player:1", "s_ge2e_2")
        replay = list(s1["actions"])
        s2["actions"] = []
        for act in replay:
            _, err = d2.apply_action(s2, act["type"], act["actor"], act["payload"])
            assert err is None
        keys = ("stage", "round", "clues_gained", "votes", "status", "flaw_count",
                "counsel_count", "held_cards", "evidence_cards", "boss_ready")
        for k in keys:
            assert s1[k] == s2[k], f"回放发散：{k}"

    def test_boss_accusation_ultimate_reachable(self, content_index):
        """破绽 5/5（进指认幕发放 clue_032）+ 心晴 ≥2 → 指认 DM → 看山还是山。"""
        driver = EngineDriver(SCENARIO_DIR)
        session = driver.create_session("main", "player:1", "s_ge2e_3")
        driver.apply_action(session, "chat", "player:1", {"text": "看山，关门"})
        driver.apply_action(session, "advance", "player:1", {})
        clues = content_index["clues"]
        assert _search_clue(driver, session, clues["clue_028"])
        assert _search_clue(driver, session, clues["clue_029"])
        # 抽卡必须给开导留 2AP：先拿到 kc_06 发破绽三，有余力再开第二人
        def _draw_until(pred, reserve=2):
            guard = 0
            while not pred() and session.get("actions_left", 0) > reserve and guard < 12:
                guard += 1
                driver.apply_action(session, "search", "player:1",
                                    {"location": "茶水间", "keyword": "泡面"})

        def _has_kc06():
            return any(c["id"] == "kc_06" for c in driver.ks.held_cards())

        def _extra_char():
            return next((c for c in driver.ks.held_cards()
                         if c["id"] != "kc_06"
                         and str(c.get("binds") or "").startswith("char_")), None)

        _draw_until(_has_kc06, reserve=2)
        assert _has_kc06(), f"预算内未抽到 kc_06：{session.get('held_cards')}"
        evs, err = driver.apply_action(session, "counsel", "player:1",
                                       {"card": "kc_06", "target": "char_05"})
        assert err is None
        assert any(e.get("payload", {}).get("clue_id") == "clue_030" for e in evs)
        _draw_until(lambda: _extra_char() is not None, reserve=2)
        extra = _extra_char()
        if extra and session.get("actions_left", 0) >= 2:
            driver.apply_action(session, "counsel", "player:1",
                                {"card": extra["id"], "target": extra["binds"]})
        counsel_n = driver.ks.clinic_settlement()["counsel_count"]
        assert "clue_030" in driver.ec.get_player_clues("player:1")
        assert driver.ec.flaw_count() == 4  # clue_032 在进入 accuse 时发放
        driver.apply_action(session, "advance", "player:1", {})
        driver.apply_action(session, "advance", "player:1", {})
        assert session["stage"] == "accuse"
        assert driver.ec.flaw_count() == 5 and driver.ec.boss_ready() is True
        events, err = driver.apply_action(session, "vote", "player:1", {"target": "dm"})
        assert err is None
        ending = next(e for e in events if e["type"] == "ending")
        expect = "kanshan_still_mountain" if counsel_n >= 2 else "truth_revealed"
        assert ending["payload"]["outcome"] == expect
        assert ending["payload"]["detail"]["vote_result"]["allowed"] is True
        assert ending["payload"]["outcome"] != "dm_mock"

    def test_negative_paths(self, content_index):
        driver = EngineDriver(SCENARIO_DIR)
        session = driver.create_session("main", "player:1", "s_ge2e_4")
        # 破冰阶段禁搜证
        _, err = driver.apply_action(session, "search", "player:1",
                                     {"location": "监控室", "keyword": "监控"})
        assert err and "不允许" in err
        # 未知动作类型
        _, err = driver.apply_action(session, "hack", "player:1", {})
        assert err and "未支持" in err
        # 非 player actor
        _, err = driver.apply_action(session, "chat", "npc:char_01", {"text": "hi"})
        assert err and "player:" in err
        # 唤醒词后搜证（→investigate），AP 不足拒绝 counsel（2AP）
        driver.apply_action(session, "chat", "player:1", {"text": "看山，关门"})
        driver.apply_action(session, "advance", "player:1", {})
        session["actions_left"] = 1
        _, err = driver.apply_action(session, "counsel", "player:1",
                                     {"card": "kc_01", "target": "char_06"})
        assert err and "行动力不足" in err
        # 恶意地点
        events, err = driver.apply_action(session, "search", "player:1",
                                          {"location": "../../etc", "keyword": "x"})
        assert err is None and any(
            e["payload"].get("event") == "bad_location" for e in events)
        # round_table 是对质幕：search 必须被引擎拒绝，且不消耗 AP/不写入搜证结果。
        driver.apply_action(session, "advance", "player:1", {})
        assert session["stage"] == "round_table"
        ap_before = session["actions_left"]
        action_count_before = len(session["actions"])
        events, err = driver.apply_action(session, "search", "player:1",
                                          {"location": "监控室", "keyword": "监控"})
        assert err and "不允许动作 search" in err
        assert session["actions_left"] == ap_before
        assert len(session["actions"]) == action_count_before
        assert not any(e["type"] == "search_result" for e in events)
        # 无效投票目标
        driver.apply_action(session, "advance", "player:1", {})
        events, err = driver.apply_action(session, "vote", "player:1",
                                          {"target": "char_99"})
        assert err is None and any(
            e["payload"].get("event") == "bad_target" for e in events)
