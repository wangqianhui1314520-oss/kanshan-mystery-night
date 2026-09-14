"""V5 创新机制回归守护：污染对照(S2) / 回声证据(S1) / 法官辩论(S4) / 求真相(S3)

运行（约定于 game/ 目录）：
    pytest tests/test_innovation_v5.py -v

零 AI、零网络：全部走引擎确定性路径。
每个用例都对应一条 mutation 反例——改动引擎规则必须让对应用例失败。
"""
from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------- fixtures
def _to_investigate(driver, session):
    """推进到搜证幕（skill 类动作在破冰幕被引擎门控）。"""
    for _ in range(6):
        driver.apply_action(session, "advance", "player:1", {})
        if session["stage"] in ("investigate", "round_table", "accuse"):
            return session["stage"]
    return session["stage"]


@pytest.fixture()
def driver_and_session(fresh_driver):
    d, sid = fresh_driver()
    s = d.create_session("solo", session_id=sid)
    return d, s


# ------------------------------------------------------- S2 污染对照：数据
def test_pollution_data_integrity(scenario_dir):
    """5 道题：每个 span 都必须在 polluted 文本中真实出现，且改动数恰为 3。"""
    import glob

    files = sorted(glob.glob(str(scenario_dir / "pollution" / "pc_*.json")))
    assert len(files) == 5, f"污染对照题应为 5 道，实际 {len(files)}"
    for f in files:
        d = json.loads(open(f, encoding="utf-8").read())
        assert d.get("original") and d.get("polluted"), f"{d['id']} 缺原文/改写文"
        for sp in d["spans"]:
            assert sp["text"] in d["polluted"], (
                f"{d['id']}/{sp['id']} 的 span 不在 polluted 中，前端无法定位")
        changed = [sp for sp in d["spans"] if sp.get("changed")]
        assert len(changed) == 3, f"{d['id']} 改动数应为 3，实际 {len(changed)}"
        assert all(sp.get("why") for sp in d["spans"]), f"{d['id']} 缺 why 说明"


# ------------------------------------------------------- S2 污染对照：裁决
def test_pollution_all_correct_rewards(driver_and_session):
    d, s = driver_and_session
    _to_investigate(d, s)
    case = d._do_skill(s, "player:1", {"skill": "pollution_open"})[0]["payload"]["case"]
    truth = json.loads(
        (d.scenario_dir / "pollution" / f"{case['id']}.json").read_text(encoding="utf-8"))
    changed = {sp["id"] for sp in truth["spans"] if sp["changed"]}
    res = d._do_skill(s, "player:1",
                      {"skill": "pollution_mark", "case": case["id"],
                       "picks": sorted(changed)})[0]["payload"]
    assert res["passed"] is True and res["missed"] == 0 and res["wrong"] == 0
    assert res["ammo"] == 1 and res["ap_refund"] == 1 and res["heat_delta"] == -2


def test_pollution_wrong_pick_penalty(driver_and_session):
    """误选（把作者原句当成操纵）必须被判错——mutation：去掉误选判定则此例失败。"""
    d, s = driver_and_session
    _to_investigate(d, s)
    case = d._do_skill(s, "player:1", {"skill": "pollution_open"})[0]["payload"]["case"]
    truth = json.loads(
        (d.scenario_dir / "pollution" / f"{case['id']}.json").read_text(encoding="utf-8"))
    untouched = [sp["id"] for sp in truth["spans"] if not sp.get("changed")]
    res = d._do_skill(s, "player:1",
                      {"skill": "pollution_mark", "case": case["id"],
                       "picks": untouched})[0]["payload"]
    assert res["passed"] is False and res["wrong"] >= 1
    assert res["heat_delta"] == 3 and res["ammo"] == 0


def test_pollution_ammo_boosts_refute(driver_and_session):
    """对照弹药在辟谣成功时必须被消耗，并额外压热度 2 点。"""
    d, s = driver_and_session
    _to_investigate(d, s)
    d.pc._ammo = 1
    d.pc._ammo_earned = 1
    pair = None
    for post in d.of._posts.values():
        tag = str(post.get("topic_tag") or "").strip()
        if not tag:
            continue
        for cid, c in d.ks._cards.items():
            if str(c.get("topic_tag") or "").strip() == tag:
                pair = (post, cid)
                break
        if pair:
            break
    assert pair, "剧本应至少有一对 topic_tag 匹配的热搜帖与知识卡"
    post, card_id = pair
    evs = d._do_skill(s, "player:1",
                      {"skill": "refute", "post": post["id"], "card": card_id})
    res = next(e["payload"] for e in evs if e["payload"].get("event") == "refute_result")
    assert res["ok"] is True
    assert res["ammo_spent"] == 1 and res["ammo"] == 0
    assert res["heat_delta"] == -int(post.get("heat_delta", 5)) - 2
    assert d.pc.ammo() == 0 and d.pc.ammo_earned() == 1


def test_pollution_best_score_locked(driver_and_session):
    """通过后再次提交错误答案，成绩不得回退（结算防误伤）。"""
    d, s = driver_and_session
    _to_investigate(d, s)
    case = d._do_skill(s, "player:1", {"skill": "pollution_open"})[0]["payload"]["case"]
    truth = json.loads(
        (d.scenario_dir / "pollution" / f"{case['id']}.json").read_text(encoding="utf-8"))
    changed = {sp["id"] for sp in truth["spans"] if sp["changed"]}
    d._do_skill(s, "player:1", {"skill": "pollution_mark",
                                "case": case["id"], "picks": sorted(changed)})
    d._do_skill(s, "player:1", {"skill": "pollution_mark",
                                "case": case["id"], "picks": []})
    assert d.pc.summary()["passed"] == 1


# --------------------------------------------------------------- S1 回声证据
def test_echo_contradiction_and_defend(driver_and_session):
    d, s = driver_and_session
    _to_investigate(d, s)
    d._do_chat(s, "player:1", {"text": "我相信看山，他没问题", "target": "npc:char_01"})
    d._do_chat(s, "player:1", {"text": "我现在怀疑看山在撒谎", "target": "npc:char_01"})
    assert d.el.summary("player:1")["contradictions"] == 1
    ch = d.el.challenge("player:1")
    assert ch["mode"] == "contradiction"
    pair = ch["pair"]
    wrong = d._do_skill(s, "player:1",
                        {"skill": "echo_defend", "picks": [1, 99]})[0]["payload"]
    assert wrong["passed"] is False
    ok = d._do_skill(s, "player:1",
                     {"skill": "echo_defend", "picks": [pair["a"], pair["b"]]})
    assert ok[0]["payload"]["passed"] is True
    assert ok[0]["payload"]["ap_refund"] == 1
    assert "clue_033" in d.ec.get_player_clues("player:1")


def test_echo_consistent_player_also_passes(driver_and_session):
    """前后一致（无矛盾）的玩家自证应判成功——奖励逻辑自洽。"""
    d, s = driver_and_session
    _to_investigate(d, s)
    d._do_chat(s, "player:1", {"text": "请问昨晚你在哪里", "target": "npc:char_02"})
    res = d._do_skill(s, "player:1", {"skill": "echo_defend", "picks": []})[0]["payload"]
    assert res["passed"] is True and res["mode"] == "consistent"


# --------------------------------------------------------------- S4 法官辩论
def test_judge_stance_biased_by_heat():
    from engine import judge_debate

    jd = judge_debate.JudgeDebate()
    assert jd.open_case(80)["stance"] == "skeptical"   # 被舆论带偏
    assert jd.open_case(10)["stance"] == "open"


def test_judge_scoring_rules():
    from engine import judge_debate

    ctx = {"evidence_terms": ["策划案"], "card_titles": ["如何走出职业倦怠？"],
           "echo_ok": True, "heat": 50}
    jd = judge_debate.JudgeDebate()
    jd.open_case(10)
    r = jd.submit("p", "策划案说明了一切，我承认我动摇过", ctx)
    assert r["gain"] == 3                                  # 证据+2 自证+1
    jd2 = judge_debate.JudgeDebate(); jd2.open_case(10)
    assert jd2.submit("p", "你就是个废物", ctx)["gain"] < 0  # 辱骂扣分
    jd3 = judge_debate.JudgeDebate(); jd3.open_case(10)
    first = jd3.submit("p", "策划案与动机链吻合，我认为成立", ctx)
    repeat = jd3.submit("p", "策划案与动机链吻合，我认为成立", ctx)
    assert repeat["gain"] == first["gain"] - 1, "车轱辘话未触发重复扣分"


def test_judge_convinced_releases_clue(driver_and_session):
    d, s = driver_and_session
    _to_investigate(d, s)
    c1 = d.ks.draw("player:1")["card"]["title"]
    c2 = d.ks.draw("player:1")["card"]["title"]
    d._do_skill(s, "player:1", {"skill": "debate_open"})
    for i, t in enumerate([f"{c1}构成动机", f"{c1}与{c2}互证",
                           f"卷宗中{c2}指向同一人", f"{c1}解释时间线"]):
        d._do_skill(s, "player:1", {"skill": "debate_submit", "claim": t})
    assert d.jd.summary()["convinced"] is True
    assert "clue_034" in d.ec.get_player_clues("player:1")


# --------------------------------------------------------------- S3 求真相
def test_truth_profile_archetypes():
    from engine import truth_profile

    hero = truth_profile.build({
        "clue_count": 9, "coverage": 0.8, "pollution": {"passed": 4, "total": 5, "ammo": 4},
        "refutes": 2, "buy_heats": 0, "counsel_count": 4,
        "echo": {"defended": True}, "debate": {"score": 5, "convinced": True},
        "accused_dm": True, "heat": 20})
    assert hero["archetype"] == "追光者"
    assert hero["scores"]["courage"] == 100
    assert 0 <= hero["overall"] <= 100

    trader = truth_profile.build({
        "clue_count": 2, "coverage": 0.1,
        "pollution": {"passed": 0, "total": 5, "ammo": 0},
        "buy_heats": 3, "heat": 80})
    assert trader["archetype"] == "流量操盘手"
    assert trader["scores"]["independence"] < 20
    assert trader["highlights"], "画像至少应产出一条高光行为"


def test_truth_profile_survives_empty_ctx():
    from engine import truth_profile

    p = truth_profile.build({})
    assert p["archetype"] in truth_profile.ARCHETYPES
    assert len(p["share"]["lines"]) == 3


# ------------------------------------------ 茧房 / 图钉 / 策反（skill 契约）
def test_judge_line_in_icebreaker_grants_core_coverage(driver_and_session):
    """评委线必须在破冰就能上行，并发满起步包（覆盖 ≥50%，否则策反按钮永灰）。"""
    d, s = driver_and_session
    evs, err = d.apply_action(s, "skill", "player:1", {"kind": "judge_line"})
    assert err is None, err
    ready = next(e["payload"] for e in evs if e["payload"].get("event") == "judge_line_ready")
    assert ready["coverage"]["pct"] >= 50
    gained = {e["payload"]["clue_id"] for e in evs if e.get("type") == "clue_gained"}
    assert {"clue_001", "clue_002", "clue_005"} <= gained | set(ready.get("granted") or [])
    assert s.get("stage") == "investigate"
    pins = [e["payload"] for e in evs if e["payload"].get("event") == "evidence_pin"]
    assert len(pins) >= 3
    evs2, err2 = d.apply_action(s, "skill", "player:1", {"kind": "judge_line"})
    assert err2 is None
    ready2 = next(e["payload"] for e in evs2 if e["payload"].get("event") == "judge_line_ready")
    assert ready2["coverage"]["pct"] >= 50
    evs3, err3 = d.apply_action(s, "skill", "player:1",
                                {"kind": "defect", "charId": "char_03"})
    assert err3 is None
    assert evs3[0]["payload"]["event"] == "defect"


def test_search_miss_increments_bias(driver_and_session):
    """搜空也必须记偏执，否则茧房在真引擎局里永远进不去。"""
    d, s = driver_and_session
    _to_investigate(d, s)
    evs, err = d.apply_action(s, "search", "player:1",
                              {"location": "loc_reception", "keyword": "zzzznope"})
    assert err is None, err
    assert d.search_bias, "搜空后 search_bias 不应为空"
    evs2, err2 = d.apply_action(s, "search", "player:1",
                                {"location": "loc_reception", "keyword": "zzzznope"})
    assert err2 is None
    assert max(d.search_bias.values()) >= 2
    assert any((e.get("payload") or {}).get("event") == "cocoon_enter" for e in evs2)


def test_evidence_pin_allowed_in_icebreaker(driver_and_session):
    """破冰幕 StageMachine 禁 skill，但图钉必须能单独上行（否则评委线钉线索 400）。"""
    d, s = driver_and_session
    assert s.get("stage") in ("break_ice", None) or d.sm.stage.value == "break_ice"
    evs, err = d.apply_action(s, "skill", "player:1",
                              {"kind": "evidence_pin", "clueId": "clue_001"})
    assert err is None, err
    assert evs[0]["payload"]["event"] == "pin_rejected"


def test_evidence_pin_owned_via_kind_alias(driver_and_session):
    """前端只发 kind=evidence_pin 也必须命中（mutation：丢掉 kind→skill 则失败）。"""
    d, s = driver_and_session
    _to_investigate(d, s)
    assert d.ec.release("clue_001", "player:1")
    evs, err = d.apply_action(s, "skill", "player:1",
                              {"kind": "evidence_pin", "clueId": "clue_001"})
    assert err is None
    pin = next(e["payload"] for e in evs if e["payload"].get("event") == "evidence_pin")
    assert pin["clueId"] == "clue_001" and "tn_02" in pin["nodes"]
    assert any(l.get("clue_id") == "clue_001" for l in d.evidence_links)


def test_evidence_pin_rejects_unknown(driver_and_session):
    d, s = driver_and_session
    _to_investigate(d, s)
    evs, err = d.apply_action(s, "skill", "player:1",
                              {"skill": "evidence_pin", "clueId": "clue_999"})
    assert err is None
    assert evs[0]["payload"]["event"] == "pin_rejected"


def test_defect_requires_coverage_then_flips(driver_and_session):
    d, s = driver_and_session
    _to_investigate(d, s)
    evs, err = d.apply_action(s, "skill", "player:1",
                              {"kind": "defect", "charId": "char_03"})
    assert err is None
    assert evs[0]["payload"]["event"] == "defect_rejected"
    for cid in ("clue_001", "clue_002", "clue_005"):
        assert d.ec.release(cid, "player:1")
        evs, err = d.apply_action(s, "skill", "player:1",
                                  {"skill": "evidence_pin", "clueId": cid})
        assert err is None
        assert evs[0]["payload"]["event"] == "evidence_pin"
    evs, err = d.apply_action(s, "skill", "player:1",
                              {"skill": "defect", "charId": "char_03"})
    assert err is None
    assert evs[0]["payload"]["event"] == "defect"
    assert d.defection["char_03"]["flipped"] is True


def test_cocoon_break_via_skill(driver_and_session):
    d, s = driver_and_session
    _to_investigate(d, s)
    assert d._note_search_tags(["横幅"]) is False
    assert d._note_search_tags(["横幅"]) is True
    evs, err = d.apply_action(s, "skill", "player:1", {"kind": "cocoon_break"})
    assert err is None
    assert evs[0]["payload"]["event"] == "cocoon_break"
    assert d.cocoon_broken == 1
