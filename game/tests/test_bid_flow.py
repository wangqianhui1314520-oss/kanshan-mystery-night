"""热搜竞价轮次（bid_headline 窗口化）回归测试。

冻结契约（docs/FRONTEND_BACKEND_COVERAGE §3.6 增补，只增不改）：
- 服务端→客户端事件：headline_open / headline_bid / headline_outbid / headline_settle
- 客户端→服务端动作：bid_headline（窗口内出价）/ bid_pass（本窗口放弃）
- 向后兼容硬约束：无开启窗口时 bid_headline → 旧一次性语义（headline_result）
"""
from __future__ import annotations

import time

import pytest

from tests.conftest import SCENARIO_DIR

from server.engine_driver import EngineDriver
from engine import stage_machine


def _make_driver():
    driver = EngineDriver(SCENARIO_DIR)
    session = driver.create_session("main", "player:1", "s_bidflow")
    return driver, session


def _to_round_table(driver, session):
    driver.apply_action(session, "advance", "player:1", {})  # → investigate
    driver.apply_action(session, "advance", "player:1", {})  # → round_table
    assert session["stage"] == "round_table"


def _bid(driver, session, actor, amount, topic="post_001"):
    return driver.apply_action(
        session, "skill", actor,
        {"skill": "bid_headline", "topic": topic, "amount": amount})


class TestHeadlineWindowLifecycle:
    def test_headline_open_on_stage_entry(self):
        """进入热搜战阶段（round_table）→ 广播 headline_open（契约字段齐全）。"""
        driver, session = _make_driver()
        driver.apply_action(session, "advance", "player:1", {})  # → investigate
        events, err = driver.apply_action(session, "advance", "player:1", {})
        assert err is None
        open_ev = next(e for e in events if e["type"] == "headline_open")
        p = open_ev["payload"]
        assert p["window_id"] and p["round"] == session["round"]
        assert p["deadline_ts"] > time.time() and p["deadline_in"] > 0
        assert p["min_bid"] == 1 and p["reason"]
        assert p["topics"], "topics 不得为空（kanshan 帖池已装载）"
        for t in p["topics"]:
            assert set(t) >= {"id", "title", "is_fake"}

    def test_open_idempotent_same_round(self):
        """同 round 重复 open 幂等：不重开、window_id 不变。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        wid = driver._headline_window["window_id"]
        assert driver._open_headline_window(session, "again") is None
        assert driver._headline_window["window_id"] == wid

    def test_settle_on_deadline_lazy(self):
        """懒结算：deadline 已过 → 下一动作即结算（headline_settle，胜者生效）。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        _bid(driver, session, "player:1", 2)
        driver._headline_window["deadline_ts"] = time.time() - 1
        events, err = driver.apply_action(session, "chat", "player:2", {"text": "围观"})
        assert err is None
        settle = next(e for e in events if e["type"] == "headline_settle")
        p = settle["payload"]
        assert p["winner"] == "player:1" and p["amount"] == 2
        assert p["topic_id"] == "post_001" and p["topic_title"]
        assert p["effect"] and p["window_id"]

    def test_force_settle_on_act_end(self):
        """幕结束强制结算未决窗口，且进入指认幕后开新窗口。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        _bid(driver, session, "player:1", 2)
        events, err = driver.apply_action(session, "advance", "player:1", {})
        assert err is None
        settle = next(e for e in events if e["type"] == "headline_settle")
        assert settle["payload"]["reason"] == "act_end"
        assert settle["payload"]["winner"] == "player:1"
        assert any(e["type"] == "headline_open" for e in events), "指认幕应开新窗口"
        assert driver._headline_window is not None

    def test_no_bid_liupai(self):
        """流拍：无人出价 → winner=null，effect 写明流拍。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        driver._headline_window["deadline_ts"] = time.time() - 1
        events, err = driver.apply_action(session, "advance", "player:1", {})
        assert err is None
        settle = next(e for e in events if e["type"] == "headline_settle")
        assert settle["payload"]["winner"] is None
        assert "流拍" in settle["payload"]["effect"]


class TestHeadlineBidRules:
    def test_bid_freeze_and_outbid_refund(self):
        """出价冻结 AP；被反超退还原冻结并广播 headline_outbid（对原最高者）。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        ap0 = session["actions_left"]
        events, err = _bid(driver, session, "player:1", 2)
        assert err is None
        bid = next(e for e in events if e["type"] == "headline_bid")
        assert bid["payload"] == {**bid["payload"], "bidder": "player:1",
                                  "amount": 2, "is_top": True, "top_amount": 2} | \
                                 {"window_id": bid["payload"]["window_id"]}
        assert session["actions_left"] == ap0 - 2, "出价即冻结"
        events2, err = _bid(driver, session, "player:2", 3, topic="post_004")
        assert err is None
        bid2 = next(e for e in events2 if e["type"] == "headline_bid")
        assert bid2["payload"]["is_top"] is True and bid2["payload"]["top_amount"] == 3
        out = next(e for e in events2 if e["type"] == "headline_outbid")
        assert out["payload"]["prev_bidder"] == "player:1"
        assert out["payload"]["new_amount"] == 3 and out["payload"]["prev_amount"] == 2
        assert out["actor"] == "player:1", "outbid 事件以被反超者为 actor"
        assert session["actions_left"] == ap0 - 3, "原最高者退还 2、新最高者冻结 3"

    def test_rebid_self_no_outbid(self):
        """同一玩家改价：不产生 outbid，冻结额按新价累计。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        ap0 = session["actions_left"]
        _bid(driver, session, "player:1", 2)
        events, err = _bid(driver, session, "player:1", 4)
        assert err is None
        assert not any(e["type"] == "headline_outbid" for e in events)
        bid = next(e for e in events if e["type"] == "headline_bid")
        assert bid["payload"]["top_amount"] == 4
        assert session["actions_left"] == ap0 - 4

    def test_tie_first_wins(self):
        """同额先到先得：平价时后出者 is_top=false，结算先到者胜。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        _bid(driver, session, "player:1", 3)
        events, err = _bid(driver, session, "player:2", 3, topic="post_004")
        assert err is None
        bid2 = next(e for e in events if e["type"] == "headline_bid")
        assert bid2["payload"]["is_top"] is False
        assert not any(e["type"] == "headline_outbid" for e in events)
        driver._headline_window["deadline_ts"] = time.time() - 1
        settle_events = driver._maybe_settle_headline(session)
        settle = next(e for e in settle_events if e["type"] == "headline_settle")
        assert settle["payload"]["winner"] == "player:1"

    def test_min_bid_and_ap_gates(self):
        """出价 ≥ min_bid 且 AP 足够；不足时零扣费拒绝。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        _, err = _bid(driver, session, "player:1", 0)
        assert err and "1–12" in err, "低于 1 点直接拒绝"
        driver.sm.actions_left = 1
        events, err = _bid(driver, session, "player:1", 2)
        assert err is None
        assert any(e["payload"].get("event") == "bid_rejected" for e in events)
        assert driver.sm.actions_left == 1, "拒绝出价零扣费"
        assert session["actions_left"] == driver.sm.actions_left == 1


class TestBidPass:
    def test_bid_pass_in_window(self):
        """bid_pass：窗口内放弃，零 AP，广播确认。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        ap0 = session["actions_left"]
        events, err = driver.apply_action(session, "bid_pass", "player:1", {})
        assert err is None
        assert any(e["payload"].get("event") == "bid_pass_ack" for e in events)
        assert session["actions_left"] == ap0
        assert "player:1" in driver._headline_window["passed"]

    def test_bid_pass_without_window_rejected(self):
        """无窗口时 bid_pass 被阶段门禁拒绝（err 非 None）。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        driver._headline_window = None
        _, err = driver.apply_action(session, "bid_pass", "player:1", {})
        assert err is not None


class TestLegacyCompat:
    def test_legacy_one_shot_without_window(self):
        """向后兼容硬约束：无开启窗口 → 旧一次性语义（headline_result，立即结算）。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        driver._headline_window = None  # 模拟旧存档/旧前端
        driver.of._headline = None
        ap0 = session["actions_left"]
        events, err = driver.apply_action(
            session, "skill", "player:1",
            {"skill": "bid_headline", "post": "post_001", "amount": 2})
        assert err is None
        result = next(e for e in events if e["payload"].get("event") == "headline_result")
        assert result["payload"]["settle"]["winner"] == "player:1"
        assert not any(e["type"] == "headline_bid" for e in events)
        assert session["actions_left"] == ap0 - 2, "旧语义走标准扣费路径"

    def test_bid_after_deadline_rejected_no_ap_loss(self):
        """截止后的迟到出价：先结算旧窗口，再拒绝本次出价（零扣费）。"""
        driver, session = _make_driver()
        _to_round_table(driver, session)
        ap0 = session["actions_left"]
        _bid(driver, session, "player:1", 2)
        driver._headline_window["deadline_ts"] = time.time() - 1
        events, err = _bid(driver, session, "player:2", 3)
        assert err is None
        assert any(e["type"] == "headline_settle" for e in events)
        assert any(e["payload"].get("event") == "bid_rejected" for e in events)
        assert driver.sm.actions_left == ap0 - 2, "迟到者未被扣费"


class TestPartyMode:
    def test_party_freeze_and_outbid_refund(self):
        """party 模式：各自 AP 池冻结/退还。"""
        driver = EngineDriver(SCENARIO_DIR)
        session = driver.create_session("party", "player:1", "s_bidflow_party")
        driver.join_seat("player:1")
        driver.join_seat("player:2")
        session["round"] = 3
        driver.sm.stage = stage_machine.Stage.ROUND_TABLE
        open_ev = driver._open_headline_window(session, "test")
        assert open_ev is not None and open_ev["type"] == "headline_open"
        ap1_0 = driver.pb.ap_state()["player:1"]
        ap2_0 = driver.pb.ap_state()["player:2"]
        events, err = _bid(driver, session, "player:1", 2)
        assert err is None
        assert driver.pb.ap_state()["player:1"] == ap1_0 - 2
        events2, err = _bid(driver, session, "player:2", 3, topic="post_004")
        assert err is None
        assert driver.pb.ap_state()["player:1"] == ap1_0, "被反超退还"
        assert driver.pb.ap_state()["player:2"] == ap2_0 - 3
        settle_events = driver._settle_headline_window(session, reason="test")
        settle = next(e for e in settle_events if e["type"] == "headline_settle")
        assert settle["payload"]["winner"] == "player:2"
        assert driver.pb.ap_state()["player:2"] == ap2_0 - 3, "胜者冻结即扣除"
