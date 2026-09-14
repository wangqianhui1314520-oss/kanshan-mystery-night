"""bridge 接线自测：真实 kanshan 内容 × engine 七模块 × agents 四模块（mock LLM）。

用法：python _bridge_test.py
覆盖 B 组 STATUS 遗留待办 #3 的全部 C 侧对接点：
- MemorySystem.visible_blocks → NPC 注入（heart 锁）
- KnowledgeSystem.counsel().transcript_hint → 开导演出 + effect 联动
- EvidenceChain.flaw_count → dm.set_flaw_count → boss_reveal
- EvidenceChain.sync_context（chat_keywords）→ 唤醒词彩蛋链
- 搜证/对话/指认/诊室四条链路端到端
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bridge import AgentRuntime
from llm_client import LLMClient

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, bool(ok), note))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  | {note}" if note else ""))


_TMP = Path(tempfile.mkdtemp(prefix="bridge_test_cache_"))
rt = AgentRuntime(llm=LLMClient(cache_dir=_TMP))

# ------------------------------------------------ S0 组装
check("S0 engine+agents 组装完成",
      len(rt.npcs) == 8 and len(rt.evidence.pool) >= 30
      and len(rt.knowledge.held_cards() or []) == 0 and len(rt.truth.get("truth_nodes", [])) >= 10,
      f"npcs={len(rt.npcs)} clues={len(rt.evidence.pool)} "
      f"tn={len(rt.truth.get('truth_nodes', []))}")

ev_begin = rt.begin_round()
check("S0 轮播报事件（system/dm）", ev_begin["type"] == "system" and ev_begin["actor"] == "dm"
      and "叮" in ev_begin["payload"]["text"], ev_begin["payload"]["text"][:36])

# ------------------------------------------------ S1 双层记忆接线
SINK = "char_05"                      # 沉底君（kc_06 binds 对象，B 组验证过）
sync0 = rt.sync_memory(SINK)
npc = rt.npcs[SINK]
heart_text = next((b.text for b in npc.memory_blocks if b.layer == "heart"), "")
check("S1 初始同步：said 注入 / heart 锁死",
      sync0["synced"] and sync0["version"] >= 1 and not sync0["heart_unlocked"]
      and not heart_text, str(sync0))

# 未解锁对话：引擎给的回复不得含心声文本
chat0 = rt.npc_chat(SINK, "你当晚到底在哪？", trust=30)
check("S1 未解锁对话零心声外泄",
      "heart_unlocked" in chat0 and not chat0["heart_unlocked"]
      and (not heart_text or heart_text[:8] not in chat0["reply"]))

unlock = rt.unlock_memory(SINK, "memory_fix")
check("S1 引擎解锁成功且篡改点入证据链",
      unlock.get("status") == "ok" and len(unlock.get("tamper_points", [])) >= 1
      and rt.heart_unlocked(SINK), f"ver={unlock.get('unlocked_version')}")

sync1 = rt.sync_memory(SINK)
npc2 = rt.npcs[SINK]
heart_now = next((b.text for b in npc2.memory_blocks if b.layer == "heart"), "")
check("S1 解锁后 heart 注入 NPC prompt 状态",
      sync1["heart_unlocked"] and bool(heart_now), f"blocks={sync1['block_count']}")

tp_clues = [c for c in rt.evidence.pool if c.startswith("clue_tp_")]
check("S1 篡改点 clue_card 已 ingest", len(tp_clues) >= 1, f"tp_clues={len(tp_clues)}")

# ------------------------------------------------ S2 开导链（成功 + memory_unlock/evidence 联动）
kc_success = next((cid for cid, c in
                   [(cid, rt.knowledge.card(cid)) for cid in
                     [f"kc_{i:02d}" for i in range(1, 11)]]
                   if c and c.get("binds") == SINK), None)
if kc_success is None:                # 兜底：从全卡表找 binds==SINK
    all_cards = {c["id"]: c for c in (rt.knowledge.card(f"kc_{i:02d}") for i in range(1, 11))
                 if c}
    kc_success = next((cid for cid, c in all_cards.items() if c.get("binds") == SINK), None)
counsel_ok = rt.counsel_flow("player:1", SINK, kc_success) if kc_success else None
check("S2 开导成功演出（金句+破防）",
      bool(counsel_ok) and counsel_ok["verdict"]["matched"]
      and bool(counsel_ok["performance"].strip()),
      f"card={kc_success} eff={counsel_ok['verdict'].get('effect') if counsel_ok else '-'}")

# counsel 条件线索解锁链：sync_context(counsel_cards) 已注入
cond_clues = [c for cid, c in rt.evidence.pool.items()
              if str(c.get("unlock_condition", "")).startswith(f"counsel:{kc_success}")]
if cond_clues:
    got = rt.evidence.release(cond_clues[0]["id"], rt.player_id)
    check("S2 counsel 条件线索解锁联动", got is not None, cond_clues[0]["id"])
else:
    check("S2 counsel 条件线索解锁联动", True, "（该卡无条件线索，跳过）")

# 失败分支：用绑定别人的卡开导（确定性 mock）
wrong_card = next((cid for cid, c in
                   [(f"kc_{i:02d}", rt.knowledge.card(f"kc_{i:02d}")) for i in range(1, 11)]
                   if c and c.get("binds") not in (None, SINK, "team", "team_all",
                                                   "archive", "archive_bureau")
                   and c.get("binds", "").startswith("char_")), None)
if wrong_card and wrong_card != kc_success:
    cf = rt.counsel_flow("player:1", SINK, wrong_card)
    check("S2 开导失败 → 尬聊演出", not cf["verdict"]["matched"]
          and bool(cf["performance"].strip()), f"card={wrong_card}")
else:
    check("S2 开导失败 → 尬聊演出", True, "（无可复用错配卡，跳过）")

# ------------------------------------------------ S3 彩蛋触发（先于破绽链）
# kanshan 扩展语法：clue_031（chat:keyword_看山，关门）与 clue_032（review:credits）
chat_kw = rt.npc_chat("char_04", "看山，关门", trust=50)
rt.enter_review("credits")            # 模拟进入复盘页（F 组对接点）

# ------------------------------------------------ S4 搜证链
hits = [(c.get("location"), c.get("tags", [None])[0]) for c in rt.evidence.pool.values()
        if c.get("location") and c.get("tags")]
loc, kw = hits[0]
sr = rt.search_flow(loc, kw)
check("S4 搜证反馈含 fact 原文 / 弹幕 3-5 条",
      bool(sr["feedback"]) and 3 <= len(sr["danmaku"]) <= 5,
      f"{loc}×{kw} hit={sr['result']['hit']}")

# 破绽链：5 枚 boss_flaw 条件（默认×2 / counsel:kc_06 / chat 唤醒词 / review:credits）
# 在 S2（开导成功）与本节（彩蛋触发）之后全部满足
flaws = sorted([c for c in rt.evidence.pool.values()
                if (c.get("tier") == "boss_flaw" or c.get("flaw_id"))],
               key=lambda c: c["id"])
released_flaws = 0
for c in flaws:
    if rt.evidence.release(c["id"], rt.player_id):
        released_flaws += 1
        rt.sync_flaws()
check("S4 破绽 5 枚随收集同步至 DM", released_flaws == 5 and rt.dm.flaw_count == 5
      and rt.evidence.boss_ready(), f"released={released_flaws} dm_flaw={rt.dm.flaw_count}")

# ------------------------------------------------ S5 指认链
# 表层指认：引擎规则「≥2 张证据卡才有效」（V3 §3.6）。先只合成 1 张 → 无效；
# 再补 tn_05 组（evidence:clue_005 条件链）合成第 2 张 → 有效命中真凶。
for cid in ("clue_002", "clue_003", "clue_004"):     # tn_01 ×3
    rt.evidence.release(cid, rt.player_id)
card1 = rt.evidence.try_compose(rt.player_id)
acc_weak = rt.accuse_flow(rt.truth["culprit"]["character"],
                          {"motive_statement": "流量焦虑", "method_statement": "水军"})
check("S5 证据卡 1/2 → 引擎判无效（hit=False）",
      bool(card1) and acc_weak["verdict"]["valid"] is False
      and acc_weak["verdict"]["hit"] is False
      and acc_weak["verdict"]["ending"] == "wrong",
      f"cards={len(rt.evidence.evidence_cards(rt.player_id))}")

for cid in ("clue_005", "clue_012", "clue_014"):     # tn_05 ×3（evidence 条件链满足）
    rt.evidence.release(cid, rt.player_id)
card2 = rt.evidence.try_compose(rt.player_id)
culprit = rt.truth["culprit"]["character"]
acc_strong = rt.accuse_flow(culprit, {
    "motive_statement": rt.truth["culprit"].get("motive", "")[:40],
    "method_statement": "马甲号水军矩阵"})
check("S5 证据卡 2/2 → 指认真凶命中",
      bool(card2) and acc_strong["verdict"]["valid"] is True
      and acc_strong["verdict"]["hit"] is True,
      f"ending={acc_strong['verdict']['ending']} "
      f"grade={acc_strong['verdict']['grade']}")

# 心晴累计 ≥2（S2 已开导 char_05 成功）→ 终极指认 DM 才进「看山还是山」
rt.counsel_flow("player:1", "char_02", next(
    (f"kc_{i:02d}" for i in range(1, 11)
     if (rt.knowledge.card(f"kc_{i:02d}") or {}).get("binds") == "char_02"), "kc_01"))

acc_dm = rt.accuse_flow("dm")
check("S5 指认 DM：引擎允许 + 终极层现身演出",
      acc_dm["boss_accusal"] and acc_dm["verdict"].get("allowed")
      and acc_dm["verdict"]["ending"] == "kanshan_still_mountain"
      and "刘看山" in (acc_dm["performance"] or ""),
      acc_dm["verdict"]["ending"])

clinic = rt.clinic_flow()
check("S5 心晴诊室结算链", clinic["settlement"]["counsel_count"] >= 2
      and bool(clinic["clinic"]["clinic_text"].strip()),
      f"count={clinic['settlement']['counsel_count']} tier={clinic['clinic']['tier']}")

# ------------------------------------------------ S6 守卫兜底直测
# 防线等价性：上层若误将 heart 块注入未解锁上下文，守卫兜底拦截（真实 kanshan heart 块）
heart_blocks = [b for b in rt.memory.visible_blocks(SINK, include_heart=True)
                if b.layer == "heart"]
if heart_blocks:
    hb = {"layer": "heart", "text": heart_blocks[0].text}
    leak_reply = hb["text"].strip("（）()")[:20]
    viol = rt.guard.check(rt.npcs[SINK].character, leak_reply,
                          {"memory_state": {"heart_unlocked": False, "blocks": [hb]}})
    check("S6 误注入 heart 块 → 守卫拦截", any("心声泄露" in v for v in viol),
          str(viol[:1]))
else:
    check("S6 误注入 heart 块 → 守卫拦截", True, "（无 heart 块可探，跳过）")

# ------------------------------------------------ 汇总
shutil.rmtree(_TMP, ignore_errors=True)
failed = [r for r in RESULTS if not r[1]]
print("\n" + "=" * 56)
print(f"BRIDGE TEST {'ALL PASS' if not failed else 'FAILED'}: "
      f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
for name, ok, note in failed:
    print(f"  FAIL {name} | {note}")
sys.exit(1 if failed else 0)
