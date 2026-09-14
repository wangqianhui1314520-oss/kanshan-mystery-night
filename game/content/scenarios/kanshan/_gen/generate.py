# -*- coding: utf-8 -*-
"""kanshan 内容生成器：将 data_*.py 落盘为 JSON 并做跨文件一致性断言。
用法：python generate.py （在 _gen/ 目录内运行）"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent  # .../kanshan/

import data_core
import data_characters
import data_memory
import data_clues
import data_kc_hot

FILES = {}
for mod in (data_core, data_characters, data_memory, data_clues, data_kc_hot):
    FILES.update(mod.FILES)

errors = []

# ---------- 落盘 + 自校验 ----------
for rel, obj in FILES.items():
    p = BASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
        json.loads(text)  # 序列化往返自检
        p.write_text(text + "\n", encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        errors.append(f"{rel}: {e}")

# ---------- 跨文件一致性断言 ----------
def ids_by_prefix(prefix):
    return {k.rsplit("/", 1)[-1].rsplit(".", 1)[0] for k in FILES if k.startswith(prefix)}

clue_ids = ids_by_prefix("clues/")
char_ids = {f"char_{i:02d}" for i in range(1, 9)}
kc_ids = ids_by_prefix("knowledge_cards/")
post_ids = ids_by_prefix("hotfeed/")
mem_ids = {k for k in FILES if k.startswith("memory/")}  # 完整相对路径作 key
scene_ids = set(data_core.SCENARIO["scene_map"].keys())
scene_names = {v["name"] for v in data_core.SCENARIO["scene_map"].values()}

def check(cond, msg):
    if not cond:
        errors.append("ASSERT: " + msg)

# 线索规模与分级
tiers = {}
for k, v in data_clues.CLUES.items():
    tiers[v["tier"]] = tiers.get(v["tier"], 0) + 1
check(len(data_clues.CLUES) == 32, f"线索总数应为 32，实际 {len(data_clues.CLUES)}")
check(tiers.get("fake") == 6, f"伪造线索应为 6，实际 {tiers.get('fake')}")
check(tiers.get("boss_flaw") == 5, f"boss_flaw 应为 5，实际 {tiers.get('boss_flaw')}")
flaws = sorted(v["flaw_id"] for v in data_clues.CLUES.values() if v["flaw_id"])
check(flaws == [f"flavor_{i}" for i in range(1, 6)], f"flaw_id 应为 flavor_1..5，实际 {flaws}")
for v in data_clues.CLUES.values():
    if v["tier"] == "fake":
        check(v["fake_of"] in clue_ids, f"{v['id']} fake_of 无效：{v['fake_of']}")
    check(all(n in {t["id"] for t in data_core.TRUTH["truth_nodes"]} for n in v["linked_truth_nodes"]),
          f"{v['id']} linked_truth_nodes 含未知节点")
    if v["location"] not in scene_names and v["location"] not in {"对话框", "复盘页"}:
        errors.append(f"ASSERT: {v['id']} location 不在场景表：{v['location']}")

# 场景 clue_pool 引用有效（伪造线索不入池，走投放技能）
pooled = [c for s in data_core.SCENARIO["scene_map"].values() for c in s.get("clue_pool", [])]
for c in pooled:
    check(c in clue_ids, f"scene_map 引用未知线索 {c}")
    check(data_clues.CLUES[f"clues/{c}.json"]["tier"] != "fake", f"伪造线索 {c} 不应进 clue_pool")
check(len(pooled) == 24, f"场景线索池应 24 条（32-6 伪造-2 特殊触发），实际 {len(pooled)}")

# 知识卡
check(len(data_kc_hot.KCS) == 10, f"知识卡应 10 张，实际 {len(data_kc_hot.KCS)}")
for v in data_kc_hot.KCS.values():
    if v["binds"].startswith("char_"):
        check(v["binds"] in char_ids, f"{v['id']} binds 无效：{v['binds']}")
    check(len(v["golden_lines"]) == 3, f"{v['id']} 金句应 3 条")
    check(len(v["summary"]) <= 100, f"{v['id']} 摘要超 100 字：{len(v['summary'])}")
# 心病绑定与 KNOWLEDGE_SYSTEM 匹配表一致
expect_binds = {"kc_01": "char_06", "kc_02": "char_03", "kc_03": "char_04", "kc_04": "char_07",
                "kc_05": "char_02", "kc_06": "char_05", "kc_07": "char_01", "kc_08": "char_01"}
for kid, cid in expect_binds.items():
    check(data_kc_hot.KCS[f"knowledge_cards/{kid}.json"]["binds"] == cid, f"{kid} 绑定应为 {cid}")

# 角色卡 ↔ 记忆文件
check(len(data_characters.CHARACTERS) == 8, "角色卡应 8 张")
for rel, card in data_characters.CHARACTERS.items():
    for mv in card["memory_versions"]:
        check(mv in mem_ids, f"{card['id']} 引用缺失记忆文件 {mv}")
    mem = FILES[mv]
    check(mem["owner"] == card["id"], f"{mv} owner 与角色不符")

# 记忆版本完整性
for cid in sorted(char_ids):
    for v in (1, 2, 3):
        check(f"memory/{cid}_v{v}.json" in mem_ids, f"缺记忆文件 {cid}_v{v}")

# 热搜帖
check(len(data_kc_hot.POSTS) >= 40, f"热搜帖应 40+，实际 {len(data_kc_hot.POSTS)}")
check(len(post_ids) == len(data_kc_hot.POSTS), "帖 id 重复")
rounds = sorted({p["round"] for p in data_kc_hot.POSTS.values()})
check(rounds == list(range(1, 8)), f"帖子轮次应覆盖 1-7，实际 {rounds}")
for v in data_kc_hot.POSTS.values():
    check(v["author_mask"] in {"网友", "水军", "官方"}, f"{v['id']} author_mask 非法")
    check(v["humor_tag"] in {"一眼假但好笑", "真线索伪装", "玩梗"}, f"{v['id']} humor_tag 非法")
    check(v["is_fake"] == (v["author_mask"] == "水军"), f"{v['id']} is_fake 与 author_mask 不一致")
    if v["clue_ref"]:
        check(v["clue_ref"] in clue_ids, f"{v['id']} clue_ref 无效：{v['clue_ref']}")
fake_posts = [p for p in data_kc_hot.POSTS.values() if p["is_fake"]]
tags_kc = {v["topic_tag"] for v in data_kc_hot.KCS.values()}
refutable = [p for p in fake_posts if p["topic_tag"] in tags_kc]
check(len(refutable) == 10, f"辟谣目标帖应 10（覆盖全部知识卡 tag），实际 {len(refutable)}")
for card in data_kc_hot.KCS.values():
    hit = [p["id"] for p in fake_posts if p["topic_tag"] == card["topic_tag"]]
    check(hit, f"{card['id']}（{card['topic_tag']}）无对应辟谣目标帖")

# 时间线角色合法
legal = char_ids | {"kanshan", "archiv3"}
for e in data_core.TIMELINE["timeline"]:
    check(e["character"] in legal, f"时间线角色非法：{e['character']}")
check(len(data_core.TIMELINE["timeline"]) >= 20, "时间线事件应 ≥20 条")

# 真相表证据引用
node_ids = {t["id"] for t in data_core.TRUTH["truth_nodes"]}
for t in data_core.TRUTH["truth_nodes"]:
    for c in t["proof_clues"]:
        check(c in clue_ids, f"{t['id']} proof_clue 无效：{c}")
for f in data_core.TRUTH["boss_layer"]["flaws"]:
    check(f["clue"] in clue_ids, f"破绽引用无效：{f['clue']}")
check(len(data_core.TRUTH["endings"]) == 9, "结局应为 9 条（8 正式 + 1 群嘲分支）")

# ---------- 汇总 ----------
print(f"files={len(FILES)} errors={len(errors)}")
for e in errors:
    print(" -", e)
sys.exit(1 if errors else 0)
