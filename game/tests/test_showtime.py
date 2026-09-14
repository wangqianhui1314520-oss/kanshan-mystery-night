"""G × A 交办：showtime v2 测试 pytest 化（源：agents/_showtime_test.py T0-T11，56 断言）。

C 组演出生成（ShowtimeDirector）+ bridge 运行时演 flow + D 组文案池解析 +
成就判定（AchievementEngine/resolver 双路径）+ LLM 失败兜底（零网络）。
每用例自足建局；纯读类共享只读 runtime。
"""
from __future__ import annotations

import pytest

from agents.bridge import AgentRuntime
from agents.llm_client import LLMClient
from agents.showtime import ShowtimeDirector
from tests.conftest import SCENARIO_DIR

pytestmark = pytest.mark.showtime


@pytest.fixture(scope="module")
def rt_ro(tmp_path_factory):
    """只读演出位共享实例（T0/T2/T3 纯读，不污染状态）。"""
    cache = tmp_path_factory.mktemp("showtime_ro_cache")
    return AgentRuntime(llm=LLMClient(cache_dir=cache))


@pytest.fixture()
def rt(tmp_path):
    """全新可变 runtime（record/counters 类用例专用）。"""
    return AgentRuntime(llm=LLMClient(cache_dir=tmp_path / "agents_cache"))


# ================================================================ T0 文案池解析
class TestT0Segments:
    def test_glitch_pairs(self, rt_ro):
        seg = rt_ro.show.segments
        assert len(seg.glitch_pairs) == 8
        assert all("【惩罚" in b for b, _ in seg.glitch_pairs)

    def test_quiz_bank(self, rt_ro):
        seg = rt_ro.show.segments
        assert len(seg.quiz_bank) == 20
        assert all(q["question"] and q["options"] and q["answer_text"] and q["taunt"]
                   for q in seg.quiz_bank)

    def test_achievement_library(self, rt_ro):
        seg = rt_ro.show.segments
        assert len(seg.achievements) >= 23
        assert all(a["banner"] and a["share_line"] for a in seg.achievements)

    def test_headline_radio_antifraud_pools(self, rt_ro):
        seg = rt_ro.show.segments
        assert len(seg.headline_topics) == 8
        assert len(seg.radio_reports) == 6
        assert len(seg.antifraud_acts) == 3


# ================================================================ T1 成就判定
class TestT1Achievements:
    def test_empty_session_zero(self, rt):
        assert rt.achievements_flow() == []

    def test_egg_and_ending_hits(self, rt):
        rt.record_event("chat_keyword", value="看山，关门")
        rt.record_event("ending", value="ending_kanshan")
        fresh = rt.achievements_flow()
        ids = {a["id"] for a in fresh}
        assert {"ach_huanxingci", "ach_zhenshan"} <= ids
        assert all(a["banner"] and a["share_line"] and a["ai_comment"] for a in fresh)
        assert any("谁教的它这么没礼貌" in a["banner"]
                   for a in fresh if a["id"] == "ach_huanxingci")

    def test_dedup(self, rt):
        rt.record_event("chat_keyword", value="看山，关门")
        rt.record_event("ending", value="ending_kanshan")
        rt.achievements_flow()
        assert rt.achievements_flow() == []

    def test_numeric_conditions(self, rt):
        rt.record_event("quiz_score", inc=10)
        rt.record_event("listen_full", target="char_06", inc=3)
        ids = {a["id"] for a in rt.achievements_flow()}
        assert {"ach_kuaidan", "ach_fangzhe"} <= ids


# ================================================================ T2 P1 演出位
class TestT2P1Show:
    def test_glitch_rewrite(self, rt_ro):
        assert "认真搜证" in rt_ro.show.glitch_rewrite("【惩罚：围观鱼干一分钟】")
        assert "该道歉已被折叠" in rt_ro.show.glitch_rewrite("【惩罚：向折叠区怨灵道歉】")

    def test_glitch_banner(self, rt_ro):
        assert "叮——" in rt_ro.show.glitch_banner()

    def test_bet_settle(self, rt_ro):
        assert "眼光毒辣" in rt_ro.show.bet_settle(True)
        assert "押错了" in rt_ro.show.bet_settle(False)

    def test_red_alert_and_rescue(self, rt_ro):
        ra = rt_ro.show.red_alert("沉底君")
        assert "沉底君" in ra and "红灯" in ra
        assert "双折叠" in rt_ro.show.npc_red_state("沉底君")
        rs = rt_ro.show.rescue_success("沉底君")
        assert "抢救成功" in rs and "该发言已被展开" in rs

    def test_broadcast_accident_whitelist(self, rt_ro):
        ba = rt_ro.show.broadcast_accident("路人甲")
        assert any(w in ba for w in ("泡面", "工牌", "鱼干的味道", "给妈打电话",
                                     "生日便签", "生日"))
        assert "删除" not in ba and "监控" not in ba

    def test_headline_host_lines(self, rt_ro):
        seg = rt_ro.show.segments
        ha = rt_ro.show.headline_auction()
        assert "头条位开标" in ha and any(t in ha for t, _ in seg.headline_topics)
        assert "截图存证" in rt_ro.show.headline_result("pollution")


# ================================================================ T3 P2 演出位
class TestT3P2Show:
    def test_radio_station_pool_and_fill(self, rt_ro):
        rd = rt_ro.show.radio_station(round_no=3, clue_count=5)
        assert "广播台" in rd
        seg = rt_ro.show.segments
        tpl = next(t for t in seg.radio_reports if "第 N 小时" in t)
        filled = tpl.replace("第 N 小时", "第 3 小时").replace("线索 N 条", "线索 5 条")
        assert "第 3 小时" in filled and "线索 5 条" in filled

    def test_radio_spotlight(self, rt_ro):
        assert "卡路里" in rt_ro.show.radio_station(round_no=1, spotlight="流量酱")

    def test_antifraud_three_acts(self, rt_ro):
        acts = [rt_ro.show.anti_fraud_theater(i) for i in (1, 2, 3)]
        assert all("话术拆解" in x for x in acts)
        assert "查无此猫" in acts[0] and "截止时间" in acts[1] and "设备指纹" in acts[2]
        assert "反诈学分" in rt_ro.show.antifraud_settle(True)

    def test_quick_quiz_draw(self, rt_ro):
        qs = [rt_ro.show.quick_quiz() for _ in range(10)]
        assert all(q["source"] == "segments_bank" for q in qs)
        assert all(q["options"][q["answer_index"]] == q["answer_text"] for q in qs)
        assert len({q["question"] for q in qs}) == 10


# ================================================================ T4 计分链
class TestT4ScoreFlows:
    def test_quiz_flow_issue_judge_score(self, rt):
        issued = rt.quiz_flow()
        q = issued["quiz"]
        assert issued["correct"] is None and q is not None
        ok = rt.quiz_flow(quiz=q, answer_index=q["answer_index"])
        bad = rt.quiz_flow(quiz=q, answer_text="绝不可能是这个答案")
        assert ok["correct"] is True and rt.counters["quiz_score"] >= 1
        assert bad["correct"] is False

    def test_refute_flow_counters(self, rt):
        ref = rt.refute_flow("player:1", "post_008", "kc_01")
        assert isinstance(ref, dict) and ref.get("ok") is True
        assert rt.counters["fake_exposed"] >= 1
        assert rt.counters["refute_success_streak"] >= 1
        assert "antifraud_theater" in ref


# ================================================================ T5 防卡死备忘录
class TestT5Memo:
    def test_assist_budget_and_hard_disable(self, rt):
        rt.last_hit_round = 0
        rt.stage_machine._round = 4
        grad = rt.act_settled()                      # stuck_rounds>=2 → assist
        assert grad["gradient"] == "assist" and grad["memo_budget"] == 2
        m1 = rt.memo_flow()
        assert m1 is not None and m1["source"] == "difficulty_engine"
        assert m1["hint"] and m1["hint"] in m1["memo_text"]
        assert rt.memo_flow() is not None            # assist 预算第 2 条
        assert rt.memo_flow() is None                # 预算耗尽
        rt.difficulty.on_act_settled({"clue_count": 12, "coverage": 0.9,
                                      "stuck_rounds": 0})
        rt.difficulty.apply(rt.evidence, rt.opinion)
        assert rt.difficulty.gradient == "hard"
        assert rt.memo_flow() is None                # hard 档禁用


# ================================================================ T6 引擎权威成就/广播/收集品
class TestT6EngineAuthority:
    def test_achievement_engine_wiring(self, rt):
        rt.record_event("chat_keyword", value="看山，关门")
        rt.ae.evaluate(None)
        assert "ach_huanxingci" in rt.ae.unlocked_ids()
        flow = rt.achievements_flow()
        assert any(a["id"] == "ach_huanxingci" for a in flow)
        assert all(a["banner"] and a["ai_comment"] for a in flow)

    def test_broadcast_accident_paths(self, rt):
        ba = rt.broadcast_accident_flow()            # 无人解锁心声 → 广播体操
        assert "体操" in ba or "无料可播" in ba
        rt.unlock_memory("char_02", "memory_fix")    # 解锁 → 白名单可播
        ba2 = rt.broadcast_accident_flow(candidates=["char_02"])
        assert isinstance(ba2, str) and ba2.strip()

    def test_collectibles_three_fish(self, rt):
        rt.collect_flow("fish_01", act_no=1)
        rt.collect_flow("fish_02", act_no=2)
        c3 = rt.collect_flow("fish_03", act_no=3)
        assert c3.get("all_collected")
        assert "隐藏语音" in (c3.get("show") or "") and "看山Bot" in c3["show"]


# ================================================================ T7 侦探报告
class TestT7Report:
    def test_badges_deterministic(self, rt):
        rep = rt.report_flow(ending_key="kanshan_still_mountain",
                             boss_accused_success=True,
                             highlights=["第 3 轮你率先戳穿监控删除"])
        assert "看山还是山" in rep["badges"]
        assert "看山还是山" in rep["report_text"]

    def test_empty_report_ok(self, rt):
        rep2 = rt.report_flow()
        assert rep2["badges"] == [] and rep2["report_text"].strip()


# ================================================================ T8 头条竞标链
class TestT8Headline:
    def test_headline_flow_engine_backed(self, rt):
        hf = rt.headline_flow("player:1", faction="truth", amount=2)
        assert "头条位开标" in hf["host_line"] and bool(hf["result_line"])


# ================================================================ T9 阵营铁律 + LLM 兜底
class _Boom:
    def chat(self, *a, **k):
        raise RuntimeError("net down")


class TestT9Hardening:
    def test_final_verdict_strips_faction(self, rt):
        fv = rt.show.final_verdict(
            {"ending": "truth_revealed", "title": "真相大白"},
            [{"name": "知之者", "faction": "pollution", "counseled": False}])
        assert "pollution" not in fv and fv.strip()

    def test_llm_failure_fallback_never_blank(self, rt_ro):
        sd2 = ShowtimeDirector(_Boom())
        seg = rt_ro.show.segments
        stats = rt_ro.collect_stats()
        mm = sd2.memo(3, {"loc_hint": "监控室", "kw_hint": "删除"})
        ashow = sd2.achievement_show(seg.achievements[0], "夜行侦探")
        pieces = (
            sd2.glitch_rewrite("x"), sd2.glitch_banner(),
            sd2.bet_settle(True), sd2.red_alert("沉底君"),
            sd2.rescue_success("沉底君"), sd2.broadcast_accident(),
            sd2.headline_auction(), sd2.radio_station(2, 3),
            sd2.anti_fraud_theater(1), sd2.antifraud_settle(True),
            mm["memo_text"], ashow["ai_comment"],
            sd2.detective_report(stats), sd2.final_verdict({}, []),
            sd2.collectibles_show({"voice_lines": ["样本语音一句"],
                                   "boss_reveal_extra": "加播一句"}),
            sd2.memo_render({"text": "【档案局备忘录】有人在「监控」的方向查过什么。",
                             "hint": "监控"}, "assist")["memo_text"])
        assert all(bool(str(x).strip()) for x in pieces)
        assert ashow["banner"] == seg.achievements[0]["banner"]


# ================================================================ T10 花名/暗拍/拼图/陈词
class TestT10MegaFlows:
    def test_headline_pool_and_match(self, rt_ro):
        seg = rt_ro.show.segments
        assert len(seg.headline_pool) == 22
        assert all(kws for _, kws, _ in seg.headline_pool)
        name, _intro = seg.pick_headline("简历写着码农，日常 debug")
        assert name == "调试人生司司长"

    def test_bridge_headline_from_m4_pool(self, tmp_path):
        rt10 = AgentRuntime(llm=LLMClient(cache_dir=tmp_path / "c"),
                            player_headline_text="简历写着码农，日常 debug")
        assert rt10.player_headline == "调试人生司司长"

    def test_stealth_share_puzzle_closing(self, tmp_path):
        rt10 = AgentRuntime(llm=LLMClient(cache_dir=tmp_path / "c"))
        ph = rt10.stealth_photo_flow("监控室", "监控")
        assert ph.get("ok") is True
        assert rt10.counters["photos_shared"] == 1
        assert rt10.ae._stats.get("photos_shared", 0) >= 1
        sh = rt10.share_photo_flow(ph["photo"]["photo_id"], claim="我觉得这是天外来物")
        assert sh is not None and sh["claim"] == "我觉得这是天外来物"
        assert sh["photo"]["fact"] != ""
        # 拼图对质（先攒 ≥2 篡改点）
        rt10.unlock_memory("char_02", "memory_fix")
        rt10.unlock_memory("char_03", "memory_fix")
        pu = rt10.puzzle_flow("char_02", rt10.memory.puzzle_answer("char_02"))
        assert pu.get("correct") is True and rt10.memory.puzzle_wins() >= 1
        assert "拼图" in pu["show"]
        pu_bad = rt10.puzzle_flow("char_02",
                                  list(reversed(rt10.memory.puzzle_answer("char_02"))))
        assert pu_bad.get("correct") is False and pu_bad["show"]
        # 陈词登记 + 锤票 → 结算演出
        rt10.closing_statement("player:1", "我全程只做对了一件事：没乱传谣。")
        rt10.hammer_vote_flow("danmaku:热评君", "player:1", weight=2)
        assert rt10.ae._stats.get("hammered_votes:player:1", 0) >= 2
        cs = rt10.closing_settle()
        assert cs.get("most_hammered") == "player:1" and cs["show"]
        # 暗房大师路径：photos_shared>=3 → resolver 徽章入报告
        rt10.record_event("photos_shared", inc=2)
        rep3 = rt10.report_flow()
        assert "暗房大师" in rep3["badges"]


# ================================================================ T11 M2 心声窃听器
class TestT11HeartQuiz:
    def test_bank_structure(self, rt_ro):
        seg = rt_ro.show.segments
        assert len(seg.heart_quiz_bank) == 10
        assert sum(1 for q in seg.heart_quiz_bank if q["tier"] == "open") == 6
        assert sum(1 for q in seg.heart_quiz_bank if q["tier"] == "full") == 4
        assert all(q["said"] and q["heart"] and q["answer"]
                   for q in seg.heart_quiz_bank)

    def test_open_pool_desensitized(self, rt):
        pool_open = rt.memory_puzzle_pool(tier="open")
        assert len(pool_open) == 6
        assert all(q["tier"] == "open" for q in pool_open)
        assert not any("47 个号" in q["heart"] for q in pool_open)

    def test_full_pool_login_only(self, rt):
        assert len(rt.memory_puzzle_pool(tier="full")) == 4

    def test_judge_and_settle_copy(self, rt):
        pool = rt.memory_puzzle_pool(tier="open")
        q1 = pool[0]
        ok = rt.heart_quiz_flow(q1, q1["answer"])
        bad = rt.heart_quiz_flow(q1, "A" if q1["answer"] != "A" else "C")
        assert ok["correct"] is True and "窃听成功" in ok["show"]
        assert bad["correct"] is False and "嘴硬版" in bad["show"]
        from agents.segments_lib import SegmentsLibrary
        seg = SegmentsLibrary(SCENARIO_DIR / "scripts")
        assert "接下来一整幕" in seg.heart_quiz_settle["outro"]
