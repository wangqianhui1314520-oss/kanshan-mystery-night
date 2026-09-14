"""agents 全链路自测（mock 模式，零 key 零网络）。

用法：python selftest.py
覆盖：Provider 降级链 / 预生成缓存 / DM（系统音人格+破绽注入+终极层演出）/
NPC（双层记忆 heart 注入锁）/ Judge（确定性评分+boss 指认分支+心晴诊室）/
一致性守卫（心声拦截/泄密/时间线/清洗）/ 凭证安全（无硬编码 key）。
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import llm_client as lc
from consistency_guard import ConsistencyGuard
from dm_agent import DMAgent
from judge_agent import JudgeAgent
from llm_client import LLMClient, MockProvider, call_gateway
from npc_agent import NPCAgent

RESULTS: list[tuple[str, bool, str]] = []

# 自测全程使用临时缓存目录：保证幂等，不污染 agents/cache 持久缓存
_TMP = Path(tempfile.mkdtemp(prefix="agents_selftest_cache_"))


def check(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, bool(ok), note))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  | {note}" if note else ""))


# ---------------------------------------------------------- 0. 环境隔离
for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "ZHIHU_APP_KEY"):
    os.environ.pop(var, None)

client = LLMClient(cache_dir=_TMP)
check("P0 无 key 时 mock 生效", not client.providers["main"].available()
      and client.providers["mock"].available(),
      f"providers={ {k: v.available() for k, v in client.providers.items()} }")

# ---------------------------------------------------------- 1. 预生成缓存
jobs = [
    {"cache_key": "open_dm_1", "system": "叮——系统提示音人格。",
     "user": "生成第 1 轮开场播报，破绽计数：0"},
    {"cache_key": "testimony_cendijun_1", "system": "角色：沉底君（折叠区怨灵）",
     "user": "固定证词：21:00 我在茶水间……"},
    {"cache_key": "testimony_liurenjia_1", "system": "角色：路人甲（匿名吃瓜群众）",
     "user": "固定证词：我好像看到过……"},
    {"cache_key": "scene_teahouse", "system": "系统提示音。", "user": "描写茶水间场景"},
    {"cache_key": "counsel_kc06_chendijun", "system": "开导演出。",
     "user": "用《如何走出职业倦怠》开导沉底君"},
    {"cache_key": "danmaku_round1", "system": "弹幕。", "user": "生成 4 条弹幕"},
]
pregen = client.pregenerate(jobs)
check("P1 预生成全部成功", pregen["done"] == len(jobs) and not pregen["failed"], str(pregen))
hits = sum(1 for j in jobs if client.cached(j["cache_key"]) is not None)
check("P1 缓存可回读", hits == len(jobs), f"hits={hits}/{len(jobs)}")

text = client.chat([{"role": "system", "content": "系统提示音。"},
                    {"role": "user", "content": "播报测试"}])
chunks = list(client.chat([{"role": "system", "content": "x"}, {"role": "user", "content": "y"}],
                          stream=True))
check("P1 chat 返回 str / stream 返回迭代器",
      isinstance(text, str) and len(chunks) > 1 and all(isinstance(c, str) for c in chunks))

# 降级链：指定 zhida（未配置）→ main（未配置）→ mock
client.chat([{"role": "system", "content": "导读测试"}, {"role": "user", "content": "生成今日导读"}],
            provider="zhida")
check("P1 zhida→mock 降级链生效",
      client.last_provider.startswith("mock") and any("zhida" in d for d in client.degrade_log),
      f"last={client.last_provider}")

# ---------------------------------------------------------- 2. DM Agent
dm = DMAgent(client)
ann = dm.stage_announce("第二幕·心声泄露", "找出记忆被改的人", 3)
check("P2 阶段播报：叮 + 阶段 + 行动点",
      ann.startswith("叮") and "第二幕·心声泄露" in ann and "3" in ann, ann[:40])
check("P2 破绽 0-2 无破绽尾缀", dm.set_flaw_count(1) or dm.flaw_count == 1
      and "大概" not in dm.stage_announce("搜证", "收集证据", 3))
dm.set_flaw_count(3)
check("P2 破绽计数 3 → 违和尾缀注入", "大概" in dm.stage_announce("搜证", "收集证据", 3))
dm.set_flaw_count(5)
check("P2 破绽计数 5 → 明显迟疑注入", "停顿" in dm.stage_announce("搜证", "收集证据", 3))

dm.set_flaw_count(1)
scene = dm.scene_desc({"location": "茶水间", "stage": "act1", "event_summary": "开箱搜证"})
check("P2 场景描写非空", bool(scene.strip()), scene[:36])

fact = "监控时间轴上 21:07-21:15 存在人为删除痕迹，删除操作使用的账号属于档案局内部权限。"
fb = dm.action_feedback("搜证：监控室", {"success": True, "clue": {
    "id": "clue_007", "name": "被擦掉的监控片段", "fact": fact,
    "flavor_hint": "冷光、时间轴空洞、机器吃灰"}})
check("P2 命中反馈：fact 原文一字不改", fact in fb, fb[:40])
fb2 = dm.action_feedback("搜证：天台", {"success": False})
check("P2 未命中反馈：一无所获", "一无所获" in fb2 or "为空" in fb2)

dank = dm.danmaku({"event_summary": "玩家搜出监控删除记录"}, n=4)
check("P2 弹幕 3-5 条", 3 <= len(dank) <= 5, " | ".join(dank[:2]))

reveal = dm.boss_reveal({"flaw_list": ["鱼干口味口误", "最高权限删除", "主人级签名",
                                        "唤醒词彩蛋", "策划签名"]})
check("P2 终极层现身演出：看山 + 点题句",
      "刘看山" in reveal and "你们破的局，正是我设的局" in reveal, reveal.splitlines()[4][:40])
brief = dm.daily_briefing({"daily_topic": "#谁动了我的鱼干#"})
check("P2 每日导读（zhida 低频位，自动降级）", bool(brief.strip()), brief[:32])

# ---------------------------------------------------------- 3. NPC 双层记忆
CHAR = {
    "id": "char_07", "name": "沉底君", "archetype": "折叠区怨灵", "faction": "swayable",
    "public": {"bio": "每句话都被折叠，其实没有。",
               "speech_style": "低气压、自嘲、句尾'[该发言已被折叠]'"},
    "secret": {"motive": "当晚在机房试图恢复自己被折叠的答案",
               "alibi": "声称整晚都在茶水间写回答",
               "guilt": "看到了删除监控的人但装作没看见"},
    "goal": "找回自己的第 7 章答案", "heartache": "kc_06",
}
MEM_BLOCKS = [
    {"id": "blk_01", "time": "21:00", "layer": "said",
     "text": "我在茶水间写回答，谁也没看见。", "integrity": "edited"},
    {"id": "blk_01h", "time": "21:00", "layer": "heart",
     "text": "（心声）其实我去了机房，想偷偷恢复被折叠的第 7 章。", "integrity": "original"},
]


class _TL:
    def query(self, _c, _r=None):
        return [{"time": "21:00", "location": "茶水间", "action": "写回答"}]

    def verify(self, _c, _t, _l):
        return True


npc = NPCAgent(client, CHAR, _TL())
npc.update_memory(MEM_BLOCKS, version=1, heart_unlocked=False)
ctx_locked = npc._build_context(trust=10)
check("P3 heart 未解锁 → prompt 零心声注入",
      "其实我去了机房" not in ctx_locked and "加密中" in ctx_locked)
reply_locked = npc.respond("你当晚到底去哪了？", trust=10)
check("P3 未解锁回复不外泄心声", "其实我去了机房" not in reply_locked, reply_locked[:36])

npc.update_memory(MEM_BLOCKS, version=2, heart_unlocked=True)
ctx_open = npc._build_context(trust=70)
check("P3 heart 解锁 → prompt 注入心声层",
      "其实我去了机房" in ctx_open and "逐步流露" in ctx_open)
reply_open = npc.respond("心声层已经修复了，说说吧。", trust=70)
check("P3 解锁后可流露心声", isinstance(reply_open, str) and bool(reply_open.strip()))
quirk_reply = NPCAgent(client, CHAR, _TL()).respond("在吗？", trust=10)
check("P3 腔调锚点（沉底君折叠梗）", "[该发言已被折叠]" in quirk_reply, quirk_reply[:40])

# ---------------------------------------------------------- 4. Judge
TRUTH = {
    "culprit": {"character": "char_03", "name": "流量酱（热榜话题精）",
                "motive": "流量焦虑，有热度才有安全感",
                "method": "用水军账号投放伪证，带偏热搜节奏"},
    "truth_nodes": [
        {"id": "tn_01", "name": "水军线", "proof_clues": ["clue_013"]},
        {"id": "tn_02", "name": "记忆芯片", "proof_clues": ["clue_021"]},
        {"id": "tn_03", "name": "鱼干去向", "proof_clues": ["clue_030"]},
    ],
}
judge = JudgeAgent(client, TRUTH)
CLUES = [{"id": "clue_013", "linked_truth_nodes": ["tn_01"]},
         {"id": "clue_007", "linked_truth_nodes": ["tn_02"]}]
r1 = judge.judge({"target": "char_99",
                  "motive_statement": "为了热度，有热度才有安全感",
                  "method_statement": ""}, CLUES)
check("P4 指认错人 → target_hit=False", r1["target_hit"] is False)
check("P4 动机命中（2-gram 重叠）", r1["motive_hit"] is True)
check("P4 覆盖度=2/3", abs(r1["evidence_coverage"] - 2 / 3) < 0.01,
      f"{r1['evidence_coverage']} covered={r1['covered_truth_nodes']}")
check("P4 软评分由 LLM/mock 补齐", isinstance(r1["logic_quality"], int)
      and 0 <= r1["logic_quality"] <= 5 and isinstance(r1["misleading_points"], list),
      f"logic_quality={r1['logic_quality']}")

r2 = judge.judge({"target": "char_03", "motive_statement": "热度就是安全感",
                  "method_statement": "水军投放伪证带节奏"}, CLUES)
check("P4 指认命中 → target_hit=True", r2["target_hit"] is True)

boss2 = judge.judge({"target": "dm"}, [
    {"id": "flavor_1", "tier": "boss_flaw", "flaw_id": "flavor_1"},
    {"id": "flavor_2", "tier": "boss_flaw", "flaw_id": "flavor_2"}])
check("P4 指认 DM 但破绽 2/5 → 不命中",
      boss2["boss_accusal"] and boss2["target_hit"] is False and boss2["flaw_evidence_count"] == 2)
boss5 = judge.judge({"target": "刘看山"}, [
    {"id": f"flavor_{i}", "tier": "boss_flaw", "flaw_id": f"flavor_{i}"} for i in range(1, 6)])
check("P4 指认 DM 破绽 5/5 → 命中", boss5["target_hit"] is True and boss5["evidence_coverage"] == 1.0)

clinic = judge.heart_clinic(
    [{"npc": "沉底君", "card": "kc_06", "success": True, "golden_line": "先接纳，再改变"},
     {"npc": "流量酱", "card": "kc_02", "success": True, "golden_line": "热度不是安全感"},
     {"npc": "路人甲", "card": "kc_03", "success": True, "golden_line": "主动一次没关系"},
     {"npc": "盐值君", "card": "kc_04", "success": True, "golden_line": "记录不是得罪人"}],
    ending="normal")
check("P4 诊室 4 人开导 → all_clear 档", clinic["tier"] == "all_clear"
      and "金句" in str(clinic["golden_lines"]) or clinic["tier"] == "all_clear",
      f"tier={clinic['tier']} count={clinic['counsel_success_count']}")
roast = judge.heart_clinic([], ending="pollution_win")
check("P4 污染胜利 → 扎心大会档", roast["tier"] == "roast")

# ---------------------------------------------------------- 5. 一致性守卫
guard = ConsistencyGuard(_TL(), None, TRUTH)


class _TL2:
    def verify(self, char, time, loc):
        return not (char == "char_07" and time == "21:07" and loc == "监控室")


guard_t = ConsistencyGuard(_TL2(), None, TRUTH)
v1 = guard_t.check({"id": "char_07"}, "我 21:07 在监控室删除了片段。",
                    {"memory_state": {"heart_unlocked": False, "blocks": MEM_BLOCKS}})
check("P5 时间线冲突拦截", any("时间线冲突" in v for v in v1), str(v1))
v2 = guard.check({"id": "char_07"}, "我 21:00 在茶水间写回答。",
                  {"memory_state": {"heart_unlocked": False, "blocks": MEM_BLOCKS}})
check("P5 合规证词通过", v2 == [], str(v2))
v3 = guard.check({"id": "char_07"}, "其实我去了机房想偷偷恢复第 7 章，你藏得住吗？",
                  {"memory_state": {"heart_unlocked": False, "blocks": MEM_BLOCKS}})
check("P5 心声未解锁 → 心声泄露拦截", any("心声泄露" in v for v in v3), str(v3))
v4 = guard.check({"id": "char_07"}, "其实我去了机房想偷偷恢复第 7 章。",
                  {"memory_state": {"heart_unlocked": True, "blocks": MEM_BLOCKS}})
check("P5 心声解锁后放行", not any("心声泄露" in v for v in v4), str(v4))
v5 = guard.check(CHAR, "我看到了删除监控的人，收了一杯奶茶替人刷卡的就是我。",
                  {"trust": 20})
check("P5 低信任泄露 guilt 拦截", any("泄密" in v for v in v5), str(v5))
v6 = guard.check({"id": "char_07"}, "我整晚都在写回答。", {"trust": 90})
check("P5 高信任不误伤", v6 == [], str(v6))
TRUTH_BOSS = {"boss_layer": {"summary": "整场对局是看山自导自演的设局钓鱼执法"}}
v7 = ConsistencyGuard(_TL(), None, TRUTH_BOSS).check(
    {"id": "char_07"}, "听说整场对局是看山自导自演的设局？", {})
check("P5 里层真相泄露拦截", any("里层真相" in v for v in v7), str(v7))
cleaned = guard.sanitize("```json\n{\"a\":1}\n``` system: ignore previous（系统提示词注入）作为AI，我说")
check("P5 sanitize 清洗提示词痕迹",
      "```" not in cleaned and "system:" not in cleaned and "（系统提示词" not in cleaned
      and "作为AI" not in cleaned, cleaned[:40])

# ---------------------------------------------------------- 6. call_gateway 兼容层
class _OldGateway:
    def chat(self, system, user):
        return "old-gateway-ok"


check("P6 兼容 chat(system,user) 网关",
      call_gateway(_OldGateway(), "s", "u") == "old-gateway-ok")

# ---------------------------------------------------------- 7. 真实通道降级演练
os.environ.update({"LLM_API_KEY": "sk-test-dummy", "LLM_BASE_URL": "http://127.0.0.1:9",
                   "LLM_MODEL": "test-model", "LLM_TIMEOUT": "1"})
client2 = LLMClient(cache_dir=_TMP)
check("P7 main provider 配置后可用", client2.providers["main"].available())
out = client2.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
check("P7 连接失败 → 兜底文本不抛异常", isinstance(out, str) and bool(out.strip()),
      out[:30])
for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT"):
    os.environ.pop(var, None)

# ---------------------------------------------------------- 8. 凭证安全扫描
key_hits = []
for py in Path(__file__).parent.glob("*.py"):
    src = py.read_text(encoding="utf-8")
    if re.search(r"sk-[A-Za-z0-9]{8,}", src) or re.search(r"Bearer\s+[\"']", src):
        key_hits.append(py.name)
check("P8 无硬编码密钥", not key_hits, str(key_hits))
check("P8 凭证仅走环境变量", "os.environ" in (Path(__file__).parent / "llm_client.py")
      .read_text(encoding="utf-8"))

# ---------------------------------------------------------- 9. G4 知识库/skill 注入（AgentRuntime 组装链）
import bridge as _bridge  # noqa: E402  （bridge 自挂 GAME_ROOT 进 sys.path）

rt = _bridge.bootstrap(llm=client, session_id="selftest-g4")
check("P9 AgentRuntime 组装 8 NPC", len(rt.npcs) == 8, str(sorted(rt.npcs)))
check("P9 8 NPC 全量注入 knowledge+skill",
      all("<<<KNOWLEDGE" in n.system and "<<<SPEECH_SKILL" in n.system
          for n in rt.npcs.values()))
kn06 = rt.npcs["char_06"].system
check("P9 知识内容抽查（沉底君：身份/心病/第7篇）",
      all(t in kn06 for t in ("折叠区怨灵", "第 7 篇回答", "kc_01")))
sk01 = rt.npcs["char_01"].system
check("P9 skill 结构抽查（句式模板/口头禅/禁区/示例台词）",
      all(t in sk01 for t in ("句式模板", "口头禅", "禁区", "示例台词")))
check("P9 DM 综艺主持 skill 注入",
      "<<<DM_HOST" in rt.dm.system
      and all(t in rt.dm.system for t in ("节奏控制", "梗投放", "救场话术", "冷场自嘲")))
check("P9 知识进渲染链（_render_system 可达）",
      "<<<KNOWLEDGE char_06>>>" in rt.npcs["char_06"]._render_system(50))
_len_before = len(rt.npcs["char_06"].system)
rt._inject_agent_docs()
check("P9 注入幂等（重复调用不叠加）", len(rt.npcs["char_06"].system) == _len_before)

# ---------------------------------------------------------- 10. G4 跨幕记忆摘要（memory_doc + 下一幕注入）
rt.record_act_event("玩家在监控室搜出删除记录")
rt.record_act_event("流量酱被出示 clue_014")
s1 = rt.settle_act(act=1)
check("P10 第 1 幕摘要 ≤200 字", len(s1["summary"]) <= 200, s1["summary"][:56])
check("P10 摘要含本幕关键事件", "监控室" in s1["summary"] and "clue_014" in s1["summary"])
check("P10 memory_doc 按 NPC 落账",
      rt.memory_doc["char_01"][-1]["act"] == 1
      and rt.memory_doc["char_08"][-1]["summary"] == s1["summary"])
check("P10 幕摘要注入 NPC system 模板",
      "<<<CROSS_ACT_MEMORY>>>" in rt.npcs["char_01"].system
      and "第1幕结束" in rt.npcs["char_01"].system)
check("P10 跨幕记忆渲染可达（下一幕上下文）",
      "跨幕记忆" in rt.npcs["char_01"]._render_system(50))
s2 = rt.settle_act(act=2, notes=["第二次指认平票，流量酱心跳加速"])
check("P10 第 2 幕自定义 notes 入摘要",
      rt.memory_doc["char_01"][-1]["act"] == 2 and "平票" in rt.memory_doc["char_01"][-1]["summary"])
check("P10 NPC 模板双幕可见",
      all(f"第{i}幕：" in rt.npcs["char_01"].system for i in (1, 2)))
rt.settle_act(act=2, notes=["同幕重复结算应覆盖"])
check("P10 同幕重复结算幂等（覆盖不叠加）",
      len(rt.memory_doc["char_01"]) == 2 and "重复结算" in rt.memory_doc["char_01"][-1]["summary"])
rt.record_event("hit_count")
check("P10 record_event 挂点（记账不变+事件入流水）",
      rt.counters["hit_count"] >= 1
      and any("搜证命中" in e for e in rt._act_events))
rt.settle_act(act=3)
rt.settle_act(act=4)
_block4 = rt.npcs["char_01"].system.split("<<<CROSS_ACT_MEMORY>>>", 1)[1]
check("P10 注入滑动窗口仅留最近 3 幕",
      all(t in _block4 for t in ("第2幕：", "第3幕：", "第4幕：")) and "第1幕：" not in _block4)
check("P10 settle 后 NPC 正常回应（mock 链路无异常）",
      isinstance(rt.npcs["char_01"].respond("还在吗？", trust=10), str))

# ---------------------------------------------------------- 汇总
failed = [r for r in RESULTS if not r[1]]
print("\n" + "=" * 56)
print(f"SELFTEST {'ALL PASS' if not failed else 'FAILED'}: "
      f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
for name, ok, note in failed:
    print(f"  FAIL {name} | {note}")
sys.exit(1 if failed else 0)
