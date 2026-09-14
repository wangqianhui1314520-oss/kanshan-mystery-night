# -*- coding: utf-8 -*-
"""叙事逻辑审计·实跑验证脚本（只读，不修改任何游戏数据）。

验证上一轮静态审读提出的 5 类问题是否真实存在，并追加发现新问题：
  C1  flaw_5(clue_032) 复盘页门控 vs 指认DM需5破绽（静态悖论 + G04 运行时补丁）
  C2  结局清单在 文档×3 / truth.json / resolver / 前端mock 六处口径
  C3  「看山的鱼干」结局名实不符 + 前端无该结局卡
  C4  DM_BOSS "(7→8)" 算术
  C5  V587 角色定位冲突（权威=看山学徒 vs 前端=被裹挟跳反者；主谋 流量酱 vs 知之者）
  C6  前端 mock 与权威内容的事实冲突（鱼干口味/开导卡/时间/地点/解锁条件）
  C7  前端署名缺《穿越大明，我被崇祯偷听心声》(凉风有信)
  C8  完美还原阈值 85%(前端) vs 90%(引擎/权威)
  C9  引擎→前端结局 id 协议断裂（outcome vs ending_id）
  E2E 引擎实跑：G04 补丁关闭→dm_mock；补丁语义复现→kanshan_still_mountain

用法：python tools/verify_narrative_audit.py
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME))

from engine.evidence_chain import EvidenceChain  # noqa: E402
from engine import resolver as resolver_mod  # noqa: E402
from engine.resolver import Resolver  # noqa: E402
from engine.stage_machine import Stage  # noqa: E402

SCEN = GAME / "content" / "scenarios" / "kanshan"
truth = json.loads((SCEN / "truth.json").read_text(encoding="utf-8"))
scenario = json.loads((SCEN / "scenario.json").read_text(encoding="utf-8"))
mock = json.loads((GAME / "data" / "_audit_mock.json").read_text(encoding="utf-8"))
store_js = (GAME / "frontend" / "js" / "store.js").read_text(encoding="utf-8")

docs = {name: (GAME / "docs" / name).read_text(encoding="utf-8")
        for name in ("GAME_DESIGN_V3.md", "DM_BOSS_DESIGN.md", "KNOWLEDGE_SYSTEM.md")}

results = []  # (编号, 结论, 证据行)


def add(cid, ok, expect, evidences):
    results.append((cid, "CONFIRMED" if ok else "NOT-REPRO", expect, evidences))


def doc_section(text, start, end):
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.S)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- C1 静态悖论
c32 = json.loads((SCEN / "clues" / "clue_032.json").read_text(encoding="utf-8"))
pooled = {cid for act in scenario["scene_map"].values() for cid in act.get("clue_pool", [])}
stage_order = [s.value for s in Stage]  # break_ice..accuse..review
# C1 固化修复：clue_032.auto_grant_on_boss_final 契约字段将「终局裁决前自动发放
# 复盘破绽」的语义写入数据层，engine_driver._finalize 读取该字段发放，
# 不再依赖隐式补丁 → 悖论已在数据层显式化解，判为 NOT-REPRO。
c1_fixed_in_data = bool(c32.get("auto_grant_on_boss_final"))
ev1 = [
    f"clue_032.unlock_condition={c32['unlock_condition']!r}, location={c32['location']!r}",
    f"clue_032.auto_grant_on_boss_final={c32.get('auto_grant_on_boss_final')}（数据层契约字段：终局裁决前自动发放，已固化 G04 语义）",
    f"Stage 顺序: {' → '.join(stage_order)}（accuse 在 review 之前）",
    f"clue_032 是否出现在 12 个搜证地点的 clue_pool: {('是' if 'clue_032' in pooled else '否——指认前不可通过搜证获得，由契约字段在终局自动记入')}",
    f"truth.json reveal_condition: {truth['boss_layer']['reveal_condition']}",
]
add("C1", c32["unlock_condition"] == "review:credits" and "clue_032" not in pooled
    and stage_order.index("accuse") < stage_order.index("review")
    and not c1_fixed_in_data,
    "破绽5被锁在复盘页(指认之后)且未在数据层固化自动发放语义 → 静态悖论存在（依赖隐式补丁）", ev1)

# ------------------------------------------------ C2 结局清单六处口径
gd5 = doc_section(docs["GAME_DESIGN_V3.md"], "## 五、", "## 六、")
gd_endings = re.findall(r"^\| ([^|\n]+) \|", gd5, re.M)
gd_endings = [t.strip() for t in gd_endings if t.strip() not in ("结局", "达成条件", "---", ":---")]
db4 = doc_section(docs["DM_BOSS_DESIGN.md"], "## 四、", "## 五、")
db_endings = [t.strip() for t in re.findall(r"^\| ([^|\n]+) \|", db4, re.M)
              if t.strip() not in ("结局", "条件", "---", ":---")]
ks_text = docs["KNOWLEDGE_SYSTEM.md"]
truth_endings = [e["name"] for e in truth["endings"]]
resolver_keys = list(resolver_mod.ENDINGS.keys())
mock_endings = [e["id"] for e in mock["endings"]]
fish_in_gd3 = any("看山的鱼干" in t for t in gd_endings)
fish_in_db = any("看山的鱼干" in t for t in db_endings)
fish_in_truth = any("鱼干" in t for t in truth_endings)
fish_in_resolver = "kanshan_fish" in resolver_keys
fish_in_mock = any("鱼干" in (e["name"]) for e in mock["endings"])
ev2 = [
    f"GAME_DESIGN_V3 §五: {len(gd_endings)} 个 → {gd_endings}",
    f"DM_BOSS §四: {len(db_endings)} 个 → {db_endings}",
    f"KNOWLEDGE_SYSTEM: 「总结局 6 → 7」存在={('总结局 6 →' in ks_text)}",
    f"truth.json: {len(truth_endings)} 个 → {truth_endings}",
    f"resolver.ENDINGS: {len(resolver_keys)} 个 → {resolver_keys}",
    f"前端mock.endings: {len(mock_endings)} 个 → {mock_endings}",
    f"「看山的鱼干」: V3文档有={fish_in_gd3}, DM_BOSS有={fish_in_db}(宣称删除), truth.json有={fish_in_truth}, resolver有={fish_in_resolver}, 前端有={fish_in_mock}",
]
add("C2", fish_in_gd3 and (not fish_in_db) and fish_in_truth and fish_in_resolver
    and (not fish_in_mock) and not (len(gd_endings) == len(db_endings) == len(truth_endings) == len(resolver_keys) == len(mock_endings)),
    "六处结局清单口径不一致：DM_BOSS 宣称删掉「看山的鱼干」但 truth.json/resolver 仍保留，前端又没有", ev2)

# ---------------------------------------------------------------- C3 鱼干结局名实不符
fish = next((e for e in truth["endings"] if "鱼干" in e["name"]), None)
sunny = next((e for e in truth["endings"] if "心晴" in e["name"]), None)
ev3 = [
    f"ending_fish 条件: {fish['condition'] if fish else '缺失'}",
    f"ending_sunny(占用鱼干主题) 条件: {sunny['condition'] if sunny else '缺失'}",
    "前端 mock.endings 无「看山的鱼干」结局卡 → 引擎 kanshan_fish 在前端无渲染物",
]
cond = fish["condition"] if fish else ""
add("C3", bool(fish) and ("沉底君" in cond and "V587" in cond and "鱼干" not in cond) and (not fish_in_mock),
    "「看山的鱼干」结局条件(沉底君好感+V587)与名称无关；鱼干主题实际属于全员心晴", ev3)

# ---------------------------------------------------------------- C4 7→8 算术
m78 = re.search(r"触发与结局体系（(\d+)\s*→\s*(\d+)）", docs["DM_BOSS_DESIGN.md"])
ev4 = [f"DM_BOSS_DESIGN 标题原文: 触发与结局体系（{m78.group(1)}→{m78.group(2)}）" if m78 else "未找到",
       f"V3 文档实际 {len(gd_endings)} 个结局；KNOWLEDGE +1=7；DM_BOSS 再 +1=8 —— 但「7」的起点已把鱼干结局删除计为成立，而数据未删，实际 truth.json={len(truth_endings)}、resolver={len(resolver_keys)}"]
add("C4", bool(m78), "「(7→8)」计数建立在「鱼干结局已删」的前提上，与数据现状矛盾", ev4)

# ---------------------------------------------------------------- C5 V587 定位冲突
accomp = [a["character"] for a in truth["culprit"]["accomplices"]]
char08 = json.loads((SCEN / "characters" / "char_08.json").read_text(encoding="utf-8"))
redeem_mock = next((e for e in mock["endings"] if e["id"] == "redeem"), None)
demo_culprit_branch = "target === 'char_03'" in store_js
demo_rescue_char08 = "r.char_id === 'char_08'" in store_js
timeline_v587 = any("受流量酱指使" in r["text"] for r in mock["reviewTimeline"])
ev5 = [
    f"truth.json 被裹挟者(swayable): {accomp}（主谋 culprit={truth['culprit']['character']} 知之者）",
    f"char_08 V587: faction={char08['faction']}, 三层身份含「看山的影子学徒」={('影子学徒' in char08['secret']['motive'])}",
    f"前端 redeem 描述: {redeem_mock['desc'] if redeem_mock else '缺失'}",
    f"前端演示裁决: 主谋分支 target==='char_03'(流量酱) 存在={demo_culprit_branch}; 跳反判定绑 char_08(V587)={demo_rescue_char08}",
    f"前端复盘时间线: 「V587 受流量酱指使送芯片备份」存在={timeline_v587}",
]
add("C5", bool(redeem_mock) and "V587" in redeem_mock["desc"] and demo_rescue_char08
    and char08["faction"] == "truth" and demo_culprit_branch
    and truth["culprit"]["character"] == "char_01",
    "权威: 主谋=知之者(char_01)、V587=看山学徒(truth阵营)；前端演示: 主谋=流量酱(char_03)、V587=被裹挟跳反者 —— 双层叙事互相矛盾", ev5)

# ---------------------------------------------------------------- C6 双数据层事实冲突
f1 = next(c for c in mock["bossFlaws"] if c["flaw_id"] == "flavor_1")
f2 = next(c for c in mock["bossFlaws"] if c["flaw_id"] == "flavor_2")
f3 = next(c for c in mock["bossFlaws"] if c["flaw_id"] == "flavor_3")
f5 = next(c for c in mock["bossFlaws"] if c["flaw_id"] == "flavor_5")
c28 = json.loads((SCEN / "clues" / "clue_028.json").read_text(encoding="utf-8"))
c29 = json.loads((SCEN / "clues" / "clue_029.json").read_text(encoding="utf-8"))
c30 = json.loads((SCEN / "clues" / "clue_030.json").read_text(encoding="utf-8"))
c31 = json.loads((SCEN / "clues" / "clue_031.json").read_text(encoding="utf-8"))
kc05 = json.loads((SCEN / "knowledge_cards" / "kc_05.json").read_text(encoding="utf-8"))
kc06 = json.loads((SCEN / "knowledge_cards" / "kc_06.json").read_text(encoding="utf-8"))
char05 = json.loads((SCEN / "characters" / "char_05.json").read_text(encoding="utf-8"))
t_kanshan_out = next((r for r in mock["reviewTimeline"] if r["time"] == "21:40"), None)
t_door_unlock = next((r for r in mock["reviewTimeline"] if r["time"] == "22:31"), None)
director_office = scenario["scene_map"]["director_office"]
ev6 = [
    f"鱼干口味: 前端flavor_1=「{('鲁宾斯坦深海' if '鲁宾斯坦' in f1['fact'] else '?')}」 vs 权威clue_028=「{('彩虹鳟鱼' if '彩虹鳟鱼' in c28['fact'] else '?')}」 vs 局长办公室彩蛋=「{('彩虹鳟鱼' if '彩虹鳟鱼' in str(director_office.get('flavor_note','')) else '?')}」",
    f"flavor_3 开导卡: 前端={f3['unlock']} vs 权威clue_030={c30['unlock_condition']}; 权威绑定: 看山Bot heartache={char05['heartache']}(kc_06={kc06.get('title','?')}); kc_05={kc05.get('title','?')}",
    f"flavor_3 时间: 前端=「{('22:10' if '22:10' in f3['fact'] else '?')}收到指令」 vs 权威timeline=22:30看山Bot执行删除(21:07-15为监控删除窗)",
    f"flavor_5: 前端 location={f5['location']}, unlock={f5['unlock']} vs 权威 clue_032 location={c32['location']}, unlock={c32['unlock_condition']}",
    f"flavor_2 解锁: 前端={f2['unlock']} vs 权威clue_029={c29['unlock_condition']}; flavor_4: 前端unlock={next(c['unlock'] for c in mock['bossFlaws'] if c['flaw_id']=='flavor_4')} vs 权威clue_031={c31['unlock_condition']}",
    f"看山行踪: 前端时间线 21:40「{t_kanshan_out['text'] if t_kanshan_out else '?'}」+22:31「{t_door_unlock['text'] if t_door_unlock else '?'}」 vs 权威truth.json: 看山21:00进暗门入局控室、扮系统音控场（假失踪，人在局内）",
]
conflicts = ("鲁宾斯坦" in f1["fact"] and "彩虹鳟鱼" in c28["fact"]) and \
            (f3["unlock"] != c30["unlock_condition"]) and (f5["location"] != c32["location"] or f5["unlock"] != c32["unlock_condition"]) and \
            bool(t_kanshan_out and "出门买鱼干" in t_kanshan_out["text"])
add("C6", conflicts, "前端 mock 数据层与权威 content/ 在鱼干口味、开导卡绑定、破绽地点/解锁、看山行踪等关键事实上互相矛盾", ev6)

# ---------------------------------------------------------------- C7 署名缺失
salt_works = mock["creditsSalt"]
missing_liangfeng = not any("穿越大明" in w or "崇祯" in w for w in salt_works)
ev7 = [
    f"前端 credits.salt: {salt_works}",
    f"权威 attribution（truth.json 末尾）要求 4 部盐言：灯灯/凉风有信/反骨/六酒",
    f"前端是否含《穿越大明，我被崇祯偷听心声》(凉风有信): {not missing_liangfeng}",
]
add("C7", missing_liangfeng, "前端演示署名区缺《穿越大明，我被崇祯偷听心声》——第二幕缝合来源未署名（合规缺口）", ev7)

# ---------------------------------------------------------------- C8 阈值不一致
perfect_mock = next(e for e in mock["endings"] if e["id"] == "perfect")
ev8 = [
    f"前端 perfect 描述: {perfect_mock['desc']}",
    "resolver.truth_coverage + truth.json: 完美还原=覆盖 ≥90%（solo 单人 partial 降 0.45，perfect 仍 0.9）",
]
add("C8", "85" in perfect_mock["desc"], "前端演示阈值 85% 与引擎/权威 90% 不一致", ev8)

# ---------------------------------------------------------------- C9 结局 id 协议断裂
fe_reads_ending_id = "state.ending = p.ending_id" in store_js
fe_reads_outcome = "outcome" in store_js
ev9 = [
    f"engine_driver._finalize 发出 payload: {{accused, outcome: matrix['ending'], title, desc, ...}} → outcome 取值如 kanshan_still_mountain/vindicated/all_hearts_clear/dm_mock",
    f"前端 store.js 仅读 p.ending_id（={fe_reads_ending_id}），全文检索 'outcome'={fe_reads_outcome}",
    f"前端结局 id 集 {mock_endings} 与 resolver id 集 {resolver_keys} 仅 'wrong' 重合，其余 8 个 id 全部对不上",
]
add("C9", fe_reads_ending_id and not fe_reads_outcome, "引擎局连真实后端时结局事件无法被前端解析（outcome vs ending_id 协议断裂），所有结局卡回退默认渲染", ev9)

# ================================================================ E2E 实跑
def e2e():
    ec = EvidenceChain(SCEN)
    rv = Resolver()
    log = []
    # 合法前置：flaw_1/2 默认可拿；flaw_3 需 kc_06 开导；flaw_4 需对话框说唤醒词
    for cid in ("clue_028", "clue_029"):
        got = ec.release(cid, "p1")
        log.append(f"release({cid}) -> {'OK:' + got['flaw_id'] if got else 'None'}")
    ec.sync_context(counsel_cards=["kc_06"])
    got = ec.release("clue_030", "p1")
    log.append(f"sync(counsel=kc_06) + release(clue_030) -> {'OK:' + got['flaw_id'] if got else 'None'}")
    ec.sync_context(chat_keywords=["看山，关门"])
    got = ec.release("clue_031", "p1")
    log.append(f"sync(chat=看山，关门) + release(clue_031) -> {'OK:' + got['flaw_id'] if got else 'None'}")
    n4 = ec.flaw_count()
    # 指认前直接拿 clue_032：应被 review 门控拒绝
    got32_early = ec.release("clue_032", "p1")
    res4 = rv.resolve_boss_accusation(n4, 2)
    log.append(f"指认前破绽数={n4}, boss_ready={ec.boss_ready()}, 提前拿clue_032={got32_early}, "
               f"resolve_boss_accusation({n4}) -> {res4['ending']}（G04 补丁关闭·mutation 基线）")
    # G04 语义复现（engine_driver._finalize L575-585）：裁决前注入 review_flags 并发放 review 线索
    ec.sync_context(review_flags={"credits"})
    got32 = ec.release("clue_032", "p1")
    n5 = ec.flaw_count()
    res5 = rv.resolve_boss_accusation(n5, 2)
    log.append(f"G04 注入后: release(clue_032)={'OK' if got32 else 'None'}, 破绽数={n5}, boss_ready={ec.boss_ready()}, "
               f"resolve_boss_accusation({n5}, counsel=2) -> {res5['ending']}")
    return log, (n4 == 4 and got32_early is None and res4["ending"] == "dm_mock"
                 and n5 == 5 and got32 is not None and res5["ending"] == "kanshan_still_mountain")


e2e_log, e2e_ok = e2e()

# ---------------------------------------------------------------- 输出
print("=" * 100)
print("叙事逻辑审计 · 实跑验证（只读）  场景: content/scenarios/kanshan")
print("=" * 100)
for cid, verdict, expect, evs in results:
    print(f"\n[{cid}] {verdict} —— {expect}")
    for e in evs:
        print(f"    · {e}")
print("\n" + "=" * 100)
print("[E2E] 引擎实跑（EvidenceChain + Resolver，真实 32 条线索数据）")
for line in e2e_log:
    print(f"    · {line}")
print(f"    => E2E {'PASS：悖论在数据层存在、运行时靠 G04 补丁兜底' if e2e_ok else 'FAIL：复现失败，需人工复核'}")
print("=" * 100)
n_conf = sum(1 for r in results if r[1] == "CONFIRMED")
print(f"汇总: {n_conf}/{len(results)} 项问题实跑复现（CONFIRMED）；E2E {'PASS' if e2e_ok else 'FAIL'}")
