"""showtime v2 自测：按 segments 文件演出生成 + achievements.md 横幅文案模板成就。

用法：python _showtime_test.py
覆盖：D 组文案池解析 / P1 演出位（抽风重写·押注结算·急诊红灯·抢救·心声广播事故·头条竞标）/
P2 演出位（广播台·反诈三幕·快问快答 20 题库）/ 成就 23 项判定+横幅演出 /
防卡死备忘录 / 侦探报告 / LLM 失败兜底。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bridge import AgentRuntime
from llm_client import LLMClient
from segments_lib import SegmentsLibrary
from showtime import ShowtimeDirector

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, bool(ok), note))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  | {note}" if note else ""))


_TMP = Path(tempfile.mkdtemp(prefix="showtime_test_cache_"))
rt = AgentRuntime(llm=LLMClient(cache_dir=_TMP))
seg = rt.show.segments

# ------------------------------------------------ T0 segments 资产解析
check("T0 抽风池 8 对原句→重写句", len(seg.glitch_pairs) == 8
      and all("【惩罚" in b for b, _ in seg.glitch_pairs),
      f"pairs={len(seg.glitch_pairs)}")
check("T0 快问快答题库 20 题（题干/选项/答案/吐槽齐全）",
      len(seg.quiz_bank) == 20 and all(
          q["question"] and q["options"] and q["answer_text"] and q["taunt"]
          for q in seg.quiz_bank), f"bank={len(seg.quiz_bank)}")
check("T0 成就库 24 项（D v2；条件 JSON+横幅文案+分享卡）",
      len(seg.achievements) >= 23 and all(
          a["banner"] and a["share_line"] for a in seg.achievements),
      f"ach={len(seg.achievements)}")
check("T0 头条话题池 8 条 / 广播台播报 6 条 / 反诈三幕",
      len(seg.headline_topics) == 8 and len(seg.radio_reports) == 6
      and len(seg.antifraud_acts) == 3,
      f"topics={len(seg.headline_topics)} radio={len(seg.radio_reports)} "
      f"acts={len(seg.antifraud_acts)}")

# ------------------------------------------------ T1 成就判定（achievements.md 条件）
check("T1 空局零成就", rt.achievements_flow() == [])
rt.record_event("chat_keyword", value="看山，关门")        # ach_huanxingci（彩蛋，引擎自判）
rt.record_event("ending", value="ending_kanshan")           # ach_zhenshan（金，ending 类）
fresh = rt.achievements_flow()
ids = {a["id"] for a in fresh}
check("T1 彩蛋/结局成就命中（横幅文案=achievements.md 模板）",
      {"ach_huanxingci", "ach_zhenshan"} <= ids
      and all(a["banner"] and a["share_line"] and a["ai_comment"] for a in fresh)
      and any("谁教的它这么没礼貌" in a["banner"]
              for a in fresh if a["id"] == "ach_huanxingci"),
      str(sorted(ids)))

# 去重
check("T1 成就去重（不重复解锁）", rt.achievements_flow() == [])

# 数值条件（上层注账）：quiz 10/10 → ach_kuaidan；listen_full 3 → ach_fangzhe
rt.record_event("quiz_score", inc=10)
rt.record_event("listen_full", target="char_06", inc=3)
fresh2 = rt.achievements_flow()
ids2 = {a["id"] for a in fresh2}
check("T1 数值成就（快问快答满分/防折叠斗士）",
      {"ach_kuaidan", "ach_fangzhe"} <= ids2, str(sorted(ids2)))

# ------------------------------------------------ T2 P1 演出位（segments_p1.md）
g = rt.show.glitch_rewrite("【惩罚：围观鱼干一分钟】")
check("T2 抽风重写= D 组重写句", "认真搜证" in g, g[:40])
g3 = rt.show.glitch_rewrite("【惩罚：向折叠区怨灵道歉】")
check("T2 沉底君抢答句", "该道歉已被折叠" in g3, g3[:40])
check("T2 故障播报池", "叮——" in rt.show.glitch_banner())
check("T2 押注结算句", "眼光毒辣" in rt.show.bet_settle(True)
      and "押错了" in rt.show.bet_settle(False))
ra = rt.show.red_alert("沉底君")
check("T2 急诊红灯播报（模板填 NPC 名）", "沉底君" in ra and "红灯" in ra, ra[:40])
check("T2 沉底君红灯状态词", "双折叠" in rt.show.npc_red_state("沉底君"))
rs = rt.show.rescue_success("沉底君")
check("T2 抢救成功+专属追加句", "抢救成功" in rs and "该发言已被展开" in rs)
ba = rt.show.broadcast_accident("路人甲")
check("T2 心声广播事故（D v2 白名单池，无案情词）",
      any(w in ba for w in ("泡面", "工牌", "鱼干的味道", "给妈打电话", "生日便签", "生日"))
      and "删除" not in ba and "监控" not in ba, ba[:40])
ha = rt.show.headline_auction()
check("T2 头条竞标主持词（模板填池内话题）",
      "头条位开标" in ha and any(t in ha for t, _ in seg.headline_topics), ha[:44])
check("T2 头条开标结果句", "截图存证" in rt.show.headline_result("pollution"))

# ------------------------------------------------ T3 P2 演出位（segments_p2.md）
rd = rt.show.radio_station(round_no=3, clue_count=5)
check("T3 广播台整点播报池", "广播台" in rd, rd[:44])
tpl = next(t for t in seg.radio_reports if "第 N 小时" in t)
filled = tpl.replace("第 N 小时", "第 3 小时").replace("线索 N 条", "线索 5 条")
check("T3 整点播报封控模板填空", "第 3 小时" in filled and "线索 5 条" in filled)
spot = rt.show.radio_station(round_no=1, spotlight="流量酱")
check("T3 点播名场面（可指定）", "卡路里" in spot)
a1 = rt.show.anti_fraud_theater(1)
a2 = rt.show.anti_fraud_theater(2)
a3 = rt.show.anti_fraud_theater(3)
check("T3 反诈三幕（各含话术拆解）",
      all("话术拆解" in x for x in (a1, a2, a3))
      and "查无此猫" in a1 and "截止时间" in a2 and "设备指纹" in a3)
check("T3 反诈结算句", "反诈学分" in rt.show.antifraud_settle(True))

# 快问快答：题库出题、选项乱序但答案可判、10 题不重复
qs = [rt.show.quick_quiz() for _ in range(10)]
check("T3 快问快答 20 题库出题（乱序+答案可判+不重复）",
      all(q["source"] == "segments_bank" for q in qs)
      and all(q["options"][q["answer_index"]] == q["answer_text"] for q in qs)
      and len({q["question"] for q in qs}) == 10,
      f"unique={len({q['question'] for q in qs})}")

# ------------------------------------------------ T4 quiz_flow / refute_flow 计分链
issued = rt.quiz_flow()                                     # 出题（不计分）
q = issued["quiz"]
r_ok = rt.quiz_flow(quiz=q, answer_index=q["answer_index"])
r_bad = rt.quiz_flow(quiz=q, answer_text="绝不可能是这个答案")
check("T4 quiz_flow 出题/判定/计分", issued["correct"] is None and q is not None
      and r_ok["correct"] is True and rt.counters["quiz_score"] >= 1
      and r_bad["correct"] is False)

ref = rt.refute_flow("player:1", "post_008", "kc_01")       # B 组验证过的成功对
check("T4 refute_flow 联动（成功→streak/fake_exposed 计数）",
      isinstance(ref, dict) and ref.get("ok") is True
      and rt.counters["fake_exposed"] >= 1
      and rt.counters["refute_success_streak"] >= 1
      and "antifraud_theater" in ref, f"ok={ref.get('ok')}")

# ------------------------------------------------ T5 防卡死备忘录（difficulty.py assist 档消费）
# v3：方向词与预算全部由引擎 DifficultyDirector.memo_for 确定性给出
rt.last_hit_round = 0
rt.stage_machine._round = 4
grad = rt.act_settled()                        # stuck_rounds>=2 → assist 档
check("T5 幕结算→assist 档落地", grad["gradient"] == "assist"
      and grad["memo_budget"] == 2, str(grad))
m1 = rt.memo_flow()
check("T5 备忘录（引擎方向词+AI 润色保留 hint）",
      m1 is not None and m1["source"] == "difficulty_engine"
      and m1["hint"] and m1["hint"] in m1["memo_text"], str(m1)[:60])
m2 = rt.memo_flow()                            # assist 预算第 2 条
check("T5 assist 档预算 2 条/幕", m2 is not None)
check("T5 预算耗尽 → 不生成", rt.memo_flow() is None)
rt.difficulty.on_act_settled({"clue_count": 12, "coverage": 0.9, "stuck_rounds": 0})
rt.difficulty.apply(rt.evidence, rt.opinion)
check("T5 hard 档 → 备忘录禁用", rt.difficulty.gradient == "hard"
      and rt.memo_flow() is None)

# ------------------------------------------------ T6 引擎权威成就 + 白名单广播 + 收集品
rt6 = AgentRuntime(llm=LLMClient(cache_dir=_TMP))   # 新实例（T1 已消费部分成就）
rt6.record_event("chat_keyword", value="看山，关门")
rt6.ae.evaluate(None)                          # 引擎全量判定（确定性、幂等）
check("T6 AchievementEngine 权威判定接入",
      "ach_huanxingci" in rt6.ae.unlocked_ids(), str(rt6.ae.unlocked_ids()[:6]))
flow = rt6.achievements_flow()
check("T6 achievements_flow 消费引擎解锁（横幅演出结构）",
      any(a["id"] == "ach_huanxingci" for a in flow)
      and all(a["banner"] and a["ai_comment"] for a in flow),
      str([a["id"] for a in flow]))

ba = rt6.broadcast_accident_flow()             # 无人解锁心声 → 广播体操
check("T6 心声广播事故（引擎白名单，未解锁→体操）",
      "体操" in ba or "无料可播" in ba, ba[:40])
rt6.unlock_memory("char_02", "memory_fix")     # 解锁一个心声 → 白名单可播
ba2 = rt6.broadcast_accident_flow(candidates=["char_02"])
check("T6 解锁后白名单播报或拦截（双路径均演出）",
      isinstance(ba2, str) and bool(ba2.strip()), ba2[:40])

c1 = rt6.collect_flow("fish_01", act_no=1)
c2 = rt6.collect_flow("fish_02", act_no=2)
c3 = rt6.collect_flow("fish_03", act_no=3)
check("T6 收集品三件集齐 → 隐藏语音演出",
      c3.get("all_collected") and "隐藏语音" in (c3.get("show") or "")
      and "看山Bot" in c3["show"], str(c3.get("show", ""))[:40])

# ------------------------------------------------ T7 侦探报告 v2（resolver.achievements 消费）
rep = rt6.report_flow(ending_key="kanshan_still_mountain",
                      boss_accused_success=True,
                      highlights=["第 3 轮你率先戳穿监控删除"])
check("T7 徽章确定性进报告（badges 原样）",
      "看山还是山" in rep["badges"] and "看山还是山" in rep["report_text"],
      str(rep["badges"]))
rep2 = rt.report_flow()
check("T7 空参报告徽章墙可空", rep2["badges"] == []
      and bool(rep2["report_text"].strip()))

# ------------------------------------------------ T8 头条竞标链（引擎裁决）
hf = rt6.headline_flow("player:1", faction="truth", amount=2)
check("T8 头条竞标链（主持词+引擎成交+结果句）",
      "头条位开标" in hf["host_line"] and bool(hf["result_line"]),
      hf["result_line"][:36])

# ------------------------------------------------ T9 faction 铁律（CONTRACTS §四.4）
fv = rt6.show.final_verdict({"ending": "truth_revealed", "title": "真相大白"},
                            [{"name": "知之者", "faction": "pollution",
                              "counseled": False}])
check("T9 终局陈词输出不含阵营字段（防御剥离）",
      "pollution" not in fv and bool(fv.strip()), fv[:36])


class _Boom:
    def chat(self, *a, **k):
        raise RuntimeError("net down")


stats = rt.collect_stats()
sd2 = ShowtimeDirector(_Boom())
mm = sd2.memo(3, {"loc_hint": "监控室", "kw_hint": "删除"})
ashow = sd2.achievement_show(seg.achievements[0], "夜行侦探")
check("T9 LLM 失败 → D 组文案/预写兜底不断流",
      all(bool(str(x).strip()) for x in (
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
                           "hint": "监控"}, "assist")["memo_text"]))
      and ashow["banner"] == seg.achievements[0]["banner"])

# ------------------------------------------------ T10 暗拍/拼图/陈词 → ae.record + M4 花名
check("T10 M4 花名池 22 枚（关键词+介绍齐全）",
      len(seg.headline_pool) == 22
      and all(kws for _, kws, _ in seg.headline_pool),
      f"pool={len(seg.headline_pool)}")
hl_name, _intro = seg.pick_headline("简历写着码农，日常 debug")
check("T10 headline 关键词匹配（码农→调试人生司司长）",
      hl_name == "调试人生司司长", hl_name)

rt10 = AgentRuntime(llm=LLMClient(cache_dir=_TMP),
                    player_headline_text="简历写着码农，日常 debug")
check("T10 bridge 花名取自 M4 池", rt10.player_headline == "调试人生司司长",
      rt10.player_headline)

ph = rt10.stealth_photo_flow("监控室", "监控")
check("T10 暗拍链：引擎拍照 + ae.record(photos_shared)",
      ph.get("ok") is True and rt10.counters["photos_shared"] == 1
      and rt10.ae._stats.get("photos_shared", 0) >= 1,
      str(ph.get("photo", {}).get("photo_id")))
sh = rt10.share_photo_flow(ph["photo"]["photo_id"], claim="我觉得这是天外来物")
check("T10 照片分享（原文+声称并存）", sh is not None
      and sh["claim"] == "我觉得这是天外来物" and sh["photo"]["fact"] != "")

rt10.unlock_memory("char_02", "memory_fix")    # 记忆修复 → 产出篡改点（拼图发起成本）
rt10.unlock_memory("char_03", "memory_fix")    # 攒够 ≥2 个篡改点
pu = rt10.puzzle_flow("char_02", rt10.memory.puzzle_answer("char_02"))
check("T10 拼图对质（正确序列→胜→ae.record）",
      pu.get("correct") is True and rt10.memory.puzzle_wins() >= 1
      and "拼图" in pu["show"], pu["show"][:36])
pu_bad = rt10.puzzle_flow("char_02", list(reversed(rt10.memory.puzzle_answer("char_02"))))
check("T10 拼图排错 → DM 锐评演出", pu_bad.get("correct") is False
      and bool(pu_bad["show"]))

rt10.closing_statement("player:1", "我全程只做对了一件事：没乱传谣。")
rt10.hammer_vote_flow("danmaku:热评君", "player:1", weight=2)
check("T10 陈词登记+锤票（ae.record hammered_votes:target）",
      rt10.ae._stats.get("hammered_votes:player:1", 0) >= 2)
cs = rt10.closing_settle()
check("T10 陈词结算演出（最想锤的人宣布）",
      cs.get("most_hammered") == "player:1" and bool(cs["show"]))

# 暗房大师路径：photos_shared>=3 → resolver.achievements 徽章
rt10.record_event("photos_shared", inc=2)      # 凑满 3 次
rep3 = rt10.report_flow()
check("T10 resolver 徽章消费（暗房大师入报告）",
      "暗房大师" in rep3["badges"], str(rep3["badges"]))

# ------------------------------------------------ T11 M2 心声窃听器（F memory-puzzle 数据源）
check("T11 M2 题库 10 题（open 6 / full 4，said/heart/答案齐全）",
      len(seg.heart_quiz_bank) == 10
      and sum(1 for q in seg.heart_quiz_bank if q["tier"] == "open") == 6
      and sum(1 for q in seg.heart_quiz_bank if q["tier"] == "full") == 4
      and all(q["said"] and q["heart"] and q["answer"] for q in seg.heart_quiz_bank),
      f"bank={len(seg.heart_quiz_bank)}")
pool_open = rt.memory_puzzle_pool(tier="open")
check("T11 open 脱敏池过滤（full 题零泄漏）",
      len(pool_open) == 6 and all(q["tier"] == "open" for q in pool_open)
      and not any("47 个号" in q["heart"] for q in pool_open),
      f"open={len(pool_open)}")
pool_full = rt.memory_puzzle_pool(tier="full")
check("T11 full 池仅登录局内使用", len(pool_full) == 4, f"full={len(pool_full)}")
q1 = pool_open[0]
r_ok = rt.heart_quiz_flow(q1, q1["answer"])
r_bad = rt.heart_quiz_flow(q1, "A" if q1["answer"] != "A" else "C")
check("T11 心声窃听判定+D 组结算句",
      r_ok["correct"] is True and "窃听成功" in r_ok["show"]
      and r_bad["correct"] is False and "嘴硬版" in r_bad["show"],
      r_ok["show"][:36])
check("T11 热身关收尾句（第二幕开场）",
      "接下来一整幕" in seg.heart_quiz_settle["outro"])

# ------------------------------------------------ 汇总
shutil.rmtree(_TMP, ignore_errors=True)
failed = [r for r in RESULTS if not r[1]]
print("\n" + "=" * 56)
print(f"SHOWTIME v3 TEST {'ALL PASS' if not failed else 'FAILED'}: "
      f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
for name, ok, note in failed:
    print(f"  FAIL {name} | {note}")
sys.exit(1 if failed else 0)
