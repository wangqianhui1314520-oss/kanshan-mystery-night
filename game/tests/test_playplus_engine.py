"""可玩缺口补全：OpinionFeed 控评/举报 + engine_driver 新技能接线。

零 AI。直接实例化 OpinionFeed 喂帖；引擎技能走 kanshan 真目录。
"""
from __future__ import annotations

from engine.opinion_feed import HEAT_INIT, OpinionFeed
from server.engine_driver import EngineDriver


def _feed_two_posts() -> OpinionFeed:
    of = OpinionFeed()
    of._posts = {
        "p_real": {"id": "p_real", "is_fake": False, "clue_ref": "clue_x",
                   "title": "真帖", "heat_delta": 5},
        "p_fake": {"id": "p_fake", "is_fake": True, "clue_ref": None,
                   "title": "水军帖", "heat_delta": 5},
    }
    return of


def _ev(events, name: str):
    return next((e["payload"] for e in events
                 if (e.get("payload") or {}).get("event") == name), None)


class TestOpinionFeedFloodReport:
    def test_flood_success_and_missing(self):
        of = _feed_two_posts()
        miss = of.flood_comments("p1", "nope")
        assert not miss["ok"] and miss["reason"] == "post_not_found"
        assert miss["heat_delta"] == 0 and miss["heat"] == HEAT_INIT
        ok = of.flood_comments("p1", "p_real")
        assert ok["ok"] and ok["heat_delta"] == 6
        assert ok["heat"] == HEAT_INIT + 6 and of.heat == HEAT_INIT + 6
        assert "clue_x" in of.clues_blocked_by_heat()

    def test_report_spam_fail_and_success(self):
        of = _feed_two_posts()
        assert of.report_spam("p1", "p_real", 1)["reason"] == "not_fake"
        assert of.report_spam("p1", "p_fake", 0)["reason"] == "need_evidence"
        miss = of.report_spam("p1", "ghost", 2)
        assert miss["reason"] == "post_not_found"
        h0 = of.heat
        ok = of.report_spam("p1", "p_fake", 1)
        assert ok["ok"] and ok["heat_delta"] == -4
        assert ok["heat"] == h0 - 4 and "p_fake" in of._refuted


class TestEnginePlayplusSkills:
    def test_quick_session_skips_icebreaker(self, scenario_dir):
        d = EngineDriver(scenario_dir)
        s = d.create_session("quick", "player:1", "s_pp_quick")
        assert s["stage"] != "break_ice"
        assert s["stage"] == "investigate"
        setup = _ev(s["events"], "mode_setup")
        assert setup and setup.get("mode") == "quick"

    def test_quiz_draw_then_correct_answer(self, scenario_dir):
        d = EngineDriver(scenario_dir)
        s = d.create_session("quick", "player:1", "s_pp_quiz")
        evs, err = d.apply_action(s, "skill", "player:1", {"skill": "quiz_draw"})
        assert err is None, err
        q = _ev(evs, "quiz_question")
        assert q and q.get("q") and len(q.get("options") or []) == 3
        evs, err = d.apply_action(s, "skill", "player:1",
                                  {"skill": "quiz_answer", "choice": 0})
        assert err is None, err
        res = _ev(evs, "quiz_result")
        assert res and res["ok"] is True
        assert res["score"] == 1 and s["quiz_score"] == 1
        assert s["zans"] == 2

    def test_unlock_office_code(self, scenario_dir):
        d = EngineDriver(scenario_dir)
        s = d.create_session("quick", "player:1", "s_pp_office")
        evs, err = d.apply_action(s, "skill", "player:1",
                                  {"skill": "unlock_office", "code": "0000"})
        assert err is None, err
        bad = _ev(evs, "office_result")
        assert bad and bad["ok"] is False
        assert not s.get("office_open")
        evs, err = d.apply_action(s, "skill", "player:1",
                                  {"skill": "unlock_office", "code": "4 7 2 9"})
        assert err is None, err
        good = _ev(evs, "office_result")
        assert good and good["ok"] is True
        assert s.get("office_open") is True

    def test_plant_fake_on_fake_clue(self, scenario_dir):
        d = EngineDriver(scenario_dir)
        s = d.create_session("quick", "player:1", "s_pp_plant")
        evs, err = d.apply_action(s, "skill", "player:1",
                                  {"skill": "plant_fake", "clue": "clue_022"})
        assert err is None, err
        res = _ev(evs, "plant_fake_result")
        assert res and res["ok"] is True
        gained = [e for e in evs if e.get("type") == "clue_gained"]
        assert gained and gained[0]["payload"]["clue_id"] == "clue_022"
        assert "clue_022" in d.ec.get_player_clues("player:1")

    def test_flip_side_clue_012_needs_005(self, scenario_dir):
        d = EngineDriver(scenario_dir)
        s = d.create_session("quick", "player:1", "s_pp_flip")
        evs, err = d.apply_action(s, "skill", "player:1",
                                  {"skill": "flip_side", "clue": "clue_012"})
        assert err is None, err
        fail = _ev(evs, "flip_result")
        assert fail and fail.get("ok") is False
        assert not fail.get("back")
        assert d.ec.release("clue_005", "player:1")
        evs, err = d.apply_action(s, "skill", "player:1",
                                  {"skill": "flip_side", "clue_id": "clue_012"})
        assert err is None, err
        ok = _ev(evs, "flip_result")
        assert ok and ok.get("ok") is True
        assert "流量酱" in str(ok.get("back") or "")
