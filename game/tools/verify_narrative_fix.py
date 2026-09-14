# -*- coding: utf-8 -*-
"""叙事修复回归守护（只读）。配合 tools/_audit_dump_mock.js 使用：
先重导 mock（node），再跑本脚本断言修复后状态 + 引擎 E2E 复跑。

用法：node tools/_audit_dump_mock.js && python tools/verify_narrative_fix.py
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

SCEN = GAME / "content" / "scenarios" / "kanshan"
truth = json.loads((SCEN / "truth.json").read_text(encoding="utf-8"))
scenario = json.loads((SCEN / "scenario.json").read_text(encoding="utf-8"))
mock = json.loads((GAME / "data" / "_audit_mock.json").read_text(encoding="utf-8"))
data_js = (GAME / "frontend" / "js" / "data.js").read_text(encoding="utf-8")
store_js = (GAME / "frontend" / "js" / "store.js").read_text(encoding="utf-8")
docs = {n: (GAME / "docs" / n).read_text(encoding="utf-8")
        for n in ("GAME_DESIGN_V3.md", "DM_BOSS_DESIGN.md", "KNOWLEDGE_SYSTEM.md")}

results = []


def check(cid, ok, desc):
    results.append((cid, "PASS" if ok else "FAIL", desc))


# ---- R1 (C5): 主谋/跳反者对齐权威 ----
check("R1a", "target === 'char_01'" in store_js and "target === 'char_03'" not in store_js,
      "演示局主谋分支=知之者(char_01)，原 char_03 分支已移除")
check("R1b", "r.char_id === 'char_08'" not in store_js
      and "['char_03', 'char_04']" in store_js,
      "跳反判定=被裹挟者流量酱/路人甲(char_03/04)，不再绑 V587")
redeem = next((e for e in mock["endings"] if e["id"] == "redeem"), {})
check("R1c", "流量酱/路人甲" in redeem.get("desc", "") and "V587" not in redeem.get("desc", ""),
      "沉冤得雪结局文案不再让 V587 跳反")
tl = " ".join(f'{r["time"]} {r["text"]}' for r in mock["reviewTimeline"])
check("R1d", "受流量酱指使" not in tl and "出门买鱼干" not in tl and "备注「587」" not in tl and "奶茶" not in tl,
      "复盘时间线移除「V587 受流量酱指使」「看山出门买鱼干」「587 备注/奶茶」")

# ---- R2 (C9): 结局 id 协议桥接 ----
m = re.search(r"const ENDING_TO_UI = \{([^;]+)\};", store_js, re.S)
if not m:
    m = re.search(r"\(\s*(\{[^}]+\})\s*\[p\.outcome\]\s*\)", store_js)
mapping = dict(re.findall(r"(\w+)\s*:\s*'(\w+)'", m.group(1))) if m else {}
missing_keys = [k for k in resolver_mod.ENDINGS if k not in mapping]
bad_targets = [v for v in mapping.values() if v not in {e["id"] for e in mock["endings"]}]
check("R2a", bool(mapping) and not missing_keys and not bad_targets,
      f"outcome→ending_id 映射覆盖 resolver 全部 {len(resolver_mod.ENDINGS)} 个结局且目标卡齐全"
      + (f"（缺 {missing_keys} / 坏目标 {bad_targets}）" if missing_keys or bad_targets else ""))
check("R2b", any(e["id"] == "fish" for e in mock["endings"]) and any(e["id"] == "hung" for e in mock["endings"]),
      "前端补齐「隐藏·看山的鱼干」与「悬而未决」结局卡（引擎 kanshan_fish/hung 可渲染）")

# ---- R3 (C6): 事实冲突清零 ----
f1 = next(c for c in mock["bossFlaws"] if c["flaw_id"] == "flavor_1")
f3 = next(c for c in mock["bossFlaws"] if c["flaw_id"] == "flavor_3")
f5 = next(c for c in mock["bossFlaws"] if c["flaw_id"] == "flavor_5")
c28 = json.loads((SCEN / "clues" / "clue_028.json").read_text(encoding="utf-8"))
c32 = json.loads((SCEN / "clues" / "clue_032.json").read_text(encoding="utf-8"))
check("R3a", "鲁宾斯坦" not in data_js and "彩虹鳟鱼" in f1["fact"] and "彩虹鳟鱼" in c28["fact"],
      "鱼干口味全库统一为「彩虹鳟鱼味」（前端 clue/便签/快递/天台 + 权威 clue_028 + 局长办公室）")
check("R3b", all([
    "22:30 执行" in f3["fact"],
    "22:10" not in f3["fact"],
    "22:10" not in tl,
    "22:30" in tl,
    "22:31" not in tl,
    "22:10" not in data_js,
]),
      "看山Bot 指令时间统一为 22:30 执行（demo 破绽 fact + 复盘时间线 + 全文件无 22:10 残留）"
      + ("" if all(["22:30 执行" in f3["fact"], "22:10" not in f3["fact"], "22:10" not in tl,
                    "22:30" in tl, "22:31" not in tl, "22:10" not in data_js])
         else f"（f3={f3['fact'][:30]}… tl_2231={'22:31' in tl} js_2210={'22:10' in data_js}）"))
check("R3c", "策划你的策划" in f5["fact"] and "互证" in c32["fact"],
      "flavor_5 双层互证：前端策划案落款 ↔ 权威复盘署名小字同一句签名")
check("R3d", "大门解锁" not in data_js and "出门买鱼干" not in data_js,
      "「看山离局」叙事清零（门禁记录/记忆/时间线均改为人在局内）")
kc_target = next((k for k in mock["kcards"]
                  if "不想学习" in k.get("title", "") and "黛西巫巫" in k.get("author", "")), None)
check("R3e", bool(kc_target) and kc_target.get("binds") == "char_05",
      f"「黛西巫巫《不想学习…》→ 看山Bot(char_05)」语义绑定保留（前端权威编号 kc_06，与 content kc 编号体系差异已记录为非缺陷）：id={kc_target and kc_target.get('id')}")

# ---- R4 (C7): 署名补齐 ----
check("R4", any("穿越大明" in w for w in mock["creditsSalt"]) and len(mock["creditsSalt"]) == 4,
      f"盐言署名补齐为 4 部（含凉风有信）：{mock['creditsSalt']}")

# ---- R5 (C8): 阈值统一 90% ----
perfect = next(e for e in mock["endings"] if e["id"] == "perfect")
check("R5", "≥90%" in perfect["desc"] and "85" not in perfect["desc"] and "cov.pct >= 90" in store_js,
      "完美还原阈值统一 ≥90%（前端文案 + 演示裁决逻辑）")

# ---- R6 (C2/C4): 文档口径统一 9 结局 ----
gd, db, ks = docs["GAME_DESIGN_V3.md"], docs["DM_BOSS_DESIGN.md"], docs["KNOWLEDGE_SYSTEM.md"]
check("R6a", "多结局（9 个" in gd and "全员心晴" in gd and "看山还是山" in gd and "群嘲分支" in gd,
      "GAME_DESIGN_V3 §五 更新为 9 结局全表")
check("R6b", "7 → 8" not in db and "看山的鱼干" in db and "G04" in db,
      "DM_BOSS 标题去除(7→8)、补回「看山的鱼干」行并写入 G04 时序桥接说明")
check("R6c", "总结局 → **9**" in ks,
      "KNOWLEDGE_SYSTEM 规模增量行更新为 9 结局口径")

# ---- R7 (C1): G04 语义写回数据 ----
check("R7", "G04" in truth["boss_layer"]["reveal_condition"] and "互证" in c32["fact"],
      "truth.json reveal_condition 写入 G04 语义；clue_032 fact 标注互证来源")

# ---- E2E 回归：引擎 boss 流程 + resolver 字符串改动无副作用 ----
ec = EvidenceChain(SCEN)
rv = Resolver()
for cid in ("clue_028", "clue_029"):
    ec.release(cid, "p1")
ec.sync_context(counsel_cards=["kc_06"])
ec.release("clue_030", "p1")
ec.sync_context(chat_keywords=["看山，关门"])
ec.release("clue_031", "p1")
base = rv.resolve_boss_accusation(ec.flaw_count(), 2)["ending"]
n4 = ec.flaw_count()
early = ec.release("clue_032", "p1")
ec.sync_context(review_flags={"credits"})
ec.release("clue_032", "p1")
n5 = ec.flaw_count()
g04 = rv.resolve_boss_accusation(n5, 2)["ending"]
check("E2E", n4 == 4 and early is None and base == "dm_mock"
      and n5 == 5 and g04 == "kanshan_still_mountain"
      and "彩虹鳟鱼" in resolver_mod.ENDINGS["kanshan_fish"][1],
      f"引擎 E2E 复跑：破绽4(无G04注入,提前拿flavor_5={early})→{base}/dm_mock；"
      f"注入后破绽5→{g04}/kanshan_still_mountain；resolver 鱼干结局文案含彩虹鳟鱼（字符串改动零行为影响）")

# ---------------------------------------------------------------- 输出
print("=" * 96)
print("叙事修复 · 回归守护（只读）")
print("=" * 96)
for cid, verdict, desc in results:
    print(f"[{cid}] {verdict}  {desc}")
n_pass = sum(1 for r in results if r[1] == "PASS")
print("=" * 96)
print(f"汇总: {n_pass}/{len(results)} PASS" + ("  —— 全部修复项验证通过" if n_pass == len(results) else "  —— 存在 FAIL，见上"))
sys.exit(0 if n_pass == len(results) else 1)
