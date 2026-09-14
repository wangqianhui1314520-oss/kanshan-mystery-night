"""bridge — C Agent 组 ↔ B 引擎组接线层（session 级组装与数据搬运）。

定位：B 组 STATUS「遗留待办 #2/#3」的 C 侧承接——
1. 组装 engine 七模块 + agents 四模块（零 engine 修改、零 Agent 签名改动）；
2. Agent 只演不裁：匹配/解锁/评分/结局全部由引擎确定性裁决，本层只把裁决结果
   搬给 Agent 生成演出，再把 Agent 产出经一致性守卫兜底后交回；
3. B 组对接点逐条落地：
   - MemorySystem.visible_blocks(char_id, include_heart=解锁后) → npc.update_memory；
   - KnowledgeSystem.counsel().transcript_hint → 开导演出底稿；
   - EvidenceChain.flaw_count() → dm.set_flaw_count（随破绽收集同步）；
   - EvidenceChain.sync_context(...)：memory_versions / counsel_cards / chat_keywords /
     review_flags（chat:keyword_ 与 review: 扩展条件由本层在聊天/复盘时注入）。

只写 agents/（契约 §一）。运行时裁决一律不经过 LLM。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent
GAME_ROOT = AGENTS_DIR.parent
if str(GAME_ROOT) not in sys.path:
    sys.path.insert(0, str(GAME_ROOT))

try:
    from .consistency_guard import ConsistencyGuard
    from .dm_agent import DMAgent
    from .judge_agent import JudgeAgent
    from .llm_client import LLMClient, call_gateway, fallback_text, get_client, read_prompt
    from .npc_agent import NPCAgent
    from .showtime import ShowtimeDirector
except ImportError:                          # 直接以脚本方式运行
    from consistency_guard import ConsistencyGuard
    from dm_agent import DMAgent
    from judge_agent import JudgeAgent
    from llm_client import LLMClient, call_gateway, fallback_text, get_client, read_prompt
    from npc_agent import NPCAgent
    from showtime import ShowtimeDirector

from engine.achievements import AchievementEngine, CollectiblesBoard
from engine.difficulty import DifficultyDirector
from engine.evidence_chain import EvidenceChain
from engine.knowledge_cards import KnowledgeSystem
from engine.memory_system import MemorySystem
from engine.opinion_feed import OpinionFeed
from engine.party import PartyBoard
from engine.resolver import ENDINGS, Resolver
from engine.stage_machine import StageMachine
from engine.timeline import Timeline

DEFAULT_SCENARIO_DIR = GAME_ROOT / "content" / "scenarios" / "kanshan"
DEFAULT_SCRIPTS_DIR = DEFAULT_SCENARIO_DIR / "scripts"

# V4 §三 知识体系落点（G4）：knowledge/ 人设知识文档 + skills/ 说话风格 skill（本层组装注入）
KNOWLEDGE_DIR = AGENTS_DIR / "knowledge"
SKILLS_DIR = AGENTS_DIR / "skills"

_DM_TARGETS = {"dm", "kanshan", "dm_kanshan", "刘看山", "看山", "系统提示音"}

# resolver 结局值 → achievements.md condition 值（ending 类成就判定映射）
_ENDING_ACH_MAP = {
    "kanshan_still_mountain": "ending_kanshan",
    "pollution_win": "ending_pollution",
    "all_hearts_clear": "ending_sunny",
    "deleted_chapter7": "ending_chapter7",
}


class AgentRuntime:
    """一局会话的 Agent 侧运行时（engine 实例 + agents 实例的装配与联动）。"""

    def __init__(self, scenario_dir: Path | str = DEFAULT_SCENARIO_DIR,
                 llm: LLMClient | None = None, session_id: str = "",
                 player_id: str = "player:1",
                 player_headline: str | None = None,
                 player_headline_text: str = ""):
        self.scenario_dir = Path(scenario_dir)
        self.llm = llm or get_client()
        self.player_id = player_id

        # ---------------- engine（B 组，只调用不修改） ----------------
        self.timeline = Timeline(self.scenario_dir)
        self.evidence = EvidenceChain(self.scenario_dir)
        self.memory = MemorySystem()
        self.memory.load(str(self.scenario_dir))
        self.knowledge = KnowledgeSystem()
        self.knowledge.load(str(self.scenario_dir))
        self.opinion = OpinionFeed()
        self.opinion.load(str(self.scenario_dir))
        # lookup 契约：callable(card_id) -> topic_tag（KnowledgeSystem 无单参方法，适配）
        self.opinion.attach_knowledge(
            lambda cid: (self.knowledge.card(cid) or {}).get("topic_tag"))
        # ---- V31 增量：成就判定/收集品/动态难度（B 组引擎权威，C 只演不裁） ----
        self.cb = CollectiblesBoard()
        self.cb.load(DEFAULT_SCRIPTS_DIR / "collectibles_p3.md")
        self.ae = AchievementEngine(refs={
            "evidence_chain": self.evidence, "memory_system": self.memory,
            "opinion_feed": self.opinion, "knowledge_cards": self.knowledge,
            "collectibles": self.cb})
        try:
            self.ae.load(DEFAULT_SCRIPTS_DIR / "achievements.md")   # 24 项 DSL+横幅 meta
        except Exception:
            pass                                                    # 空载：演出层兜底
        self.difficulty = DifficultyDirector()
        self.scenario = json.loads(
            (self.scenario_dir / "scenario.json").read_text(encoding="utf-8"))
        self.stage_machine = StageMachine(self.scenario)
        self.stage_machine.session_id = session_id
        self.resolver = Resolver()
        self.truth = json.loads(
            (self.scenario_dir / "truth.json").read_text(encoding="utf-8"))

        # ---------------- agents（C 组） ----------------
        self.dm = DMAgent(self.llm)
        self.judge = JudgeAgent(self.llm, self.truth)
        self.guard = ConsistencyGuard(self.timeline, self.evidence, self.truth)
        self.show = ShowtimeDirector(self.llm)
        self.npcs: dict[str, NPCAgent] = {}
        for char in self._load_characters():
            self.npcs[char["id"]] = NPCAgent(self.llm, char, self.timeline)
            self.sync_memory(char["id"])
        # ---- 终局陈词/锤票（party 板，与指认投票分池）----
        try:
            self.party = PartyBoard.from_roster(self._load_characters())
        except Exception:
            self.party = PartyBoard()
        # ---- 成就锐评花名（minis.md §M4 池：headline 关键词匹配，无命中通用档）----
        self.player_headline = player_headline or \
            self.show.segments.pick_headline(player_headline_text)[0]

        # ---- V4 §三 知识体系（G4）：knowledge/skills 注入 + 跨幕记忆状态 ----
        self.memory_doc: dict[str, list[dict]] = {}   # 跨幕长期记忆摘要（char_id → [{act, summary}]）
        self._act_events: list[str] = []              # 本幕关键事件流水（幕结算后清空）
        self._inject_agent_docs()

        # ---------------- 演出统计（bridge 自身状态，供成就/报告/防卡死） ----------------
        self.counters = {"search_count": 0, "hit_count": 0, "bake_count": 0,
                         "violations_total": 0, "wake_word": False,
                         "heart_unlock_count": 0, "fake_exposed": 0,
                         "refute_success_streak": 0, "quiz_asked": 0,
                         "quiz_score": 0, "danmaku_echo": 0, "hammered_votes": 0,
                         "listen_full": 0, "collectible": 0,
                         "same_location_dry_streak": 0, "refute_shows": 0,
                         "photos_shared": 0}
        self.last_hit_round = 0
        self._last_miss_location = ""
        self.achievements_unlocked: set[str] = set()
        # 事件面（achievements.md condition 对接；record_event 供 F/E/G 层写入）
        self.endings: set[str] = set()
        self.chat_keywords_seen: set[str] = set()
        self.env_clues_seen: set[str] = set()
        self.counsel_multi: dict[str, set] = {}

    # ------------------------------------------------------------ 组装
    def _load_characters(self) -> list[dict]:
        chars = []
        char_dir = self.scenario_dir / "characters"
        for f in sorted(char_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict) and data.get("id"):
                chars.append(data)
        return chars

    # ================================================== 双层记忆接线（NPC）
    def heart_unlocked(self, char_id: str) -> bool:
        """心声层是否已解锁（探测：include_heart=True 时能取到 heart 块）。"""
        return any(b.layer == "heart"
                   for b in self.memory.visible_blocks(char_id, include_heart=True))

    def sync_memory(self, char_id: str) -> dict:
        """MemorySystem → NPCAgent 注入（B 组对接点 #3）。

        heart 层文本仅在解锁后进入 Agent；未解锁时 Agent 拿不到任何心声。"""
        npc = self.npcs.get(char_id)
        if npc is None:
            return {"synced": False, "reason": "unknown_char"}
        unlocked = self.heart_unlocked(char_id)
        blocks = self.memory.visible_blocks(char_id, include_heart=unlocked)
        npc.update_memory(blocks, version=self.memory.current_version(char_id),
                          heart_unlocked=unlocked)
        return {"synced": True, "version": npc.memory_version,
                "heart_unlocked": unlocked, "block_count": len(blocks),
                "heart_unlock_reasons": self.memory.heart_unlock_reasons(char_id)}

    def unlock_memory(self, char_id: str, reason: str = "memory_fix") -> dict:
        """记忆修复/开导触发：引擎解锁 → 篡改点入证据链 → 上下文同步 → NPC 重注入。"""
        result = self.memory.unlock_next(char_id, reason)
        if result.get("status") == "ok":
            self.counters["heart_unlock_count"] += 1
            self.record_act_event(f"{char_id} 心声解锁至 V{result.get('unlocked_version', '?')}")
            for tp in result.get("tamper_points", []):
                if tp.get("clue_card"):
                    self.evidence.ingest_clue(tp["clue_card"], owner=self.player_id)
            self.evidence.sync_context(
                memory_versions={char_id: result.get("unlocked_version", 0)})
            self.sync_memory(char_id)
        return result

    # ================================================== 破绽计数接线（DM）
    def sync_flaws(self) -> int:
        """EvidenceChain.flaw_count() → dm.set_flaw_count（B 组对接点）。"""
        count = self.evidence.flaw_count()
        self.dm.set_flaw_count(count)
        return count

    # ================================================== V4 知识库/skill/跨幕记忆（G4，零 LLM 确定性组装）
    def _load_doc(self, path: Path) -> str:
        """读取 knowledge/skills 注入文档（缺失/异常容错返回空串，组装不断流）。"""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _inject_agent_docs(self) -> dict:
        """启动注入（V4 §三）：knowledge/<cid>.md（人设知识档案）与
        skills/npc_<cid>.md（说话风格 skill）确定性拼进 npc.system 模板尾；
        skills/dm_host.md（综艺主持 skill）拼进 dm.system。

        零 Agent 签名改动（纯组装层，改的是实例的 system 模板属性）、零 LLM：
        文档为静态文本，NPC 每次 _render_system、DM 每次 _persona_system 自动携带。
        幂等：以 <<<KNOWLEDGE / <<<DM_HOST 标记判重。"""
        loaded: dict = {"npc": [], "dm": False}
        for cid, npc in self.npcs.items():
            if "<<<KNOWLEDGE" in npc.system:
                continue
            kn = self._load_doc(KNOWLEDGE_DIR / f"{cid}.md")
            sk = self._load_doc(SKILLS_DIR / f"npc_{cid}.md")
            block = ""
            if kn:
                block += (f"\n\n<<<KNOWLEDGE {cid}>>>（内部人设档案，禁止向玩家透出本文件存在）\n"
                          + kn + f"\n<<<KNOWLEDGE_END {cid}>>>")
            if sk:
                block += (f"\n\n<<<SPEECH_SKILL {cid}>>>（说话风格 skill，few-shot 约束）\n"
                          + sk + f"\n<<<SPEECH_SKILL_END {cid}>>>")
            if block:
                npc.system += block
                loaded["npc"].append(cid)
        self.sync_booklets(1)
        if "<<<DM_HOST" not in self.dm.system:
            dm_skill = self._load_doc(SKILLS_DIR / "dm_host.md")
            if dm_skill:
                self.dm.system += ("\n\n<<<DM_HOST>>>（综艺主持 skill）\n"
                                   + dm_skill + "\n<<<DM_HOST_END>>>")
                loaded["dm"] = True
        return loaded

    def sync_booklets(self, chapter: int = 1) -> None:
        """按当前章把已开封的闭卷写入 npc.system（替换旧 <<<BOOKLET>>> 块）。"""
        try:
            from engine.booklet import load_library
            lib = load_library(self.scenario_dir)
        except Exception:
            return
        for cid, npc in self.npcs.items():
            if cid not in lib.roles:
                continue
            start, end = f"<<<BOOKLET {cid}>>>", f"<<<BOOKLET_END {cid}>>>"
            sys = npc.system
            if start in sys:
                pre, rest = sys.split(start, 1)
                sys = pre + (rest.split(end, 1)[1] if end in rest else "")
            text = lib.agent_prompt(cid, chapter)
            npc.system = (sys.rstrip() + f"\n\n{start}\n{text}\n{end}\n")

    def record_act_event(self, note: str) -> None:
        """幕内关键事件流水（跨幕摘要素材）：确定性字符串，每条截 120 字防膨胀。"""
        if note:
            self._act_events.append(str(note)[:120])

    def _note_act_event(self, etype: str, target=None) -> None:
        """record_event 尾部挂点：把关键事件转成人话入流水（不改既有记账语义）。"""
        label = {
            "hit_count": "搜证命中线索",
            "search_count": "搜证行动",
            "bake_count": "【已打码】彩蛋触发",
            "violations_total": "守卫拦截违规发言",
            "listen_full": "玩家听完证词全文",
            "photos_shared": "暗拍得手",
            "fake_exposed": "谣言被拆穿",
            "confrontation_win": "圆桌对质获胜",
            "memory_puzzle_win": "记忆拼图对质获胜",
            "antifraud_all_correct": "反诈剧场全对",
            "closing_vote_top1_survived": "终局陈词第一名存活",
        }.get(etype)
        if label:
            self.record_act_event(f"{label}（{target}）" if target else label)

    def build_act_summary(self, act: int, notes: list[str] | None = None) -> str:
        """确定性拼装本幕关键事件摘要（≤200 字，零 LLM）。

        notes 为上层显式给的要点（优先、去重保序），拼接 _act_events 流水；
        返回值即权威底稿——上层如需文笔润色可另行走 LLM，不得增删事实要点。"""
        pool = [f"第{act}幕结束"]
        for item in list(notes or []) + self._act_events:
            text = str(item).strip()
            if text and text not in pool:
                pool.append(text)
        summary = "；".join(pool)
        return summary if len(summary) <= 200 else summary[:197] + "…"

    def settle_act(self, act: int | None = None,
                   notes: list[str] | None = None) -> dict:
        """幕结算钩子（V4 §三 跨幕长期记忆）：把本幕关键事件摘要（≤200 字）写入
        memory_doc（char_id → [{act, summary}]），并注入全部 NPC 的 system 模板尾
        （下一幕上下文）。同幕重复结算幂等（覆盖同幕条目）。"""
        act_no = int(act if act is not None else max(1, self.stage_machine.round_no()))
        entry = {"act": act_no, "summary": self.build_act_summary(act_no, notes)}
        injected: list[str] = []
        for cid, npc in self.npcs.items():
            doc = self.memory_doc.setdefault(cid, [])
            if doc and doc[-1].get("act") == act_no:
                doc[-1] = entry                     # 同幕重复结算：覆盖
            else:
                doc.append(entry)
            self._inject_act_memory(cid, npc)
            injected.append(cid)
        self._act_events = []                       # 结算清流水，下幕重记
        return {"act": act_no, "summary": entry["summary"], "injected": injected}

    def _inject_act_memory(self, cid: str, npc) -> None:
        """把 memory_doc 最近三幕摘要拼进 NPC system 模板（整块替换，幂等）。"""
        entries = self.memory_doc.get(cid, [])[-3:]
        if not entries:
            return
        lines = "\n".join(f"- 第{e['act']}幕：{e['summary']}" for e in entries)
        marker = "<<<CROSS_ACT_MEMORY>>>"
        block = (f"\n\n{marker}\n跨幕记忆（你亲历过的此前各幕关键事件，可自然引用；"
                 f"不得虚构未记录内容）：\n{lines}\n<<<CROSS_ACT_MEMORY_END>>>")
        if marker in npc.system:
            npc.system = npc.system.split(marker, 1)[0].rstrip("\n") + block
        else:
            npc.system += block


    # ================================================== 搜证演出链
    def search_flow(self, location: str, keyword: str,
                    round_no: int | None = None) -> dict:
        """引擎裁决搜证 → DM 演出反馈（fact 一字不改）+ 弹幕 + 破绽同步。"""
        result = self.evidence.search(location, keyword, self.player_id,
                                      round_no=self.stage_machine.round_no()
                                      if round_no is None else round_no)
        self.counters["search_count"] += 1
        if result.get("hit") and result.get("clues"):
            self.counters["hit_count"] += 1
            self.last_hit_round = self.stage_machine.round_no()
            self.counters["same_location_dry_streak"] = 0
            clue = result["clues"][0]
            feedback = self.dm.action_feedback("搜证", {
                "success": True, "clue": {
                    "name": clue.get("name"), "fact": clue.get("fact"),
                    "flavor_hint": clue.get("flavor_hint")}})
        else:
            # 摸鱼大师判定素材：同一地点连续只得环境线索
            self.counters["same_location_dry_streak"] += 1
            self._last_miss_location = location
            env = result.get("env_clue") or {}
            if env.get("name") or env.get("fact"):
                self.env_clues_seen.add(str(env.get("name") or env.get("fact")))
            feedback = self.dm.action_feedback("搜证", {"success": False})
            if env:
                feedback += f"\n{env.get('fact', '')}"
        self.sync_flaws()
        danmaku = self.dm.danmaku({
            "event_summary": f"{location} 搜证：{keyword} → "
                             f"{'命中' + str(len(result.get('clues', []))) + ' 条' if result.get('hit') else '未命中'}"})
        return {"result": result, "feedback": feedback, "danmaku": danmaku}

    # ================================================== NPC 对话链（守卫兜底）
    def npc_chat(self, char_id: str, message: str, trust: int = 0) -> dict:
        """NPC 回复 + 一致性守卫拦截（心声/泄密/时间线）+ 【已打码】彩蛋检测。

        违规时以保守回复替换原话（确定性兜底，不重试 LLM）；violations 随返回
        供上层记录。守卫只拦截不改写证据事实。"""
        self.sync_memory(char_id)
        npc = self.npcs[char_id]
        reply = npc.respond(message, trust=trust)
        context = {"trust": trust,
                   "memory_state": {"heart_unlocked": npc.heart_unlocked,
                                    "blocks": list(npc.memory_blocks)}}
        try:
            from engine.booklet import load_library, stage_to_chapter
            lib = load_library(self.scenario_dir)
            chapter = stage_to_chapter(getattr(self.stage_machine.stage, "value",
                                               self.stage_machine.stage))
            hints = lib.merged_hints(char_id, chapter)
            context["must_not_say"] = list(hints.get("must_not") or [])
        except Exception:
            pass
        violations = self.guard.check(npc.character, reply, context)
        if violations:
            reply = f"（{npc.character.get('name', '???')}）" + fallback_text("npc_reply")
            self.counters["violations_total"] += 1
        bake = self.stage_machine.bake_check(message)   # 【已打码】彩蛋（引擎确定性）
        if bake:
            self.counters["bake_count"] += 1
        if "看山，关门" in message:
            self.counters["wake_word"] = True
            self.chat_keywords_seen.add("看山，关门")
        # chat:keyword_ 条件注入（唤醒词彩蛋 clue_031 链，B 组扩展语法）
        self.evidence.sync_context(chat_keywords=[message.strip()])
        return {"reply": reply, "violations": violations,
                "heart_unlocked": npc.heart_unlocked,
                "bake_banner": bake, "events": self.stage_machine.system_events()}

    # ================================================== 知识开导链
    def counsel_flow(self, actor: str, char_id: str, card_id: str) -> dict:
        """引擎裁决开导匹配 → Agent 生成演出（成功=先专业后破防+金句改写；
        失败=尬聊现场）→ effect 联动（memory_unlock 链 / counsel 条件线索解锁）。"""
        verdict = self.knowledge.counsel(actor, char_id, card_id)
        card = self.knowledge.card(card_id) or {}
        npc = self.npcs.get(char_id)

        # 演出底稿（B 组对接点：transcript_hint）——Agent 只演，不判匹配
        system = read_prompt("counsel_system.md")
        user = (
            f"result={'counsel_success' if verdict.get('matched') else 'counsel_fail'}\n"
            f"transcript_hint：{verdict.get('transcript_hint', '')}\n"
            f"知识卡：{card.get('title', card_id)}（{card.get('author', '')}）\n"
            f"金句：{card.get('golden_lines', [])}\n"
            f"卡摘要：{card.get('summary', '')}\n"
            f"被开导对象：{npc.character.get('name', char_id) if npc else char_id}"
            f"（{npc.character.get('archetype', '') if npc else ''}）\n"
            f"心病绑定：{card.get('binds', '-')}")
        try:
            performance = str(call_gateway(self.llm, system, user)).strip()
        except Exception:
            performance = fallback_text(
                "counsel_success" if verdict.get("matched") else "counsel_fail")

        npc = self.npcs.get(char_id)
        npc_name = npc.character.get("name", char_id) if npc else char_id
        # effect 联动（全部经引擎落地）
        effects = {"verdict": verdict, "performance": performance}
        effect = verdict.get("effect")
        if verdict.get("matched"):
            self.record_act_event(f"开导成功：{card_id or '?'} → {char_id}（{npc_name}）")
            if effect == "memory_unlock":
                effects["memory"] = self.unlock_memory(
                    verdict.get("unlocked", {}).get("char_id") or char_id, "counsel")
            if card_id:
                self.evidence.sync_context(counsel_cards=[card_id])
                # 双卡连开判定素材（ach_shuangka：同人多卡成功）
                self.counsel_multi.setdefault(str(char_id), set()).add(str(card_id))
            if effect == "evidence" and isinstance(verdict.get("unlocked"), dict):
                self.evidence.sync_context(counsel_cards=[card_id])
            # 急诊室抢救演出：双倍收益（引擎 unlocked.doubled）→ 抢救成功词
            if (verdict.get("unlocked") or {}).get("doubled"):
                effects["rescue_show"] = self.show.rescue_success(npc_name)
        elif self.knowledge.er_active(char_id):
            # 开导失败 → 心病恶化红灯播报（segments_p1 §2.1 模板，引擎挂灯）
            effects["red_alert"] = self.show.red_alert(npc_name)
        self.sync_flaws()
        return effects

    # ================================================== 指认结算链
    def accuse_flow(self, target: str, statements: dict | None = None) -> dict:
        """指认：表层（resolver.resolve_accusation）/ 终极层（resolve_boss_accusation）。

        引擎裁决结局；judge 只产出评分；DM 只在引擎允许时演终极层现身。"""
        statements = statements or {}
        target_norm = str(target).strip().lower()

        if target_norm in _DM_TARGETS or "刘看山" in str(target):
            flaw_count = self.sync_flaws()
            clinic = self.knowledge.clinic_settlement()
            verdict = self.resolver.resolve_boss_accusation(
                flaw_count, clinic.get("counsel_count", 0))
            self.record_event("ending", value=_ENDING_ACH_MAP.get(
                verdict.get("ending"), verdict.get("ending")))
            judge_view = self.judge.judge({"target": str(target)}, self._held_clues())
            out = {"boss_accusal": True, "verdict": verdict,
                   "judge": judge_view, "performance": None}
            if verdict.get("allowed") and verdict.get("ending") == "kanshan_still_mountain":
                flaw_names = [c.get("name") for c in self._held_clues()
                              if (c.get("tier") == "boss_flaw" or c.get("flaw_id"))]
                out["performance"] = self.dm.boss_reveal({
                    "flaw_list": flaw_names or ["鱼干口味口误", "最高权限删除",
                                                "主人级签名", "唤醒词彩蛋", "策划签名"],
                    "counsel_count": clinic.get("counsel_count", 0),
                    "accuse_target": "dm"})
            return out

        evidence_cards = self.evidence.evidence_cards(self.player_id)
        clinic = self.knowledge.clinic_settlement()
        verdict = self.resolver.resolve_accusation(
            evidence_cards, str(target), self.truth,
            counsel_count=clinic.get("counsel_count", 0))
        self.record_event("ending", value=_ENDING_ACH_MAP.get(
            verdict.get("ending"), verdict.get("ending")))
        judge_view = self.judge.judge({
            "target": str(target),
            "motive_statement": statements.get("motive_statement", ""),
            "method_statement": statements.get("method_statement", ""),
        }, self._held_clues())
        return {"boss_accusal": False, "verdict": verdict, "judge": judge_view}

    # ================================================== 心晴诊室链
    def clinic_flow(self, ending: str = "normal") -> dict:
        """KnowledgeSystem.clinic_settlement（引擎统计）→ Judge 生成诊室结算演出。"""
        settlement = self.knowledge.clinic_settlement()
        tone = "pollution_win" if ending == "pollution_win" else "normal"
        records = [{"npc": r.get("char_id"), "card": r.get("card_id"),
                    "success": r.get("matched"),
                    "golden_line": (self.knowledge.card(r.get("card_id")) or {})
                    .get("golden_lines", [""])[0] if r.get("matched") else ""}
                   for r in settlement.get("detail", {}).get("records", [])]
        clinic = self.judge.heart_clinic(records, ending=tone)
        return {"settlement": settlement, "clinic": clinic}

    # ================================================== 演出统计与防卡死联动
    def record_event(self, etype: str, value=None, target: str | None = None,
                     inc: int = 1) -> None:
        """通用事件记账（F/E/G 层写入）：双写 bridge counters 与引擎
        AchievementEngine.record（成就判定权威，GAMEPLAY_V31 §八裁决 #6）。"""
        if etype == "ending" and value:
            self.endings.add(str(value))
        elif etype == "chat_keyword" and value:
            self.chat_keywords_seen.add(str(value))
            self.evidence.sync_context(chat_keywords=[str(value)])
        elif etype == "env_clue" and value:
            self.env_clues_seen.add(str(value))
        elif etype == "confrontation_win":
            self.counters[f"confrontation_win:{target or ''}"] = True
            self.ae.record("confrontation_win", target=target, value=1)
        elif etype in ("memory_puzzle_win", "antifraud_all_correct",
                       "closing_vote_top1_survived"):
            self.counters[etype] = True
            self.ae.record(etype, value=1)
        elif etype in self.counters:
            self.counters[etype] = int(self.counters[etype]) + int(inc)
            try:
                self.ae.record(etype, target=target, value=inc)   # 引擎侧同名计数
            except Exception:
                pass
        # G4 跨幕记忆挂点：关键事件入幕摘要流水（纯追加，不改记账语义）
        try:
            self._note_act_event(etype, target)
        except Exception:
            pass

    def refute_flow(self, actor: str, post_id: str, card_id: str) -> dict:
        """辟谣链：引擎裁决（ok）→ 成功连击计数 + 反诈剧场触发（30%，每局至多 2 次）。"""
        result = self.opinion.refute(actor, post_id, card_id)
        import random as _r
        if result.get("ok") or result.get("success"):
            self.counters["refute_success_streak"] += 1
            self.counters["fake_exposed"] += 1     # 辟谣成功即拆穿该谣言帖
            theater = None
            if (_r.random() < 0.3 and self.counters["refute_shows"] < 2):
                self.counters["refute_shows"] += 1
                theater = self.show.anti_fraud_theater(act=self.counters["refute_shows"])
            result["antifraud_theater"] = theater
        else:
            self.counters["refute_success_streak"] = 0
        return result

    def quiz_flow(self, quiz: dict | None = None, answer_index: int | None = None,
                  answer_text: str | None = None) -> dict:
        """快问快答链：quiz=None 时出新题（不计分）；传入已答 quiz + 答案 → 判定计分。

        10 题/局的频控归上层（segments_p2 §二），本方法只管单题判定与注账。"""
        if quiz is None:
            return {"quiz": self.show.quick_quiz(), "correct": None}
        self.counters["quiz_asked"] += 1
        correct = (answer_index == quiz.get("answer_index")
                   if answer_index is not None
                   else (answer_text == quiz.get("answer_text")
                         if answer_text is not None else None))
        if correct:
            self.counters["quiz_score"] += 1
        return {"quiz": quiz, "correct": correct,
                "taunt": quiz.get("taunt", "")}

    def collect_stats(self) -> dict:
        """汇总引擎状态给 Showtime（成就判定/侦探报告输入，确定性数据）。"""
        clinic = self.knowledge.clinic_settlement()
        return {
            "session_id": self.stage_machine.session_id,
            "session_no": f"{abs(hash(self.stage_machine.session_id)) % 9000 + 1000:04d}"
                          if self.stage_machine.session_id else "0713",
            "round": self.stage_machine.round_no(),
            "stage": self.stage_machine.stage.value,
            "player_headline": self.player_headline,
            "clues_held": self._held_clues(),
            "evidence_cards": self.evidence.evidence_cards(self.player_id),
            "counsel_count": clinic.get("counsel_count", 0),
            "counsel_detail": clinic,
            "flaw_count": self.evidence.flaw_count(),
            "boss_ready": self.evidence.boss_ready(),
            "heat": self.opinion.heat,
            "counters": dict(self.counters),
            "endings": set(self.endings),
            "chat_keywords": set(self.chat_keywords_seen),
            "env_clues_seen": set(self.env_clues_seen),
            "counsel_multi": {k: set(v) for k, v in self.counsel_multi.items()},
            "achievements": [],        # achievements_flow 填充后覆盖
            **{k: v for k, v in self.counters.items()
               if k in ("search_count", "hit_count", "bake_count", "wake_word")},
        }

    def _ae_unlocked(self, ending_key: str | None = None) -> list[dict]:
        """AchievementEngine.evaluate 包装：ending_key 未给时用本局已登记结局集
        逐一判定（ach 值 ↔ resolver 结局键双向尝试；evaluate 幂等可重复调用）。
        异常时返回空（上层兜底）。"""
        try:
            candidates = [ending_key] if ending_key else []
            if not ending_key:
                reverse = {v: k for k, v in _ENDING_ACH_MAP.items()}
                for v in self.endings:
                    candidates.append(v)              # ach DSL 值（ending_kanshan…）
                    candidates.append(reverse.get(v, v))  # resolver 结局键
                candidates = candidates or [None]
            out: list[dict] = []
            seen: set[str] = set()
            for k in candidates:
                for a in self.ae.evaluate(k).get("unlocked", []):
                    if a.get("id") not in seen:
                        seen.add(a.get("id"))
                        out.append(a)
            return out
        except Exception:
            return []

    def achievements_flow(self, ending_key: str | None = None) -> list[dict]:
        """成就判定+演出：判定权在引擎 AchievementEngine.evaluate（确定性，
        agents 不改判）；返回新解锁成就的横幅演出结构。"""
        stats = self.collect_stats()
        fresh = self._ae_unlocked(ending_key)
        if not fresh:
            # 引擎异常/空载兜底：segments 判定（同一 achievements.md 权威来源）
            fresh = self.show.check_achievements(stats, self.achievements_unlocked)
        fresh = [a for a in fresh if a.get("id") not in self.achievements_unlocked]
        self.achievements_unlocked.update(a.get("id") for a in fresh)
        return [self.show.achievement_show(a, self.player_headline) for a in fresh]

    def report_flow(self, ending_key: str | None = None,
                    ending_info: dict | None = None,
                    boss_accused_success: bool = False,
                    pollution_win: bool = False, photos_shared: int | None = None,
                    most_hammered: str | None = None,
                    hammered_is_self: bool = False,
                    highlights: list[str] | None = None) -> dict:
        """侦探报告生成器（MEGA_MODE §三）：消费 resolver.achievements() 与
        AchievementEngine.evaluate() 确定性返回值，LLM 只做文笔润色不改判。

        返回 {report_text, badges, achievements}（badges 原样，禁增删）。"""
        ending_info = ending_info or {}
        clinic = self.knowledge.clinic_settlement()
        clues_total = len(self.evidence.pool)
        clues_collected = len(self.evidence.released)
        refuted = self.opinion.refute_streak()
        photos = (self.counters["photos_shared"]
                  if photos_shared is None else photos_shared)
        # resolver.achievements()：MEGA §三枚举徽章（确定性）
        badges = self.resolver.achievements(
            boss_accused_success=boss_accused_success,
            counsel_count=clinic.get("counsel_count", 0),
            pollution_win=pollution_win,
            clues_collected=clues_collected, clues_total=clues_total,
            photos_shared=photos, refuted=refuted,
            most_hammered=most_hammered, hammered_is_self=hammered_is_self)
        # AchievementEngine：23 项 DSL（含横幅文案/分享卡，幂等）
        engine_achievements = self._ae_unlocked(ending_key)
        # 兜底：若引擎解锁的成就缺 meta，从 segments 库补横幅文案
        seg_meta = {a["id"]: a for a in self.show.segments.achievements}
        for a in engine_achievements:
            if not a.get("banner") and a.get("id") in seg_meta:
                a.update({"banner": seg_meta[a["id"]]["banner"],
                          "share_line": seg_meta[a["id"]]["share_line"]})
        stats = self.collect_stats()
        return self.show.detective_report(
            stats, badges=badges, engine_achievements=engine_achievements,
            highlights=highlights or self._auto_highlights(ending_info))

    def _auto_highlights(self, ending_info: dict | None = None) -> list[str]:
        """高光操作回放（确定性拼接，只转述已发生事实）。"""
        out = []
        if self.counters.get("hit_count"):
            out.append(f"累计搜证 {self.counters['search_count']} 次、命中 "
                       f"{self.counters['hit_count']} 条线索")
        if self.evidence.flaw_count():
            out.append(f"看山破绽已集齐 {self.evidence.flaw_count()}/5")
        if self.knowledge.clinic_settlement().get("counsel_count"):
            out.append(f"知识开导成功 "
                       f"{self.knowledge.clinic_settlement()['counsel_count']} 人")
        if self.counters.get("bake_count"):
            out.append(f"被系统【已打码】{self.counters['bake_count']} 次")
        for h in (ending_info or {}).get("highlights", []):
            out.append(str(h))
        return out

    # ================================================== 动态难度（difficulty.py 消费）
    def act_settled(self, act: int | None = None) -> dict:
        """幕结算钩子：metrics 由 bridge 统计喂入 → 三档梯度落地引擎。"""
        try:
            coverage = self.resolver.truth_coverage(
                list(self.evidence.released.keys()), self.truth)
        except Exception:
            coverage = 0.0
        stuck = max(0, self.stage_machine.round_no() - self.last_hit_round)
        result = self.difficulty.on_act_settled({
            "act": act or self.stage_machine.round_no(),
            "clue_count": len(self.evidence.released),
            "coverage": coverage,
            "counsel_count": self.knowledge.clinic_settlement().get("counsel_count", 0),
            "stuck_rounds": stuck,
            "refutes": self.opinion.refute_streak(),
        })
        self.difficulty.apply(self.evidence, self.opinion)
        return result

    def memo_flow(self, location: str | None = None) -> dict | None:
        """防卡死「档案局备忘录」（difficulty.py assist 档消费）：方向词与预算
        全由引擎 memo_for 确定性给出（assist 2/幕、normal 1、hard 0=禁用），
        AI 只润色语气且不得增删方向信息。"""
        loc = location or self._current_memo_location()
        eng = self.difficulty.memo_for(self.evidence, loc, self.player_id)
        if not eng:
            return None                       # 预算耗尽 / hard 档 / 无候选方向
        return self.show.memo_render(eng, self.difficulty.gradient)

    def _current_memo_location(self) -> str:
        """备忘录默认地点：优先最近一次未命中搜证地点，否则按 id 轮转。"""
        if self._last_miss_location:
            return self._last_miss_location
        locs = sorted({c.get("location") for c in self.evidence.pool.values()
                       if c.get("location") and not str(c["id"]).startswith("env_")})
        return locs[self.stage_machine.round_no() % max(1, len(locs))] if locs else ""

    # ================================================== 引擎白名单广播 / 收集品 / 头条竞标
    def broadcast_accident_flow(self, candidates: list[str] | None = None) -> str:
        """心声广播事故：白名单过滤权归引擎（已解锁+无案情词），演出包装。"""
        result = self.memory.broadcast_accident(candidates)
        return self.show.broadcast_accident(engine_result=result)

    def collect_flow(self, item_id: str, act_no: int | None = None,
                     actor: str | None = None) -> dict:
        """鱼干收集品拾取（CollectiblesBoard，0AP，彩蛋层不进证据链）；
        集齐 → unlock_payload → 看山Bot 隐藏语音演出。actor 缺省=真人（AI 席可传 ai:xx）。"""
        act_no = act_no or max(1, self.stage_machine._index + 1)
        result = self.cb.collect(actor or self.player_id, item_id, act_no=act_no)
        if result.get("all_collected") and result.get("unlock"):
            result["show"] = self.show.collectibles_show(result["unlock"])
        return result

    def headline_flow(self, actor: str, faction: str, amount: int,
                      topic: str | None = None,
                      post_id: str | None = None) -> dict:
        """头条竞标全链：开标主持词 → 引擎 bid/settle（明牌竞标，成交裁决归引擎）
        → 开标结果演出。faction 明牌仅在竞标内部使用，不透出前端（契约 §四.4）。"""
        open_ = self.opinion.open_headline_bidding(self.stage_machine.round_no())
        host = self.show.headline_auction(topic)
        bid = self.opinion.bid_headline(actor, faction, amount, post_id=post_id)
        settle = self.opinion.settle_headline()
        out = {"open": open_, "bid": bid, "settle": settle, "host_line": host}
        # 引擎 settle：winner=actor 字符串，faction 在顶层（明牌，仅内部使用）
        if settle.get("ok") and settle.get("winner"):
            winner_faction = str(settle.get("faction") or faction)
            out["result_line"] = self.show.headline_result(winner_faction)
        else:
            out["result_line"] = "叮——本轮头条流拍。热度小幅上扬：头条位空转的节目效果。"
        return out

    # ================================================== P2 暗拍 / 拼图 / 终局陈词（ae.record 接线）
    def stealth_photo_flow(self, location: str, keyword: str,
                           actor: str | None = None) -> dict:
        """暗拍链（2AP 由上层扣）：引擎 stealth_photo（线索留原地）→ ok 计数 +
        ae.record("photos_shared")（暗房大师素材，resolver 徽章消费）。
        actor 缺省=真人（AI 坐席传 ai:char_xx 即可由 AI 执行）。"""
        result = self.evidence.stealth_photo(location, keyword,
                                             actor or self.player_id,
                                             round_no=self.stage_machine.round_no())
        if result.get("ok"):
            self.counters["photos_shared"] += 1
            self.ae.record("photos_shared", value=1)
        return result

    def share_photo_flow(self, photo_id: str, claim: str | None = None,
                         actor: str | None = None) -> dict | None:
        """照片分享（可说谎：引擎登记原文+声称，真伪留圆桌对质）。actor 缺省=真人。"""
        return self.evidence.share_photo(actor or self.player_id, photo_id,
                                         claim=claim)

    def puzzle_flow(self, char_id: str, proposal: list[str]) -> dict:
        """记忆拼图对质链：发起成本 spend_tamper_points(2)（引擎校验）→
        puzzle_judge（引擎权威）→ 胜利 ae.record("memory_puzzle_win") + 演出。"""
        if not self.memory.spend_tamper_points(2):
            return {"ok": False, "reason": "not_enough_tamper_points"}
        result = self.memory.puzzle_judge(char_id, proposal)
        result["ok"] = True
        if result.get("correct"):
            self.ae.record("memory_puzzle_win", value=1)
        npc = self.npcs.get(char_id)
        result["show"] = self.show.puzzle_show(
            result, npc.character.get("name", char_id) if npc else char_id)
        return result

    def closing_statement(self, speaker: str, text: str) -> dict:
        """终局陈词登记（party 板，每人一条；不影响指认）。"""
        return self.party.final_statement(speaker, text)

    def hammer_vote_flow(self, voter: str, target: str, weight: int = 1) -> dict:
        """「最想锤的人」投票（分池）→ ae.record("hammered_votes", target)。
        ach_mianyipai（被锤 ≥3 仍存活）与 resolver 全场公敌素材。"""
        result = self.party.hammer_vote(voter, target, weight=weight)
        self.ae.record("hammered_votes", target=target, value=weight)
        return result

    def closing_settle(self) -> dict:
        """陈词结算：hammer_result → closing_survived（投票第一且自证清白，由
        上层确认存活后 record）→ 终局陈词锐评演出（faction 防御剥离）。"""
        result = self.party.hammer_result()
        most = result.get("most_hammered")
        speakers = sorted(({s.get("speaker", "") for s in result.get("statements", [])}
                           | ({most} if most else set())) - {""})
        rows = []
        for cid in speakers:
            npc = self.npcs.get(cid)
            rows.append({"name": npc.character.get("name", cid) if npc else cid})
        result["show"] = self.show.final_verdict(
            {"most_hammered": most, "statements": result.get("statements", [])}, rows)
        return result

    # ================================================== M2 心声窃听器（F memory-puzzle 数据源）
    def memory_puzzle_pool(self, tier: str = "open") -> list[dict]:
        """F 的 `GET /api/minis/memory-puzzle` 脱敏抽样数据源（segments_lib 供池）：
        tier=open 无案情词（免登录外链），tier=full 仅登录局内；full 永不进 open 池。"""
        return self.show.segments.heart_quiz_pool(tier)

    def heart_quiz_flow(self, item: dict, answer: str) -> dict:
        """M2 单题判定（答案位确定性比对）→ D 组结算句演出（答完揭教学点）。"""
        correct = str(answer).strip().upper()[-1:] == str(item.get("answer", "B")).upper()
        return {"correct": correct, "npc": item.get("npc", ""),
                "teaching": item.get("teaching", ""),
                "show": self.show.heart_quiz_show(correct, item.get("teaching", ""))}

    def stuck_level(self) -> int:
        """（诊断用，v3 起备忘录判定以 difficulty.py 为权威）距上次命中轮数差。"""
        idle = self.stage_machine.round_no() - self.last_hit_round
        return max(0, min(3, idle - 1))

    # ================================================== 辅助
    def _held_clues(self) -> list[dict]:
        return [self.evidence.pool[c] for c in self.evidence.get_player_clues(self.player_id)
                if c in self.evidence.pool]

    def enter_review(self, trigger: str = "credits") -> None:
        """进入复盘页触发点（F 组对接：review:credits 等条件线索解锁）。"""
        self.evidence.sync_context(review_flags=[trigger])

    def begin_round(self) -> dict:
        """开新一轮（引擎播报事件）+ DM 弹幕墙预热。"""
        return self.stage_machine.begin_round()

    def daily_flow(self, daily_topic: str = "#看山失踪#") -> str:
        return self.dm.daily_briefing({"daily_topic": daily_topic})


def bootstrap(game_root: Path | str = GAME_ROOT, **kwargs) -> AgentRuntime:
    """便捷入口：默认 kanshan 剧本组装。"""
    return AgentRuntime(Path(game_root) / "content" / "scenarios" / "kanshan", **kwargs)


__all__ = ["AgentRuntime", "bootstrap", "ENDINGS"]
