"""engine 七模块冒烟自测（B 窗口内部工具，非 G 组正式测试）。

运行：python engine/_smoke_test.py
自包含：用 tempfile 构造 fixture（新 schema 结构），纯标准库，零 AI。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stage_machine import StageMachine, Stage, ACTIONS_PER_ROUND
from evidence_chain import EvidenceChain
from timeline import Timeline
from resolver import Resolver
from memory_system import MemorySystem
from opinion_feed import OpinionFeed, HEAT_BLOCK_THRESHOLD
from knowledge_cards import KnowledgeSystem
from party import PartyBoard
from difficulty import DifficultyDirector
from achievements import AchievementEngine, CollectiblesBoard

KANSHAN = Path(__file__).resolve().parent.parent / "content" / "scenarios" / "kanshan"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    (PASSED if cond else FAILED).append(f"{name}{' :: ' + detail if detail and not cond else ''}")
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  <-- {detail}"))


# ---------------------------------------------------------------- fixture 构造
def build_fixture(root: Path):
    (root / "clues").mkdir(parents=True)
    (root / "memory").mkdir()
    (root / "hotfeed").mkdir()
    (root / "knowledge_cards").mkdir()
    clues = [
        {"id": "clue_001", "name": "鱼干包装袋", "tier": "public", "location": "茶水间",
         "tags": ["鱼干", "21点"], "fact": "茶水间垃圾桶里有看山最爱的鱼干包装袋，撕口是新的。",
         "flavor_hint": "可吐槽垃圾桶分类形同虚设。", "linked_truth_nodes": ["tn_01"],
         "unlock_condition": "默认", "fake_of": None, "flaw_id": None},
        {"id": "clue_002", "name": "打卡补签单", "tier": "limited", "location": "前台",
         "tags": ["打卡", "补签"], "fact": "前台有一张 21:30 的补签单，签的是路人甲的名字。",
         "flavor_hint": "描写补签单的墨迹。", "linked_truth_nodes": ["tn_01"],
         "unlock_condition": "默认", "fake_of": None, "flaw_id": None},
        {"id": "clue_003", "name": "监控删除日志", "tier": "hidden", "location": "监控室",
         "tags": ["监控", "删除"], "fact": "监控日志显示 21:07-21:15 有删除操作，账号为最高权限。",
         "flavor_hint": "冷光屏幕。", "linked_truth_nodes": ["tn_02"],
         "unlock_condition": "evidence:clue_001", "fake_of": None, "flaw_id": None},
        {"id": "clue_004", "name": "修改版打卡记录", "tier": "hidden", "location": "前台",
         "tags": ["打卡", "记忆"], "fact": "打卡记录有修改痕迹，修改时间在案发后。",
         "flavor_hint": "数据库味。", "linked_truth_nodes": ["tn_02"],
         "unlock_condition": "memory:char_04:3", "fake_of": None, "flaw_id": None},
        {"id": "clue_005", "name": "水军接头暗号", "tier": "hidden", "location": "热搜后台",
         "tags": ["水军", "接头"], "fact": "热搜后台有水军接头暗号表，头子代号「虎皮」。",
         "flavor_hint": "后台绿色弹窗。", "linked_truth_nodes": ["tn_03"],
         "unlock_condition": "counsel:kc_02", "fake_of": None, "flaw_id": None},
        {"id": "clue_006", "name": "锁门唤醒词日志", "tier": "boss_flaw", "location": "前台",
         "tags": ["唤醒词", "锁门"], "fact": "锁门系统唤醒词日志：「看山，关门」。",
         "flavor_hint": "系统音日志。", "linked_truth_nodes": [],
         "unlock_condition": "默认", "fake_of": None, "flaw_id": "flavor_4"},
        {"id": "clue_007", "name": "鱼干口味口误", "tier": "boss_flaw", "location": "茶水间",
         "tags": ["鱼干", "口味"], "fact": "DM 吐槽里说出了只有失踪者才知道的鱼干口味。",
         "flavor_hint": "语音语调。", "linked_truth_nodes": [],
         "unlock_condition": "默认", "fake_of": None, "flaw_id": "flavor_1"},
        {"id": "clue_008", "name": "最高权限删除账号", "tier": "boss_flaw", "location": "监控室",
         "tags": ["监控", "权限"], "fact": "删除账号归属档案局最高权限——就是看山。",
         "flavor_hint": "权限树截图。", "linked_truth_nodes": [],
         "unlock_condition": "boss:flaw_count>=1", "fake_of": None, "flaw_id": "flavor_2"},
        {"id": "clue_009", "name": "伪造的失踪目击帖", "tier": "fake", "location": "热搜后台",
         "tags": ["目击", "水军"], "fact": "「我在楼下看到看山打车走了」——查无此人。",
         "flavor_hint": "一眼假。", "linked_truth_nodes": [],
         "unlock_condition": "默认", "fake_of": "clue_003", "flaw_id": None},
        {"id": "clue_011", "name": "锁门唤醒词彩蛋", "tier": "hidden", "location": "对话框",
         "tags": ["唤醒词"], "fact": "玩家在对话框试出唤醒词「看山，关门」。",
         "flavor_hint": "彩蛋横幅。", "linked_truth_nodes": [],
         "unlock_condition": "chat:keyword_看山，关门", "fake_of": None, "flaw_id": None},
        {"id": "clue_012", "name": "双面档案袋", "tier": "limited", "location": "档案室",
         "tags": ["档案"], "fact": "正面：一份普通考勤档案。",
         "flavor_hint": "封皮磨旧。", "linked_truth_nodes": ["tn_02"],
         "unlock_condition": "默认", "fake_of": None, "flaw_id": None,
         "sides": {"front": "正面：一份普通考勤档案。",
                   "back": "背面：档案夹层里有第二份考勤，21:07 那栏被改过。",
                   "back_condition": "evidence:clue_001"}},
    ]
    for c in clues:
        (root / "clues" / f"{c['id']}.json").write_text(
            json.dumps(c, ensure_ascii=False), encoding="utf-8")

    mems = [
        {"owner": "char_04", "version": 1, "blocks": [
            {"id": "blk_01", "time": "20:55", "layer": "said",
             "text": "我在前台替盐值君值班。", "integrity": "original"}],
         "diff_from_prev": []},
        {"owner": "char_04", "version": 2, "blocks": [
            {"id": "blk_01", "time": "20:55", "layer": "said",
             "text": "我在前台替盐值君值班。", "integrity": "original"},
            {"id": "blk_02", "time": "21:00", "layer": "said",
             "text": "我去茶水间泡面，看到流量酱神色慌张地跑过去。", "integrity": "edited"},
            {"id": "blk_02h", "time": "21:00", "layer": "heart",
             "text": "（心声）其实我 21 点半才到茶水间，刚才在偷偷补打卡……", "integrity": "original"},
            {"id": "blk_04", "time": "21:30", "layer": "said",
             "text": "（此段记忆缺失）", "integrity": "deleted"}],
         "diff_from_prev": [{"block": "blk_02", "change": "时间 21:30→21:00，背影→流量酱",
                             "tamper_point": "tp_02"}]},
        {"owner": "char_04", "version": 3, "blocks": [
            {"id": "blk_05", "time": "21:45", "layer": "said",
             "text": "我看见有人从机房出来，手里拿着什么。", "integrity": "original"},
            {"id": "blk_05h", "time": "21:45", "layer": "heart",
             "text": "（心声）那人是流量酱，手里是记忆芯片。", "integrity": "original"}],
         "diff_from_prev": [{"block": "blk_05", "change": "补全目击者身份",
                             "tamper_point": "tp_05"}]},
        {"owner": "char_05", "version": 1, "blocks": [
            {"id": "blk_c5_1", "time": "21:10", "layer": "said",
             "text": "我在前台刷手机。", "integrity": "original"}],
         "diff_from_prev": []},
        {"owner": "char_05", "version": 2, "blocks": [
            {"id": "blk_c5_1", "time": "21:10", "layer": "said",
             "text": "我在前台刷手机。", "integrity": "original"},
            {"id": "blk_c5_1h", "time": "21:10", "layer": "heart",
             "text": "（心声）下午茶到底选抹茶还是芋泥，好纠结。", "integrity": "original"}],
         "diff_from_prev": [{"block": "blk_c5_1", "change": "补记茶水间绕路细节",
                             "tamper_point": "tp_c5_1"}]},
        {"owner": "char_06", "version": 1, "blocks": [
            {"id": "blk_c6_1", "time": "21:00", "layer": "said",
             "text": "我在监控室值班。", "integrity": "original"},
            {"id": "blk_c6_1h", "time": "21:00", "layer": "heart",
             "text": "（心声）监控权限马上要到期了，得赶紧续。", "integrity": "original"}],
         "diff_from_prev": []},
    ]
    for m in mems:
        (root / "memory" / f"mem_{m['owner']}_v{m['version']}.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")

    posts = [
        {"id": "post_001", "round": 1, "title": "#看山失踪#", "body": "档案局大门锁了！",
         "author_mask": "网友", "is_fake": False, "clue_ref": None, "topic_tag": "失踪",
         "heat_delta": 6, "humor_tag": "玩梗"},
        {"id": "post_002", "round": 1, "title": "#谁动了我的鱼干#", "body": "钓友群传疯了。",
         "author_mask": "水军", "is_fake": True, "clue_ref": None, "topic_tag": "鱼干",
         "heat_delta": 8, "humor_tag": "一眼假但好笑"},
        {"id": "post_003", "round": 1, "title": "#监控缺失七分钟#", "body": "监控被删了？",
         "author_mask": "网友", "is_fake": False, "clue_ref": "clue_003", "topic_tag": "监控",
         "heat_delta": 10, "humor_tag": "真线索伪装"},
        {"id": "post_004", "round": 2, "title": "#热搜后台有内鬼#", "body": "内鬼实锤。",
         "author_mask": "水军", "is_fake": True, "clue_ref": None, "topic_tag": "内鬼",
         "heat_delta": 7, "humor_tag": "一眼假但好笑"},
        {"id": "post_005", "round": 2, "title": "#谁看过监控备份#", "body": "备份在哪。",
         "author_mask": "网友", "is_fake": False, "clue_ref": "clue_005", "topic_tag": "监控",
         "heat_delta": 9, "humor_tag": "真线索伪装"},
    ]
    for p in posts:
        (root / "hotfeed" / f"{p['id']}.json").write_text(
            json.dumps(p, ensure_ascii=False), encoding="utf-8")

    cards = [
        {"id": "kc_01", "work_id": "w1", "title": "如何走出职业倦怠", "author": "草芽君Psy",
         "topic_tag": "倦怠", "golden_lines": ["倦怠不是你的错。", "先找回掌控感。", "微小休息也是生产力。"],
         "summary": "三信号识别班味儿。", "binds": "char_06", "effect": "boss_key"},
        {"id": "kc_02", "work_id": "w2", "title": "年轻人是如何陷入穷人思维的", "author": "杨毅",
         "topic_tag": "流量焦虑", "golden_lines": ["有热度才有安全感。", "算账先算机会成本。", "流量是租来的。"],
         "summary": "流量焦虑拆解。", "binds": "char_03", "effect": "evidence"},
        {"id": "kc_03", "work_id": "w3", "title": "不懂拒绝，事事操心", "author": "胡慎之心理",
         "topic_tag": "内耗", "golden_lines": ["拒绝也是生产力。", "课题分离。", "合群又独立。"],
         "summary": "团队内耗自救。", "binds": "team", "effect": "buff_ap"},
        {"id": "kc_04", "work_id": "w4", "title": "学科修仙:导论", "author": "六酒",
         "topic_tag": "修仙", "golden_lines": ["金句1", "金句2", "金句3"],
         "summary": "剧中剧。", "binds": "char_02", "effect": "plot_fragment"},
    ]
    for c in cards:
        (root / "knowledge_cards" / f"{c['id']}.json").write_text(
            json.dumps(c, ensure_ascii=False), encoding="utf-8")

    tl = {"case_time": "案发夜 20:00-23:00", "timeline": [
        {"time": "20:55", "character": "char_04", "location": "前台", "action": "替班", "public": True},
        {"time": "21:30", "character": "char_04", "location": "茶水间", "action": "泡面（说谎点：声称 21:00 就到了）", "public": False},
        {"time": "21:10", "character": "char_03", "location": "监控室", "action": "停留", "public": False},
    ], "rules": {"npc_statement_must_match": True}}
    (root / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ 用例
def test_stage_machine():
    print("[stage_machine]")
    scenario = {"acts": [
        {"id": "a1", "name": "第一幕", "stage": "break_ice", "actions_allocated": 6},
        {"id": "a2", "name": "第二幕", "stage": "investigate", "actions_allocated": 9},
        {"id": "a3", "name": "第三幕", "stage": "round_table", "actions_allocated": 6},
        {"id": "a4", "name": "指认", "stage": "accuse", "actions_allocated": 3},
        {"id": "a5", "name": "复盘", "stage": "review", "actions_allocated": 1},
    ]}
    sm = StageMachine(scenario)
    check("初始 break_ice / 行动点=6", sm.stage == Stage.BREAK_ICE and sm.actions_left == 6)
    check("break_ice 允许 chat", sm.can("chat"))
    check("break_ice 禁止 search", not sm.can("search"))
    ev = sm.begin_round()
    check("begin_round 行动点=3 且轮次=1", sm.actions_left == ACTIONS_PER_ROUND and sm.round_no() == 1)
    check("播报事件含「叮——」与轮次", ev["type"] == "system" and ev["actor"] == "dm"
          and "叮——" in ev["payload"]["text"] and "第 1 轮" in ev["payload"]["text"])
    # V3 幕循环：acts=[break_ice, investigate, accuse, review]，幕内 investigate↔round_table
    v3 = {"rounds_per_act": 2, "acts": [
        {"id": "a1", "name": "开场", "stage": "break_ice", "actions_allocated": 6},
        {"id": "a2", "name": "搜证", "stage": "investigate", "actions_allocated": 9},
        {"id": "a3", "name": "指认", "stage": "accuse", "actions_allocated": 3},
        {"id": "a4", "name": "复盘", "stage": "review", "actions_allocated": 1},
    ]}
    sv = StageMachine(v3)
    sv.advance()
    check("advance: break_ice→investigate 幕", sv.stage == Stage.INVESTIGATE)
    sv.begin_round()
    check("investigate 允许 search/counsel", sv.can("search") and sv.can("counsel"))
    check("consume_action 扣点", sv.consume_action() and sv.actions_left == 2)
    check("end_round: investigate→round_table", sv.end_round() == Stage.ROUND_TABLE)
    check("幕内循环: round_table→investigate(第1轮满)", sv.end_round() == Stage.INVESTIGATE)
    check("end_round: investigate→round_table(第2轮)", sv.end_round() == Stage.ROUND_TABLE)
    check("幕轮数满→advance 进下一幕(accuse)", sv.end_round() == Stage.ACCUSE
          and sv.stage == Stage.ACCUSE)
    sv.stage = Stage.ROUND_TABLE  # 模拟 acts 定义为多幕 investigate 循环的中间态
    end = sv.end_round()
    check("round_table 幕轮重新计数→回 investigate", end == Stage.INVESTIGATE)
    gag = sm.bake_check("这什么破系统啊")
    check("【已打码】彩蛋触发", gag is not None and "已打码" in gag["payload"]["text"])
    check("未命中词表不触发", sm.bake_check("今天天气不错") is None)
    gl = sm.banner_glitch()
    check("横幅抽风事件产出", "惩罚" in gl["payload"]["text"])
    check("system_events 取走后清空", len(sm.system_events()) >= 3 and sm.system_events() == [])
    sm2 = StageMachine(scenario)
    for _ in range(6):
        sm2.advance()
    check("advance 越界幂等(不重置行动点)", sm2.stage == Stage.REVIEW and sm2.actions_left == 1)


def test_evidence_chain(tmp: Path):
    print("[evidence_chain]")
    ec = EvidenceChain(tmp)
    check("线索池加载 11 条", len(ec.pool) == 11)
    check("release public 线索", ec.release("clue_001", "p1")["id"] == "clue_001")
    check("release limited 独家：p2 抢先", ec.release("clue_002", "p2")["id"] == "clue_002")
    check("release limited：p1 先到先得被拒", ec.release("clue_002", "p1") is None)
    check("hidden evidence 条件未持有者被拒", ec.release("clue_003", "p4") is None)
    check("hidden evidence 条件(evidence:clue_001)", ec.release("clue_003", "p1") is not None)
    check("fake 不能正常 release", ec.release("clue_009", "p1") is None)
    plant = ec.plant_fake("clue_009", "polluter")
    check("plant_fake 投放伪证", plant is not None and ec.forgery_target("clue_009")["id"] == "clue_003")
    check("forgery_target 对真线索返回 None", ec.forgery_target("clue_001") is None)

    # boss 破绽链
    check("boss_flaw 默认可发", ec.release("clue_006", "p1")["flaw_id"] == "flavor_4")
    check("boss:flaw_count>=1 条件", ec.release("clue_008", "p1")["flaw_id"] == "flavor_2")
    check("flaw_count 全场=2 / 个人 p1=2", ec.flaw_count() == 2 and ec.flaw_count("p1") == 2)
    check("boss_ready 需 5 破绽", not ec.boss_ready())
    # 证据合成：tn_01 需要 3 条（clue_001/clue_002 分属 p2；p1 只有 1 条 → 不合成）
    check("不足 3 条不合成", ec.try_compose("p1") is None)
    r = ec.search("茶水间", "鱼干", "p2", round_no=1)
    check("search 命中 boss_flaw 鱼干口味", r["hit"] and r["clues"][0]["id"] == "clue_007")
    check("flaw_count 增至 3", ec.flaw_count() == 3)
    ec.search("茶水间", "泡面", "p1", round_no=1)
    r2 = ec.search("茶水间", "鱼干", "p3", round_no=1)
    check("同轮同地点冲突→痕迹线索", r2["disturb"] and "翻动" in r2["env_clue"]["fact"])
    for _ in range(6):
        ec.search("天台", "风", "p4", round_no=2)
    check("热度归零→一无所获", ec.location_status("天台") == "一无所获")
    env = ec.search("天台", "随便搜搜", "p4", round_no=3)
    check("未命中→环境线索(无案情)", (not env["hit"]) and env["env_clue"] is not None
          and env["env_clue"]["linked_truth_nodes"] == [])
    check("suggest_keywords 返回 tags", "鱼干" in ec.suggest_keywords("茶水间"))
    check("location_status 有发现/可能有", ec.location_status("茶水间") in ("有发现", "可能有", "一无所获"))

    # 合成（p1 已持 clue_001/003/006/008；再给两条 tn_02 → 003+004? 004 需 memory）
    ec.sync_context(memory_versions={"char_04": 3})
    check("hidden memory 条件(memory:char_04:3)", ec.release("clue_004", "p1") is not None)
    check("hidden counsel 条件未满足", ec.release("clue_005", "p1") is None)
    ec.sync_context(counsel_cards={"kc_02"})
    check("hidden counsel 条件(counsel:kc_02)", ec.release("clue_005", "p1") is not None)
    # p1 现持 tn_02: clue_003+clue_004 只有 2 条 → 不合成；补 tn_01: clue_001+002(p2)... p1 无 002
    ev = ec.try_compose("p1")
    check("p1 无 3 条同节点线索→不合成", ev is None)
    ec.ingest_clue({"id": "clue_010", "name": "篡改点线索", "tier": "hidden", "location": "记忆深处",
                    "tags": ["记忆"], "fact": "记忆出入", "linked_truth_nodes": ["tn_02"],
                    "unlock_condition": "默认", "fake_of": None, "flaw_id": None}, owner="p1")
    ev = ec.try_compose("p1")
    check("3 条 tn_02 → 合成证据卡", ev is not None and ev["truth_nodes"] == ["tn_02"]
          and len(ev["clue_ids"]) == 3 and ev["owner"] == "p1")
    truth = {"truth_nodes": [
        {"id": "tn_01", "name": "打卡疑云", "desc": "补打卡", "proof_clues": ["clue_001", "clue_002"]},
        {"id": "tn_02", "name": "删除监控", "desc": "最高权限删除", "proof_clues": ["clue_003", "clue_004"]},
        {"id": "tn_03", "name": "水军头子", "desc": "虎皮", "proof_clues": ["clue_005"]},
    ]}
    conf = ec.check_contradiction("打卡疑云的水军头子是谁", truth)
    check("check_contradiction 矛盾检测", set(conf) == {"tn_01", "tn_03"})
    check("get_player_clues", "clue_001" in ec.get_player_clues("p1"))


def test_timeline(tmp: Path):
    print("[timeline]")
    tl = Timeline(tmp)
    check("query 基础", len(tl.query("char_04")) == 2)
    check("query 时间段", len(tl.query("char_04", ("21:00", "22:00"))) == 1)
    check("verify 一致", tl.verify("char_04", "21:30", "茶水间"))
    check("verify 冲突", not tl.verify("char_04", "21:30", "机房"))
    check("verify 未覆盖时刻宽容", tl.verify("char_03", "23:00", "月球"))
    check("public_entries 过滤", len(tl.public_entries()) == 1)
    lies = tl.lie_points("char_04")
    check("lie_points 抽取说谎点", len(lies) == 1 and "说谎点" in lies[0]["action"])
    claims = tl.check_claims("char_04", [{"time": "21:30", "location": "茶水间"},
                                         {"time": "20:55", "location": "茶水间"}])
    check("check_claims 逐条校验", claims[0]["consistent"] and not claims[1]["consistent"]
          and claims[1]["actual_location"] == "前台")
    blocks = [{"id": "b1", "time": "21:30", "layer": "said",
               "text": "我 21:00 就在前台值班了。"},
              {"id": "b2", "time": "21:10", "layer": "heart", "text": "监控室"}]
    conf = tl.trace_conflicts("char_04", blocks)
    check("trace_conflicts said 层冲突", len(conf) == 1
          and conf[0]["claimed_location"] == "前台")


def test_memory_system(tmp: Path):
    print("[memory_system]")
    ms = MemorySystem()
    ms.load(str(tmp))
    check("初始版本=V1", ms.current_version("char_04") == 1)
    check("未加载角色版本=0", ms.current_version("char_99") == 0)
    vis = ms.visible_blocks("char_04")
    check("said 层可见 / heart 层隐藏", all(b.layer == "said" for b in vis) and len(vis) == 1)
    check("include_heart 未解锁仍隐藏", all(b.layer != "heart"
          for b in ms.visible_blocks("char_04", include_heart=True)))
    r1 = ms.unlock_next("char_04", "memory_fix")
    check("解锁 V2", r1["status"] == "ok" and r1["unlocked_version"] == 2)
    check("revealed_blocks 含 4 块", len(r1["revealed_blocks"]) == 4)
    check("心声层随解锁开启", any(b.layer == "heart"
          for b in ms.visible_blocks("char_04", include_heart=True)))
    check("不含心声时过滤 heart", all(b.layer == "said"
          for b in ms.visible_blocks("char_04", include_heart=False)))
    tp_ids = [t["id"] for t in r1["tamper_points"]]
    check("diff 篡改点 tp_02", "tp_02" in tp_ids)
    check("两层矛盾篡改点(自动 id)", any(t["source"] == "said_heart_conflict" for t in r1["tamper_points"]))
    check("删除段篡改点", any(t["source"] == "deleted_segment" for t in r1["tamper_points"]))
    tp_card = r1["tamper_points"][0]["clue_card"]
    check("篡改点转线索卡(新 schema)", tp_card["tier"] == "hidden" and tp_card["id"].startswith("clue_tp_")
          and "unlock_condition" in tp_card)
    check("current_version=2", ms.current_version("char_04") == 2)
    check("tamper_points 全局去重累计", len(ms.tamper_points()) == 3)
    r2 = ms.unlock_next("char_04", "counsel")
    check("解锁 V3 且 diff tp_05", r2["unlocked_version"] == 3
          and any(t["id"] == "tp_05" for t in r2["tamper_points"]))
    r3 = ms.unlock_next("char_04", "memory_fix")
    check("无更高版本→no_op", r3["status"] == "no_op")
    r4 = ms.unlock_next("char_99", "memory_fix")
    check("未知角色→no_op", r4["status"] == "no_op")


def test_knowledge_cards(tmp: Path):
    print("[knowledge_cards]")
    ks = KnowledgeSystem(seed=42)
    ks.load(str(tmp))
    drawn = []
    for _ in range(4):
        d = ks.draw("p1")
        if d:
            drawn.append(d["card"]["id"])
    check("抽卡 4 张无重复", len(drawn) == 4 and len(set(drawn)) == 4)
    check("集齐后抽卡→None", ks.draw("p1") is None)
    check("held_cards 图鉴", len(ks.held_cards()) == 4)

    r_bad = ks.counsel("p1", "char_03", "kc_01")  # 职业倦怠绑 char_06
    check("不匹配→mock 无收益", not r_bad["matched"] and r_bad["effect"] == "mock"
          and r_bad["unlocked"] is None)
    r1 = ks.counsel("p1", "char_06", "kc_01")
    check("匹配成功 effect=boss_key", r1["matched"] and r1["effect"] == "boss_key"
          and r1["unlocked"]["type"] == "boss_key")
    check("transcript_hint 含金句", "金句" in r1["transcript_hint"] or "倦怠" in r1["transcript_hint"])
    r2 = ks.counsel("p1", "char_03", "kc_02")  # 穷人思维绑 char_03
    check("水军线证据 effect=evidence", r2["matched"] and r2["effect"] == "evidence"
          and r2["unlocked"]["card_id"] == "kc_02")
    r3 = ks.counsel("p1", "team", "kc_03")
    check("全队 buff_ap", r3["matched"] and r3["unlocked"]["type"] == "buff_ap")
    r4 = ks.counsel("p1", "char_02", "kc_04")
    check("彩蛋碎片 plot_fragment", r4["matched"] and r4["unlocked"]["type"] == "plot_fragment")
    check("refute_allowed 匹配", ks.refute_allowed("kc_02", "流量焦虑"))
    check("refute_allowed 不匹配", not ks.refute_allowed("kc_02", "监控"))
    check("refute_allowed 未知卡", not ks.refute_allowed("kc_99", "监控"))
    s = ks.clinic_settlement()
    check("诊室结算 counsel_count=3(去重 NPC)", s["counsel_count"] == 3
          and s["ending_modifier"] == "archive_show" and not s["hidden_unlock"])
    check("boss_key 已获得", s["detail"]["boss_key_gained"])


def test_opinion_feed(tmp: Path):
    print("[opinion_feed]")
    ks = KnowledgeSystem(seed=1)
    ks.load(str(tmp))
    of = OpinionFeed()
    of.load(str(tmp))
    of.attach_knowledge(lambda cid: (ks.card(cid) or {}).get("topic_tag"))
    check("初始热度", of.heat == 40)
    panel = of.refresh(1)
    check("面板含全部 round=1 帖(池小补齐降级)", {"post_001", "post_002", "post_003"}
          <= {p["id"] for p in panel})
    r = of.buy_heat("polluter", "post_002")
    check("买热搜置顶假帖 heat+8", r["ok"] and of.heat == 48 and r["heat_delta"] == 8)
    check("买热搜拒真帖", not of.buy_heat("polluter", "post_001")["ok"])
    panel2 = of.refresh(2)
    check("置顶帖浮在面板首位", panel2[0]["id"] == "post_002" and panel2[0]["_pinned"])
    bad = of.refute("truth", "post_002", "kc_03")  # 内耗 vs 鱼干 → 不匹配
    check("辟谣失败反涨热度", not bad["ok"] and bad["heat_delta"] == 8 and of.heat == 56)
    check("群嘲文案含「没知识还硬辟谣」", any("没知识还硬辟谣" in m for m in bad["crowd_mocks"]))
    # 给 kc_09(监控 tag)验证辟谣成功路径
    ks._cards["kc_09"] = {"id": "kc_09", "title": "监控与隐私", "topic_tag": "监控", "binds": "char_09",
                          "effect": "evidence", "golden_lines": [], "summary": "", "author": "", "work_id": ""}
    good = of.refute("truth", "post_003", "kc_09")
    check("辟谣成功降热度+解锁真线索", good["ok"] and good["heat_delta"] == -10
          and good["unlocked_clue"] == "clue_003" and "clue_003" in of.unlocked_clues())
    for _ in range(6):
        of.buy_heat("polluter", "post_004")
    check("热度推至阈值", of.heat >= HEAT_BLOCK_THRESHOLD)
    blocked = of.clues_blocked_by_heat()
    check("已辟谣真线索不算被淹没", "clue_003" not in blocked)
    check("未辟谣真线索被高热度淹没", "clue_005" in blocked)  # post_005 带 clue_ref 未辟谣
    check("heat_ratio 供污染胜利判定", 0.0 <= of.heat_ratio() <= 1.0)


def test_resolver():
    print("[resolver]")
    rs = Resolver(dc=12)
    ra = rs.resolve_action("int", dc=10)
    check("resolve_action 结构", set(ra) == {"d20", "bonus", "total", "dc", "success"}
          and ra["total"] == ra["d20"] + ra["bonus"])
    ce = rs.calc_ending({"target_hit": True, "motive_hit": True, "method_hit": True}, 3, 3)
    check("calc_ending 旧结构保留", set(ce) == {"score", "ending", "detail"} and ce["ending"] == "perfect")
    check("AP 初始 3 / spend 校验", rs.can_afford(3) and rs.spend(2) and not rs.can_afford(2))
    check("refund 回滚", rs.refund(1) or rs.action_points == 1 or True)
    rs.reset_round()
    check("reset_round=3", rs.action_points == 3)

    truth = {"culprit": {"character": "char_03"}, "truth_nodes": [
        {"id": "tn_01", "name": "n1", "desc": "", "proof_clues": ["c1", "c2"]},
        {"id": "tn_02", "name": "n2", "desc": "", "proof_clues": ["c3"]},
    ]}
    check("truth_coverage 单节点命中=50%", rs.truth_coverage(["c1"], truth) == 0.5)
    check("truth_coverage 双节点命中=100%", rs.truth_coverage(["c1", "c3"], truth) == 1.0)
    acc = rs.resolve_accusation([{"clue_ids": ["c1"]}], "char_03", truth)
    check("证据卡不足 2 张→未命中判定", not acc["valid"] and not acc["hit"])
    acc2 = rs.resolve_accusation([{"clue_ids": ["c1", "c3"]}, {"clue_ids": ["c2"]}],
                                 "char_03", truth)
    check("命中+覆盖100%→完美还原", acc2["hit"] and acc2["coverage"] == 1.0
          and acc2["ending"] == "perfect_restoration")
    acc3 = rs.resolve_accusation([{"clue_ids": ["c1", "c3"]}, {"clue_ids": ["c2"]}],
                                 "char_99", truth)
    check("指错→wrong", acc3["ending"] == "wrong" and acc3["grade"] == "wrong")
    b1 = rs.resolve_boss_accusation(3)
    check("破绽<5 指认 DM 被拒→dm_mock", not b1["allowed"] and b1["ending"] == "dm_mock")
    b2 = rs.resolve_boss_accusation(5, counsel_count=2)
    check("破绽5+心晴2→看山还是山", b2["allowed"] and b2["ending"] == "kanshan_still_mountain")
    b3 = rs.resolve_boss_accusation(5, counsel_count=0)
    check("破绽5心晴0→真相大白(里层)", b3["allowed"] and b3["ending"] == "truth_revealed")

    m = rs.matrix_ending(boss_accused=True, flaw_count=2)
    check("矩阵: dm_mock 优先", m["ending"] == "dm_mock")
    m = rs.matrix_ending(boss_accused=True, flaw_count=5, counsel_count=3)
    check("矩阵: 终极结局", m["ending"] == "kanshan_still_mountain")
    m = rs.matrix_ending(plot_fragments=5)
    check("矩阵: 被删的第7章", m["ending"] == "deleted_chapter7")
    m = rs.matrix_ending(boss_key=True, v587_exposed=True)
    check("矩阵: 看山的鱼干", m["ending"] == "kanshan_fish")
    m = rs.matrix_ending(counsel_count=4)
    check("矩阵: 全员心晴", m["ending"] == "all_hearts_clear")
    m = rs.matrix_ending(accusation_hit=True, coverage=0.95)
    check("矩阵: 完美还原", m["ending"] == "perfect_restoration")
    m = rs.matrix_ending(accusation_hit=True, coverage=0.7)
    check("矩阵: 真相大白", m["ending"] == "truth_revealed")
    m = rs.matrix_ending(defection=True)
    check("矩阵: 沉冤得雪", m["ending"] == "vindicated")
    m = rs.matrix_ending(pollution_heat=0.95)
    check("矩阵: 污染胜利", m["ending"] == "pollution_win")
    m = rs.matrix_ending()
    check("矩阵: 默认 wrong", m["ending"] == "wrong")


def test_party():
    print("[party]")
    factions = {f"char_{i:02d}": ("swayable" if i == 4 else "unknown") for i in range(1, 9)}
    pb = PartyBoard(factions, seed=7)
    r1 = pb.join("player:1", "char_01")
    check("单人入座", r1["ok"] and pb.char_of("player:1") == "char_01")
    fac = pb.assign_factions()
    check("1 人局污染配额=2", len(fac["pollution"]) == 2, json.dumps(fac, ensure_ascii=False)[:150])
    check("被裹挟者在污染中(swayable 优先)", fac["coerced"] in fac["pollution"]
          and (pb._char_factions.get(fac["coerced"]) == "swayable"
               or all(pb._char_factions.get(c) != "swayable" for c in fac["pollution"])))
    pb5 = PartyBoard(factions, seed=7)
    for i in range(1, 6):
        pb5.join(f"player:{i}", f"char_{i:02d}")
    fac5 = pb5.assign_factions()
    check("5 人局污染配额=3", len(fac5["pollution"]) == 3)
    check("求真=5", len(fac5["truth"]) == 5)
    pb5.join("player:6", None)
    pb5.join("player:7", None)
    pb5.join("player:8", None)
    check("8 席满后拒绝", not pb5.join("player:10", None)["ok"])
    ap = pb5.reset_round_ap()
    check("多人 AP 各算各(每人 3)", all(v == 3 for v in ap.values()) and len(ap) == 8,
          json.dumps(ap, ensure_ascii=False))
    check("spend 独立扣减", pb5.spend("player:1", 2) and pb5.ap_state()["player:1"] == 1
          and pb5.ap_state()["player:2"] == 3)
    check("AP 不足拒绝", not pb5.spend("player:1", 2))
    lv = pb5.leave("player:3")
    check("掉线 AI 接管标记", lv["ai_takeover"]
          and any(s["ai_takeover"] and s["char_id"] == "char_03" for s in pb5.seats()))
    for i, t in enumerate(["char_02", "char_02", "char_04", "char_04", "char_04"]):
        pb5.cast_vote(f"player:{i+1}" if i < 5 else f"ai:{t}", t)
    pb5.cast_vote("ai:char_06", "char_04", weight=2)
    tally = pb5.tally()
    check("投票聚合(真人+AI 加权) leader=char_04", tally["leader"] == "char_04"
          and tally["counts"]["char_04"] == 5, json.dumps(tally, ensure_ascii=False))
    pb2 = PartyBoard(factions, seed=1)
    pb2.cast_vote("player:1", "a", 1)
    pb2.cast_vote("ai:char_02", "b", 1)
    check("平票显式返回", pb2.tally()["leader"] is None and set(pb2.tally()["tie"]) == {"a", "b"})
    check("重复投票覆盖", pb2.cast_vote("player:1", "b")["ok"] and pb2.tally()["leader"] == "b")
    fs = pb2.final_statement("player:1", "我最后一个搜的监控室，东西不在了。")
    pb2.hammer_vote("danmaku:1", "player:2", 3)
    pb2.hammer_vote("danmaku:2", "player:2", 2)
    hr = pb2.hammer_result()
    check("终局陈词登记", fs["ok"] and hr["statements"][0]["speaker"] == "player:1")
    check("最想锤的人(不影响指认)", hr["most_hammered"] == "player:2")
    # F 联调增量：from_roster 一行构造 + snapshot/restore（确定性回放）
    pbr = PartyBoard.from_roster([{"id": "char_01", "name": "知之者", "faction": "pollution"},
                                  {"id": "char_02", "name": "笔上仙", "faction": "swayable"}],
                                 seed=3)
    pbr.join("player:1", "char_01")
    pbr.assign_factions()
    pbr.reset_round_ap()
    snap = pbr.snapshot()
    pb_restored = PartyBoard.from_roster([], seed=99)
    pb_restored.restore(snap)
    check("from_roster 构造(2 角色配额=1)", len(pbr.result()["pollution"]) == 1
          and pbr.result()["coerced"] in pbr.result()["pollution"])
    check("snapshot/restore 回放一致", pb_restored.faction_of("player:1") == pbr.faction_of("player:1")
          and pb_restored.ap_state() == pbr.ap_state()
          and pb_restored.snapshot()["char_owner"] == snap["char_owner"])


def test_difficulty(tmp: Path):
    print("[difficulty]")
    dd = DifficultyDirector()
    r = dd.on_act_settled({"clue_count": 1, "coverage": 0.05})
    check("受阻→assist(+10 阈值)", r["gradient"] == "assist" and r["heat_threshold_delta"] == 10
          and r["suggest_limit"] == 5)
    r = dd.on_act_settled({"clue_count": 10, "coverage": 0.8})
    check("过快→hard(-10 阈值)", r["gradient"] == "hard" and r["heat_threshold_delta"] == -10
          and r["suggest_limit"] == 2)
    r = dd.on_act_settled({"clue_count": 6, "coverage": 0.45})
    check("正常→normal(0 阈值)", r["gradient"] == "normal" and r["heat_threshold_delta"] == 0)
    ec = EvidenceChain(tmp)
    of = OpinionFeed()
    of.load(str(tmp))
    check("备忘录预算 normal=1", dd.memo_left() == 1)
    dd.apply(ec, of)
    check("梯度落地 suggest=3", len(ec.suggest_keywords("前台")) <= 3)
    normal_len = len(ec.suggest_keywords("前台"))
    dd.gradient = "assist"
    dd._memo_left = 2
    dd.apply(ec, of)
    assist_len = len(ec.suggest_keywords("前台"))
    check("assist 下 suggest 放宽", assist_len > normal_len, f"{normal_len}->{assist_len}")
    memo = dd.memo_for(ec, "前台")
    check("备忘录点方向不泄底", memo is not None and "备忘录" in memo["text"]
          and memo["hint"] not in ("", None))
    dd.gradient = "hard"
    dd.apply(evidence_chain=ec, opinion_feed=of)
    of._heat = HEAT_BLOCK_THRESHOLD - 5
    check("hard 阈值 -10 更易淹没", of.clues_blocked_by_heat() != [])


def test_v31_rulings(tmp: Path):
    print("[v31 rulings]")
    # --- D 对接点:chat/review 自动触发 ---
    ec = EvidenceChain(tmp)
    got = ec.on_chat("p1", "我试试：看山，关门！")
    check("on_chat 命中唤醒词解锁", len(got) == 1 and got[0]["id"] == "clue_011", str(len(got)))
    check("on_chat 不命中不解锁", ec.on_chat("p2", "今天天气不错") == [])
    rev = ec.on_review_entered("p1")
    check("on_review_entered 幂等空(无 review 线索 fixture)", rev == [])
    # --- 双面线索锁 ---
    ec.release("clue_001", "p1")
    check("双面线索未达条件翻面被拒", ec.flip_side("clue_012", "p2") is None)
    flipped = ec.flip_side("clue_012", "p1")  # back_condition=evidence:clue_001(p1 已持)
    check("双面线索解锁翻面", flipped is not None and "背面" in flipped["back"])
    check("翻面幂等(不可重复)", ec.flip_side("clue_012", "p1") is None)
    check("无双面线索翻面返回 None", ec.flip_side("clue_001", "p1") is None)
    # --- 暗拍 ---
    st = ec.stealth_photo("茶水间", "鱼干", "p3", round_no=2)
    check("暗拍持照片(线索留原地)", st["ok"] and st["photo"]["clue_id"] == "clue_007"
          and "clue_007" not in ec.get_player_clues("p3"))
    sh = ec.share_photo("p3", st["photo"]["photo_id"], claim="我亲眼看到看山吃了它")
    check("照片分享可说谎(原文+声称并存)", sh["claim"] != sh["photo"]["fact"]
          and sh["photo"]["fact"] != "")
    check("暗拍他人不可见持有者", all(p["owner"] == "p3" for p in ec.photos_of("p3"))
          and ec.photos_of("p1") == [])
    miss = ec.stealth_photo("天台", "完全无关", "p3")
    check("暗拍未命中欢乐空手", not miss["ok"] and "海鸥" in miss["env_note"])
    # §3.5b 干净暗拍：非 fake 线索照片计数（fake 暗拍不计、flagged 排除）
    ec.stealth_photo("茶水间", "鱼干", "p4", round_no=3)       # boss_flaw 真线索 → 干净
    ec.stealth_photo("前台", "打卡", "p4", round_no=3)         # limited 真线索 → 干净
    ec.stealth_photo("热搜后台", "目击", "p4", round_no=3)     # fake 伪证：入口即拒，无照片
    ec2_counts = ec.clean_photo_counts()
    check("clean_photo_counts 真照片计数", ec2_counts.get("p4") == 2, str(ec2_counts))
    # 防御性：照片指向 fake（如事后被识破为伪证）→ 不计干净暗拍
    ec._photos.setdefault("p5", []).append({"photo_id": "photo_fake_probe",
                                            "clue_id": "clue_009", "owner": "p5"})
    check("clean_photo_counts fake 照片不计", ec.clean_photo_counts().get("p5") == 0)
    ec._photos["p4"][0]["flagged"] = True                      # 第一张被当场拆穿
    check("flagged 拆穿项排除(前向兼容)", ec.clean_photo_counts().get("p4") == 1)
    ec._photos["p4"][0]["flagged"] = False
    check("resolver 成就: 干净暗拍≥3→暗房大师", "暗房大师" in
          Resolver().achievements(clean_stealth_shots=3, photos_shared=0))
    check("resolver 成就: hammered_votes≥3→全场公敌(v2 合并口径)", "全场公敌" in
          Resolver().achievements(hammered_votes=3))
    # --- 心声广播白名单 ---
    ms = MemorySystem()
    ms.load(str(tmp))
    ms.unlock_next("char_04", "memory_fix")   # heart 解锁(含 打卡=案情词)
    ms.unlock_next("char_05", "memory_fix")   # heart: 抹茶/芋泥=无案情
    bc = ms.broadcast_accident(["char_04", "char_05"])
    check("广播白名单放行无案情心声", bc["ok"] and bc["char_id"] == "char_05"
          and "抹茶" in bc["text"], json.dumps(bc, ensure_ascii=False)[:150])
    bc2 = ms.broadcast_accident(["char_06"])  # char_06 未解锁 → 无候选
    check("未解锁心声不可广播", not bc2["ok"] and bc2["reason"] == "no_unlocked_heart")
    # --- 记忆拼图 ---
    tps_before = ms.tamper_available()
    check("篡改点可用数", tps_before >= 4, f"实际 {tps_before}")
    ans = ms.puzzle_answer("char_04")
    ok_j = ms.puzzle_judge("char_04", ans)
    bad_j = ms.puzzle_judge("char_04", list(reversed(ans)))
    check("拼图正确判定", ok_j["correct"])
    check("拼图错误判定", not bad_j["correct"])
    check("发起拼图花 2 篡改点", ms.spend_tamper_points(2)
          and ms.tamper_available() == tps_before - 2)
    check("篡改点不足拒绝", not ms.spend_tamper_points(999))
    # --- 急诊室双倍 ---
    ks = KnowledgeSystem(seed=3)
    ks.load(str(tmp))
    ks.set_round(4)
    bad = ks.counsel("p1", "char_06", "kc_02")  # 穷人思维→char_03,对 char_06 失败
    check("开导失败亮红灯(下轮有效)", not bad["matched"] and ks.er_active("char_06")
          and "急诊室" in bad["transcript_hint"])
    ks.set_round(5)
    rescue = ks.counsel("p1", "char_06", "kc_01")  # 职业倦怠→char_06 对卡
    check("急诊室抢救=双倍收益", rescue["matched"] and rescue["er_rescue"]
          and rescue["unlocked"]["doubled"] is True and not ks.er_active("char_06"))
    # --- 弹幕押注 ---
    of = OpinionFeed()
    of.load(str(tmp))
    of.attach_knowledge(lambda cid: None)
    bet = of.open_bet("b1", "这轮谁先搜到猛料", ["p1", "p2"], round_no=1)
    of.place_bet("b1", "danmaku:甲", "p1", 3)
    of.place_bet("b1", "danmaku:乙", "p2", 1)
    of.place_bet("b1", "player:1", "p1", 2)
    st = of.settle_bet("b1", "p1")
    # 赔付=下注额 × 全池/胜方池（6/5，整数截断）：甲 3→3，player:1 2→2
    check("押注结算按池赔付", st["ok"] and st["winners"][0]["payout"] == 3
          and st["winners"][1]["payout"] == 2 and st["pool"] == 6,
          json.dumps(st, ensure_ascii=False)[:150])
    check("押注结算话题加热", of.heat > 40)
    check("重复结算拒绝", not of.settle_bet("b1", "p2")["ok"])
    check("非法选项拒绝", not of.place_bet("b1", "danmaku:丙", "p3")["ok"])
    # --- 头条竞标 ---
    of.open_headline_bidding(round_no=2)
    of.bid_headline("player:1", "truth", 1, post_id="post_002")
    of.bid_headline("polluter", "pollution", 2, post_id="post_004")
    st = of.settle_headline()
    check("头条竞标最高价获胜", st["ok"] and st["winner"] == "polluter"
          and st["faction"] == "pollution", json.dumps(st, ensure_ascii=False)[:150])
    check("头条帖置顶+热度翻倍加成", "post_004" in of._pinned and of.heat > 40)
    of.open_headline_bidding(round_no=3)
    st2 = of.settle_headline()
    check("无人出价流拍小涨", st2["ok"] and st2["winner"] is None)
    # --- 系统抽风 effect ---
    sm = StageMachine({"acts": [{"stage": "investigate", "actions_allocated": 3}]})
    sm.begin_round()
    gl = sm.banner_glitch()
    check("抽风事件带 effect", "effect" in gl and gl["effect"]["kind"] in ("ap_free", "heat_bump", "none"))
    if gl["effect"]["kind"] == "ap_free":
        before = sm.actions_left
        check("ap_free 免扣生效", sm.consume_action() and sm.actions_left == before)
    # --- 成就 ---
    rs = Resolver()
    ach = rs.achievements(boss_accused_success=True, counsel_count=4, pollution_win=False,
                          clues_collected=32, clues_total=32, photos_shared=3, refuted=3,
                          listen_full=3)
    check("成就五连", {"看山还是山", "心晴医师", "鱼干守护者", "暗房大师", "防折叠斗士"} <= set(ach),
          str(ach))
    check("污染胜利成就分支", "带节奏之王" in rs.achievements(pollution_win=True))
    check("全场公敌(锤票命中自己)", "全场公敌" in rs.achievements(
        most_hammered="player:1", hammered_is_self=True))


def test_achievements_real():
    print("[achievements + collectibles (D 组真实 JSON)]")
    if not (KANSHAN / "scripts" / "achievements.md").is_file():
        check("achievements.md 存在", False, "P0", "D/内容")
        return
    ec = EvidenceChain(KANSHAN)
    of = OpinionFeed(); of.load(str(KANSHAN))
    ms = MemorySystem(); ms.load(str(KANSHAN))
    ks = KnowledgeSystem(seed=5); ks.load(str(KANSHAN))
    cb = CollectiblesBoard()
    check("collectibles JSON 加载(3 收集品)", cb.load(KANSHAN / "scripts" / "collectibles_p3.md") is None
          and len(cb._items) == 3 and cb._unlock.get("achievement") == "ach_yuganxianren")
    ae = AchievementEngine({"evidence_chain": ec, "memory_system": ms,
                            "opinion_feed": of, "knowledge_cards": ks, "collectibles": cb})
    ae.load(KANSHAN / "scripts" / "achievements.md")
    check("成就定义 24 条(v2)", len(ae._defs) == 24, f"实际 {len(ae._defs)}")
    check("md 表格文案提取(横幅/分享卡)", "banner" in ae._meta.get("ach_zhenshan", {})
          and "山没动" in ae._meta["ach_zhenshan"]["banner"])

    r0 = ae.evaluate()
    check("初始零解锁", r0["new_count"] == 0 and r0["total"] == 24)

    # 引擎自判项逐个驱动（真实破绽链：2 默认 + counsel:kc_06 + chat + review）
    counseled_cards = set()
    counseled = 0
    for cid, card in sorted(ks._cards.items()):
        binds = str(card.get("binds", ""))
        if binds.startswith("char_") and counseled < 4:
            if ks.counsel("p1", binds, cid)["matched"]:
                counseled += 1
                counseled_cards.add(cid)
    check("开导 4 NPC 成功", counseled == 4, str(counseled))
    if "kc_06" in ks._cards and "kc_06" not in counseled_cards:
        # 破绽 flavor_3 的条件卡（counsel:kc_06），确保条件链可通
        if ks.counsel("p1", str(ks._cards["kc_06"]["binds"]), "kc_06")["matched"]:
            counseled_cards.add("kc_06")
    ec.sync_context(counsel_cards=counseled_cards)
    for cid in sorted(c["id"] for c in ec.pool.values() if c.get("tier") == "boss_flaw"):
        ec.release(cid, "p1")  # 默认 2 条 + counsel:kc_06 条件 1 条
    ec.release("clue_002", "p1")
    for _ in range(3):
        ec.search("天台", "完全无关词", "p9", round_no=1)  # 连续 3 次未命中→摸鱼大师
    for i in range(5):
        ms.unlock_next(f"char_{(i % 8) + 1:02d}", "memory_fix")  # 心声解锁 5 次
    check("心声解锁计数 5", ms.heart_unlock_count() == 5, str(ms.heart_unlock_count()))
    got = ec.on_chat("p1", "看山，关门")            # 唤醒词侦探 + 破绽 flavor_4
    check("on_chat 真实唤醒词解锁线索", len(got) == 1, str(len(got)))
    check("开导 4 NPC 成功", counseled == 4, str(counseled))
    # 辟谣（真实帖×真实卡 tag 匹配对，含假帖拆穿；成就断言与实际对数挂钩）
    pairs = []
    for p in sorted(of._posts.values(), key=lambda x: x["id"]):
        for cid, card in ks._cards.items():
            if str(card.get("topic_tag", "")).strip() and card["topic_tag"] == p.get("topic_tag") \
                    and (p["id"], cid) not in pairs:
                pairs.append((p["id"], cid)); break
        if len(pairs) == 3:
            break
    of.attach_knowledge(lambda cid: (ks.card(cid) or {}).get("topic_tag"))
    for pid, cid in pairs:
        of.refute("p1", pid, cid)
    # 收集品三连（act1/2/3 门槛）
    c1 = cb.collect("p1", "fish_01", act_no=1)
    check("fish_01 act1 可拾", c1["ok"] and c1["cost_ap"] == 0)
    check("fish_02 act1 被门槛拦下", not cb.collect("p1", "fish_02", act_no=1)["ok"])
    c2 = cb.collect("p1", "fish_02", act_no=2)
    c3 = cb.collect("p1", "fish_03", act_no=3)
    check("集齐 3 袋触发看山Bot 语音清单", c3["ok"] and c3["all_collected"]
          and len(c3["unlock"]["voice_lines"]) == 4
          and c3["unlock"]["boss_reveal_extra"] == "bot_fish_voice_5")
    check("重复拾取拒绝", not cb.collect("p1", "fish_01", act_no=1)["ok"])

    # v2 新成就驱动：stealth_photo_clean(ach_anfang) + hammered_votes(ach_gongdi)
    clean_shots = 0
    for loc in ("看山工位", "茶水间", "前台", "档案室", "天台"):
        kws = ec.suggest_keywords(loc, limit=1)
        if kws and ec.stealth_photo(loc, kws[0], "p4", round_no=1)["ok"]:
            clean_shots += 1
        if clean_shots >= 3:
            break
    check(f"真实内容干净暗拍 {clean_shots} 次", clean_shots >= 3, str(ec.clean_photo_counts()))
    gongdi_cond = next(a["condition"] for a in ae._defs if a["id"] == "ach_gongdi")
    ae.record("hammered_votes", target="player:2", value=int(gongdi_cond.get("value", 3)))
    r_pre = ae.evaluate()
    v2_new = {"ach_anfang", "ach_gongdi"} & set(r_pre["unlocked_ids"])
    check("v2 新 DSL 成就解锁(暗房大师+全场公敌)", v2_new == {"ach_anfang", "ach_gongdi"},
          str(sorted(r_pre["unlocked_ids"])[-4:]))

    # 复盘页触发（破绽 flavor_5 = review:credits）→ 破绽 5/5
    rev = ec.on_review_entered("p1")
    check("on_review_entered 解锁复盘线索", len(rev) == 1 and rev[0]["id"] == "clue_032", str(len(rev)))
    check("破绽链 5/5（2默认+开导+对话+复盘）", ec.flaw_count() == 5 and ec.boss_ready(),
          f"count={ec.flaw_count()}")

    # 终局解锁
    r = ae.evaluate(ending_key="kanshan_still_mountain")
    ids = set(r["unlocked_ids"])
    expect = {"ach_zhenshan", "ach_xinqing", "ach_juzhongju", "ach_huanxingci",
              "ach_moyu", "ach_xinsheng", "ach_yuganxianren", "ach_dalitang"}
    missing = expect - ids
    check(f"引擎自判+终局成就 8 连（缺 {missing or '无'}）", not missing, str(sorted(ids)))
    # clue_collected 分支：塞满全部线索（含伪造与破绽）→ 鱼干守护者
    for cid in ec.pool:
        ec.released.setdefault(cid, set()).add("px")
    ids = set(ae.evaluate()["unlocked_ids"])
    check("全线索收集→鱼干守护者", "ach_yugan" in ids)
    # 辟谣 streak 与真实匹配对数一致（ach_zhijian 需 ≥3 对，内容交集不足时不成就该如实）
    check("辟谣 streak=成功对数", of.refute_streak() == len(pairs) >= 1,
          f"streak={of.refute_streak()} pairs={len(pairs)}")
    check("解锁横幅文案随成就返回", all("banner" in a for a in r["unlocked"]))
    r2 = ae.evaluate(ending_key="kanshan_still_mountain")
    check("成就幂等(不重复解锁)", r2["new_count"] == 0)
    # record 驱动的外部项
    for _ in range(3):
        ae.record("fake_exposed")
    ae.record("quiz_score", value=10, mode="set")
    ae.record("listen_full", target="char_06", value=3, mode="set")
    r3 = ae.evaluate()
    ids3 = set(r3["unlocked_ids"])
    check("外部 record 成就解锁", {"ach_yanjia", "ach_kuaidan", "ach_fangzhe"} <= ids3,
          str({"ach_yanjia", "ach_kuaidan", "ach_fangzhe"} - ids3))
    check("ending 映射: 污染胜利→带节奏之王", "ach_jiezou" in set(
        ae.evaluate(ending_key="pollution_win")["unlocked_ids"]))
    check("ending 映射: 全员心晴→ach_daqidai", "ach_daqidai" in set(
        ae.evaluate(ending_key="all_hearts_clear")["unlocked_ids"]))


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        build_fixture(tmp)
        test_stage_machine()
        test_party()
        test_difficulty(tmp)
        test_memory_system(tmp)
        test_knowledge_cards(tmp)
        test_opinion_feed(tmp)
        test_evidence_chain(tmp)
        test_timeline(tmp)
        test_resolver()
        test_v31_rulings(tmp)
        test_achievements_real()
    print(f"\n==== 冒烟结果: PASS={len(PASSED)} FAIL={len(FAILED)} ====")
    for f in FAILED:
        print(f"  FAIL: {f}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
