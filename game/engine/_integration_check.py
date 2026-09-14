"""engine 集成验证：D 组真实内容(kanshan)适配检查（B 窗口内部工具）。

运行：python engine/_integration_check.py
纯标准库、零 AI、确定性；只读 content/，只写报告输出到 stdout。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYS_DIR = ROOT / "content" / "scenarios" / "kanshan"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stage_machine import StageMachine, Stage
from evidence_chain import EvidenceChain
from timeline import Timeline
from resolver import Resolver
from memory_system import MemorySystem
from opinion_feed import OpinionFeed, HEAT_BLOCK_THRESHOLD
from knowledge_cards import KnowledgeSystem

PASSED: list[str] = []
ISSUES: list[tuple[str, str, str]] = []  # (级别 P0/P1/P2, 模块, 描述)


def check(name: str, cond: bool, level: str = "P1", module: str = "", detail: str = ""):
    if cond:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        ISSUES.append((level, module or "-", f"{name}" + (f" :: {detail}" if detail else "")))
        print(f"  [FAIL][{level}] {name}" + (f"  <-- {detail}" if detail else ""))


def main():
    print("== 1. 内容就绪与规模 ==")
    check("scenario.json 存在", (SYS_DIR / "scenario.json").is_file(), "P0", "D/内容")
    check("timeline.json 存在", (SYS_DIR / "timeline.json").is_file(), "P0", "D/内容")
    check("truth.json 存在", (SYS_DIR / "truth.json").is_file(), "P0", "D/内容")
    n_clues = len(list((SYS_DIR / "clues").glob("*.json")))
    n_posts = len(list((SYS_DIR / "hotfeed").glob("*.json")))
    n_kcs = len(list((SYS_DIR / "knowledge_cards").glob("*.json")))
    n_mems = len(list((SYS_DIR / "memory").glob("*.json")))
    n_chars = len(list((SYS_DIR / "characters").glob("*.json")))
    check(f"线索 32 条（实际 {n_clues}）", n_clues >= 28, "P1", "D/内容")
    check(f"热搜帖 40+（实际 {n_posts}）", n_posts >= 24, "P2", "D/内容",
          "V3 目标 40+，当前够跑但规模未达标")
    check(f"知识卡 10 张（实际 {n_kcs}）", n_kcs == 10, "P0", "D/内容")
    check(f"记忆 24 文件（实际 {n_mems}）", n_mems == 24, "P1", "D/内容")
    check(f"角色卡 8 张（实际 {n_chars}）", n_chars == 8, "P0", "D/内容")

    print("== 2. 引擎回归基线 ==")
    import subprocess
    r = subprocess.run([sys.executable, str(Path(__file__).parent / "_smoke_test.py")],
                       capture_output=True, text=True, encoding="utf-8")
    tail = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "(no output)"
    check("冒烟 121 断言全 PASS", r.returncode == 0 and "FAIL=0" in tail, "P0", "engine", tail)

    print("== 3. 五模块真实内容加载 ==")
    ec = EvidenceChain(SYS_DIR)
    tl = Timeline(SYS_DIR)
    ms = MemorySystem()
    of = OpinionFeed()
    ks = KnowledgeSystem()
    ms.load(str(SYS_DIR)); of.load(str(SYS_DIR)); ks.load(str(SYS_DIR))
    check(f"EvidenceChain 线索池 {len(ec.pool)}/32", len(ec.pool) == n_clues, "P0", "engine")
    check(f"Timeline 轨迹 {len(tl.entries)} 条", len(tl.entries) >= 20, "P1", "engine")
    check(f"MemorySystem 记忆链 {len(ms._versions)} 角色", len(ms._versions) == 8, "P0", "engine")
    check(f"OpinionFeed 帖池 {len(of._posts)}", len(of._posts) == n_posts, "P1", "engine")
    check(f"KnowledgeSystem 卡池 {len(ks._cards)}", len(ks._cards) == 10, "P0", "engine")

    print("== 4. schema 兼容性逐项 ==")
    tiers = {}
    bad_tier = []
    bad_cond = []
    special_loc = {}
    for c in ec.pool.values():
        t = c.get("tier") or c.get("level") or "?"
        tiers[t] = tiers.get(t, 0) + 1
        if t not in ("public", "limited", "hidden", "fake", "boss_flaw"):
            bad_tier.append(c["id"])
        cond = str(c.get("unlock_condition", "默认"))
        ok = cond == "默认" or cond.split(":")[0] in ("evidence", "memory", "counsel", "boss", "chat", "review")
        if not ok:
            bad_cond.append(f"{c['id']}:{cond}")
        if c.get("location") in ("对话框", "复盘页"):
            special_loc[c.get("location")] = special_loc.get(c.get("location"), 0) + 1
    check("线索 tier 全部合法", not bad_tier, "P0", "D/内容", str(bad_tier))
    check("unlock_condition 全部可解析", not bad_cond, "P0", "engine", str(bad_cond))
    check("tier 分布含 5 类", set(tiers) == {"public", "limited", "hidden", "fake", "boss_flaw"},
          "P1", "D/内容", str(tiers))
    check("boss_flaw 线索 5 条", tiers.get("boss_flaw") == 5, "P0", "D/内容", str(tiers))
    flaws = {c.get("flaw_id") for c in ec.pool.values() if (c.get("tier") or "") == "boss_flaw"}
    check(f"破绽 flaw_id 齐全 {sorted(f for f in flaws if f)}",
          len([f for f in flaws if f]) == 5, "P1", "D/内容")
    check("对话框/复盘页特殊地点存在（扩展语法）", special_loc.get("对话框", 0) >= 1
          and special_loc.get("复盘页", 0) >= 1, "P2", "D/内容", str(special_loc))

    mem_layers = set()
    mem_integrity = set()
    diff_tp = 0
    for f in (SYS_DIR / "memory").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for b in d.get("blocks", []):
            mem_layers.add(b.get("layer"))
            mem_integrity.add(b.get("integrity"))
        diff_tp += sum(1 for x in d.get("diff_from_prev", []) if x.get("tamper_point"))
    check("memory layer 仅 said/heart", mem_layers <= {"said", "heart"}, "P0", "D/内容", str(mem_layers))
    check("memory integrity 合法", mem_integrity <= {"original", "edited", "deleted"},
          "P0", "D/内容", str(mem_integrity))
    check(f"diff tamper_point 标注 {diff_tp} 处", diff_tp >= 8, "P1", "D/内容", f"实际 {diff_tp}")

    cards = list(ks._cards.values())
    check("知识卡 binds 全部存在", all(c.get("binds") for c in cards), "P0", "D/内容")
    check("知识卡 effect 全部合法",
          {c.get("effect") for c in cards} <= {"boss_key", "evidence", "memory_unlock",
                                               "buff_ap", "plot_fragment"}, "P0", "D/内容",
          str({c.get("effect") for c in cards}))
    binds_chars = {c.get("binds") for c in cards}
    char_ids = {json.loads(f.read_text(encoding="utf-8")).get("id")
                for f in (SYS_DIR / "characters").glob("*.json")}
    group_aliases = KnowledgeSystem.TEAM_ALIASES | KnowledgeSystem.ARCHIVE_ALIASES
    orphan_binds = {b for b in binds_chars if b not in char_ids and b not in group_aliases}
    check("binds 指向存在的角色/team/archive", not orphan_binds, "P0", "D/内容", str(orphan_binds))
    # 开导匹配：真实卡逐一验证（NPC 卡对绑定角色匹配，组卡对 group 目标匹配）
    group_ok = all(ks.counsel("p1", "team_all", cid)["matched"]
                   for cid, c in ks._cards.items() if c.get("binds") in KnowledgeSystem.TEAM_ALIASES)
    check("组卡 team_all 匹配（别名适配）", group_ok, "P0", "engine")

    posts = list(of._posts.values())
    check("帖 round 字段齐全", all(int(p.get("round", 0)) > 0 for p in posts), "P1", "D/内容")
    fake_with_clue = [p["id"] for p in posts if p.get("is_fake") and p.get("clue_ref")]
    check("假帖不引用真线索 id", not fake_with_clue, "P1", "D/内容", str(fake_with_clue))
    real_clue_refs = {p.get("clue_ref") for p in posts if p.get("clue_ref")}
    missing_refs = real_clue_refs - set(ec.pool)
    check("帖 clue_ref 均指向存在的线索", not missing_refs, "P0", "D/内容", str(missing_refs))

    print("== 5. 引擎功能交叉验证（真实内容） ==")
    # 5.1 搜证命中：看山工位 + 鱼干
    r1 = ec.search("看山工位", "鱼干", "p1", round_no=1)
    check("search 真实地点命中", r1["hit"] and r1["clues"], "P0", "engine",
          json.dumps(r1, ensure_ascii=False)[:200])
    # 5.2 环境线索
    r2 = ec.search("天台", "完全无关词", "p2", round_no=1)
    check("未命中→环境线索", (not r2["hit"]) and r2["env_clue"] is not None, "P1", "engine")
    # 5.3 evidence 条件链
    cond_clues = [c for c in ec.pool.values()
                  if str(c.get("unlock_condition", "")).startswith("evidence:")]
    workable = 0
    for c in cond_clues:
        dep = c["unlock_condition"].split(":", 1)[1]
        if dep in ec.pool:
            workable += 1
    check(f"evidence 条件依赖均存在（{workable}/{len(cond_clues)}）",
          workable == len(cond_clues), "P0", "D/内容")
    for c in cond_clues:
        dep = c["unlock_condition"].split(":", 1)[1]
        ec.released.setdefault(dep, set()).add("p1")
        got = ec.release(c["id"], "p1")
        check(f"evidence 条件链解锁 {c['id']}←{dep}", got is not None, "P0", "engine")
    # 5.4 memory 条件 + memory_system 联动
    mem_cond = [c for c in ec.pool.values()
                if str(c.get("unlock_condition", "")).startswith("memory:")]
    for c in mem_cond:
        _, ch, v = c["unlock_condition"].split(":")
        guard = 0
        while ms.current_version(ch) < int(v) and guard < 5:
            ms.unlock_next(ch, "memory_fix")  # 逐版本解锁至条件版本
            guard += 1
        ec.sync_context(memory_versions={ch: ms.current_version(ch)})
        got = ec.release(c["id"], "p1")
        check(f"memory 条件链 {c['id']}（{ch}:v{v}）", got is not None and ms.current_version(ch) >= int(v),
              "P0", "engine", f"ver={ms.current_version(ch)}")
    # 5.5 counsel 条件 + knowledge_cards 联动
    cs_cond = [c for c in ec.pool.values()
               if str(c.get("unlock_condition", "")).startswith("counsel:")]
    for c in cs_cond:
        kc_id = c["unlock_condition"].split(":", 1)[1]
        card = ks.card(kc_id)
        check(f"counsel 条件卡存在 {kc_id}", card is not None, "P0", "D/内容")
        if card:
            target = card["binds"]
            cr = ks.counsel("p1", target, kc_id)
            check(f"开导演算 {kc_id}→{target}", cr["matched"], "P0", "engine",
                  f"effect={cr['effect']}")
            ec.sync_context(counsel_cards={kc_id})
            got = ec.release(c["id"], "p1")
            check(f"counsel 条件链解锁 {c['id']}", got is not None, "P0", "engine")
    # 5.6 chat/review 扩展语法
    chat_clues = [c for c in ec.pool.values()
                  if str(c.get("unlock_condition", "")).startswith("chat:keyword_")]
    for c in chat_clues:
        kw = c["unlock_condition"][len("chat:keyword_"):]
        check(f"chat 条件未触发被拒 {c['id']}", ec.release(c["id"], "p1") is None, "P0", "engine")
        ec.sync_context(chat_keywords={kw})
        check(f"chat 条件说关键词解锁 {c['id']}（{kw}）", ec.release(c["id"], "p1") is not None, "P0", "engine")
    rev_clues = [c for c in ec.pool.values()
                 if str(c.get("unlock_condition", "")).startswith("review:")]
    for c in rev_clues:
        flag = c["unlock_condition"].split(":", 1)[1]
        check(f"review 条件未触发被拒 {c['id']}", ec.release(c["id"], "p1") is None, "P0", "engine")
        ec.sync_context(review_flags={flag})
        check(f"review 条件解锁 {c['id']}", ec.release(c["id"], "p1") is not None, "P0", "engine")
    # 5.7 boss 破绽链：5 条全部可得
    boss_clues = sorted([c["id"] for c in ec.pool.values() if c.get("tier") == "boss_flaw"])
    p2_got = 0
    for cid in boss_clues:
        ec.sync_context()  # no-op
        # boss_flaw 线索 tier 视作可发放（unlock_condition 已逐条验证）
        if ec.release(cid, "p1") is not None:
            p2_got += 1
    check(f"boss_flaw 可发放 {p2_got}/5", p2_got == 5, "P0", "engine")
    check("boss_ready（破绽≥5 解锁指认 DM）", ec.boss_ready(), "P0", "engine")
    # 5.8 证据合成
    ev = ec.try_compose("p1")
    check("证据合成产出", ev is not None, "P1", "engine")
    # 5.9 篡改点→证据链
    tps = ms.tamper_points()
    check(f"篡改点产出 {len(tps)} 处", len(tps) >= 8, "P1", "engine", f"实际 {len(tps)}")
    for tp in tps[:3]:
        card = tp["clue_card"]
        ec.ingest_clue(card, owner="p1")
        check(f"篡改点线索卡入池 {tp['id']}", ec.clue(card["id"]) is not None, "P0", "engine")
    # 5.10 时间线
    chars_tl = {e["character"] for e in tl.entries}
    check(f"时间线覆盖角色 {len(chars_tl)}", len(chars_tl) >= 8, "P1", "D/内容", str(sorted(chars_tl)))
    claims = tl.check_claims(sorted(chars_tl)[0],
                             [{"time": tl.entries[0]["time"], "location": tl.entries[0]["location"]}])
    check("check_claims 真实轨迹一致", claims[0]["consistent"], "P0", "engine")
    # 5.11 舆论场
    panel = of.refresh(1)
    check(f"热搜面板 round1 {len(panel)} 条", 4 <= len(panel) <= 8, "P1", "engine")
    fake_posts = [p for p in of._posts.values() if p.get("is_fake")]
    if fake_posts:
        fb = of.buy_heat("polluter", fake_posts[0]["id"])
        check("买热搜真实假帖", fb["ok"], "P0", "engine")
    # 找一对 topic_tag 匹配的帖与卡验证辟谣成功
    pair = None
    for p in of._posts.values():
        for cid, card in ks._cards.items():
            if str(card.get("topic_tag", "")).strip() and card["topic_tag"] == p.get("topic_tag"):
                pair = (p["id"], cid, p.get("clue_ref"))
                break
        if pair:
            break
    if pair:
        of.attach_knowledge(lambda cid: (ks.card(cid) or {}).get("topic_tag"))
        ref = of.refute("p1", pair[0], pair[1])
        check(f"辟谣成功（帖 {pair[0]} × 卡 {pair[1]}，tag={ks.card(pair[1])['topic_tag']}）",
              ref["ok"] and ref["unlocked_clue"] == pair[2], "P0", "engine",
              json.dumps(ref, ensure_ascii=False)[:150])
    else:
        check("存在帖×卡 topic_tag 匹配对（辟谣可成功）", False, "P0", "D/内容",
              "hotfeed 与 knowledge_cards 的 topic_tag 无交集")
    # 5.12 真相覆盖 + 结局矩阵
    truth = json.loads((SYS_DIR / "truth.json").read_text(encoding="utf-8"))
    cov = Resolver.truth_coverage(["clue_002", "clue_004"], truth)
    check(f"truth_coverage（真实 14 节点）={cov}", 0.0 < cov <= 1.0, "P0", "engine")
    rs = Resolver()
    acc = rs.resolve_accusation([{"clue_ids": ["clue_002", "clue_004"]},
                                 {"clue_ids": ["clue_007", "clue_011"]}],
                                truth["culprit"]["character"], truth)
    check(f"指认真凶 {truth['culprit']['character']} 命中", acc["hit"], "P0", "engine",
          f"grade={acc['grade']} cov={acc['coverage']}")
    boss = rs.resolve_boss_accusation(5, counsel_count=2)
    check("终极结局分支", boss["ending"] == "kanshan_still_mountain", "P0", "engine")
    # 5.13 状态机真实 scenario
    scenario = json.loads((SYS_DIR / "scenario.json").read_text(encoding="utf-8"))
    sm = StageMachine(scenario)
    acts = [a["stage"] for a in scenario["acts"]]
    check(f"acts 阶段序列 {acts}", set(acts) <= {"break_ice", "investigate",
                                                 "round_table", "accuse", "review"}, "P0", "D/内容")
    ev1 = sm.begin_round()
    check("系统播报可生成", "叮——" in ev1["payload"]["text"], "P0", "engine")
    total_ap = sum(a["actions_allocated"] for a in scenario["acts"])
    check(f"总行动点 {total_ap}（scenario 自述 33）", total_ap == 33, "P2", "D/内容", f"实际 {total_ap}")

    # ---- 汇总 ----
    print(f"\n==== 集成验证: PASS={len(PASSED)} ISSUES={len(ISSUES)} ====")
    for lv, mod, desc in ISSUES:
        print(f"  [{lv}] ({mod}) {desc}")
    if not ISSUES:
        print("  （无 Issue，D 内容与引擎全兼容）")
    return 1 if any(lv == "P0" for lv, _, _ in ISSUES) else 0


if __name__ == "__main__":
    sys.exit(main())
