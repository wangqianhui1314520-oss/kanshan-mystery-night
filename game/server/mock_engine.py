"""可开关 mock 状态机：引擎（B 窗口）未接入期间的骨架替身。

开关（硬规则：引擎未就绪时用可开关 mock 状态机）：
  ZHIHU_GAME_USE_MOCK_ENGINE=1（默认）→ 全部动作由本状态机驱动；
  ZHIHU_GAME_USE_MOCK_ENGINE=0        → 动作返回 503，等待 engine/ 接入联调。

约定：
- 阶段序列与 engine/stage_machine.py 的 Stage 枚举一致：
  break_ice → investigate → round_table → accuse → review；
- 事件结构严格按契约 §3.6：{"type","session_id","round","actor","payload"}；
- client→server 类型仅限 search/chat/skill/counsel/vote/advance（§3.6）；
- mock 产出的 payload 一律带 "mock": true 与说明，不冒充引擎结论；
- 角色/线索优先读 content/scenarios/kanshan/（D 窗口产出），缺失时用内置 mock 池。
"""
import json
import os
import random
import time
from pathlib import Path

from .safety import sanitize_text

CLIENT_ACTIONS = ("search", "chat", "skill", "counsel", "vote", "advance")
MOCK_ENV = "ZHIHU_GAME_USE_MOCK_ENGINE"

STAGES = ("break_ice", "investigate", "round_table", "accuse", "review")
STAGE_NAMES = {
    "break_ice": "破冰·初到档案局",
    "investigate": "搜证·失踪之夜",
    "round_table": "圆桌·对质与投票",
    "accuse": "指认·终局投票",
    "review": "复盘·真相揭晓",
}
# 各阶段允许的动作——对齐 engine/stage_machine.py._STAGE_ACTIONS（契约动作集口径，
# 旧动作 introduce/private_chat/reveal_clue/accuse 由 B 引擎兼容，mock 不收录）
STAGE_ACTIONS = {
    "break_ice": {"chat"},
    "investigate": {"chat", "search", "skill", "counsel"},
    "round_table": {"chat", "skill", "counsel", "vote"},
    "accuse": {"vote"},
    "review": set(),
}
STAGE_AP = {"break_ice": 4, "investigate": 12, "round_table": 6,
            "accuse": 2, "review": 0}
ACTION_COST = {"search": 1, "chat": 0, "skill": 2, "counsel": 2, "vote": 1,
               "advance": 0}

# 内置 mock 角色（契约示例口径；D 窗口 scenario.json 就绪后自动替换）
MOCK_ROSTER = [
    {"id": "char_01", "name": "流量酱", "archetype": "百万粉大V", "faction": "pollution"},
    {"id": "char_02", "name": "键盘侠客", "archetype": "义愤填膺党", "faction": "pollution"},
    {"id": "char_03", "name": "求真姐", "archetype": "调查记者", "faction": "truth"},
    {"id": "char_04", "name": "路人甲", "archetype": "匿名吃瓜群众", "faction": "swayable"},
    {"id": "char_05", "name": "蹲蹲党", "archetype": "吃瓜蹲后续", "faction": "swayable"},
    {"id": "char_06", "name": "卷王本王", "archetype": "加班打工人", "faction": "swayable"},
    {"id": "char_07", "name": "谣研所", "archetype": "辟谣科普君", "faction": "truth"},
    {"id": "char_08", "name": "盐值君", "archetype": "社区管理员", "faction": "truth"},
]
MOCK_HEARTACHE = {f"char_{i:02d}": f"kc_{i:02d}" for i in range(1, 9)}

# 内置 mock 线索池（含 1 条 boss_flaw 演示破绽链；D 窗口 clues/ 就绪后替换）
MOCK_CLUES = [
    {"id": "clue_mock_001", "tier": "public", "location": "监控室",
     "name": "被擦掉的监控片段",
     "text": "监控终端的时间轴在 21:07-21:15 有一个刺眼空洞，擦除者技术很生疏。",
     "danmaku": ["好家伙，直接开审", "这线索我先截个图"]},
    {"id": "clue_mock_002", "tier": "limited", "location": "茶水间",
     "name": "补打卡的纸条",
     "text": "打卡机旁贴着一张手写纸条：「帮我把 21:30 那格划掉，谢了」。",
     "danmaku": ["信息量有点大", "蹲一个后续"]},
    {"id": "clue_mock_003", "tier": "hidden", "location": "走廊",
     "name": "没有烟味的烟头",
     "text": "走廊尽头有个掐灭的烟头，但档案局全员都不抽烟——那是谁留下的？",
     "danmaku": ["匿名了，怕被链到", "有一说一，确实是"]},
    {"id": "clue_mock_004", "tier": "fake", "location": "档案室",
     "name": "「知情者」的匿名信",
     "text": "一封指控性极强的匿名信，落款时间却写着一个不存在的日期——像是伪造的。",
     "danmaku": ["一眼假但好笑", "水军实锤了吧"]},
    {"id": "clue_mock_005", "tier": "boss_flaw", "flaw_id": "flavor_1",
     "location": "大厅", "name": "看山的口癖错位",
     "text": "「系统提示音」用了看山从不用过的语气词——DM 真的在幕后吗？",
     "danmaku": ["细思极恐", "IndexOf: 看山是山"]},
]

MOCK_REPLIES = [
    "谢邀。人在档案局，刚下工位。你问的这个，先问是不是，再问为什么。",
    "这个问题的水很深，我能说的都在明面上——更深的，等你想清楚再来问我。",
    "匿名了，怕被链到。我只能告诉你：那晚的走廊，不止我一个人走过。",
    "你猜的方向有一半对。另一半？说出来我这盐值就没了。",
]
MOCK_DANMAKU = [
    "谢邀，人在机房，刚下夜班", "这瓜保熟吗？", "先蹲一个后续",
    "匿名了，怕被链到", "有一说一，确实是", "热度快上热搜了兄弟们",
    "建议查查弹幕里有没有内鬼", "前排围观档案局名场面",
]


def mock_enabled() -> bool:
    """mock 开关：默认关闭（B 引擎已接线）；显式 ZHIHU_GAME_USE_MOCK_ENGINE=1 才启用。"""
    return os.environ.get(MOCK_ENV, "0").strip() == "1"


def make_event(etype: str, session_id: str, round_no: int, actor: str,
               payload: dict) -> dict:
    """契约 §3.6 事件信封（字段顺序冻结）。"""
    return {"type": etype, "session_id": session_id, "round": round_no,
            "actor": actor, "payload": payload}


class MockStateMachine:
    def __init__(self, scenario_dir: Path, store=None):
        self.scenario_dir = Path(scenario_dir)
        self.store = store
        self._clues = self._load_clues()
        self._roster = self._load_roster()

    # ------------------------------------------------------------- 数据装载
    def _load_roster(self) -> list[dict]:
        f = self.scenario_dir / "scenario.json"
        try:
            if f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                chars = data.get("characters") or []
                roster = [{"id": c.get("id"), "name": c.get("name"),
                           "archetype": c.get("archetype", ""),
                           "faction": c.get("faction", "swayable")}
                          for c in chars if c.get("id") and c.get("name")]
                if roster:
                    return roster
        except Exception:
            pass
        return [dict(m) for m in MOCK_ROSTER]

    def _load_clues(self) -> list[dict]:
        clues_dir = self.scenario_dir / "clues"
        try:
            if clues_dir.exists():
                pool = []
                for f in sorted(clues_dir.glob("*.json")):
                    c = json.loads(f.read_text(encoding="utf-8"))
                    if c.get("id") and c.get("name"):
                        pool.append(c)
                if pool:
                    return pool
        except Exception:
            pass
        return [dict(m) for m in MOCK_CLUES]

    def _next_seq(self) -> int:
        seq = 0
        if self.store is not None:
            today = time.strftime("%Y%m%d")
            prefix = f"s_{today}_"
            for sid in self.store.list_sessions():
                if sid.startswith(prefix):
                    try:
                        seq = max(seq, int(sid[len(prefix):]))
                    except ValueError:
                        continue
        return seq + 1

    # ------------------------------------------------------------- 建局
    def create_session(self, mode: str, host_player: str = "player:1") -> dict:
        sid = f"s_{time.strftime('%Y%m%d')}_{self._next_seq():04d}"
        now = time.time()
        return {
            "session_id": sid,
            "mode": mode,                      # main | daily | quick
            "engine": "mock",
            "created_at": now,
            "round": 1,
            "stage": "break_ice",
            "stage_name": STAGE_NAMES["break_ice"],
            "actions_left": STAGE_AP["break_ice"],
            "players": [{"player_id": host_player, "faction": "truth",
                         "joined_at": now}],
            "npcs": [dict(n) for n in self._roster],
            "clue_pool_size": len(self._clues),
            "clues_gained": [],
            "votes": {},
            "heat": 30,
            "flaw_count": 0,
            "status": "playing",
            "events": [],
            "booklet_roles": {host_player: "investigator"},
        }

    # ------------------------------------------------------------- 动作分发
    def apply_action(self, session: dict, action_type: str, actor: str,
                     payload: dict, *, allow_ai: bool = False
                     ) -> tuple[list[dict], str | None]:
        """返回 (§3.6 事件列表, 错误提示)。错误非 None 时事件为空。"""
        if action_type not in CLIENT_ACTIONS:
            return [], (f"未支持的客户端动作类型：{action_type}"
                        f"（契约 §3.6 仅限 {'/'.join(CLIENT_ACTIONS)}）")
        if session.get("status") != "playing":
            return [], f"对局已结束（status={session.get('status')}），无法继续动作"
        stage = session.get("stage", "break_ice")
        allowed = STAGE_ACTIONS.get(stage, set())
        # advance 是跨阶段元动作（状态机唯一合法的阶段推进），全阶段可用
        if action_type != "advance" and action_type not in allowed:
            return [], (f"当前阶段「{STAGE_NAMES.get(stage, stage)}」不允许动作 "
                        f"{action_type}（允许：{'/'.join(sorted(allowed)) or '无'}）；"
                        f"可 advance 进入下一阶段")
        cost = ACTION_COST[action_type]
        if cost > 0 and session.get("actions_left", 0) < cost:
            return [], (f"行动力不足（剩 {session.get('actions_left', 0)}，"
                        f"需 {cost}）；可 advance 进入下一阶段")

        actor = (actor or "player:1").strip()
        if actor.startswith("ai:"):
            if not allow_ai:
                return [], "actor 必须为 player:{id}（npc/dm 事件由服务端发出）"
        elif not actor.startswith("player:"):
            return [], "actor 必须为 player:{id}（npc/dm 事件由服务端发出）"
        if actor.startswith("player:") and all(
                p["player_id"] != actor for p in session["players"]):
            session["players"].append({"player_id": actor, "faction": "truth",
                                       "joined_at": time.time()})

        events = getattr(self, f"_do_{action_type}")(session, actor,
                                                     payload or {})
        session["actions_left"] = max(0, session.get("actions_left", 0) - cost)
        session["updated_at"] = time.time()
        return events, None

    # ------------------------------------------------------------- 各动作
    def _do_search(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        clue = next((c for c in self._clues
                     if c["id"] not in session["clues_gained"]), None)
        if clue is None:
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "search_empty",
                "notice": f"线索池已抽干（共 {len(self._clues)} 条）——"
                          f"等待 D 窗口内容接入，不伪造新线索",
                "mock": True})]
        session["clues_gained"].append(clue["id"])
        if clue.get("tier") == "boss_flaw":
            session["flaw_count"] = session.get("flaw_count", 0) + 1
        session["heat"] = min(100, session.get("heat", 30) + 3)
        danmaku = [sanitize_text(d)[0] for d in
                   clue.get("danmaku", random.sample(MOCK_DANMAKU, 2))]
        clue_evt = make_event("clue_gained", sid, rnd, actor, {
            "clue_id": clue["id"], "tier": clue.get("tier", "public"),
            "name": clue["name"], "text": clue.get("text", ""),
            "danmaku": danmaku, "flaw_id": clue.get("flaw_id"),
            "mock": True,
            "notice": "mock 状态机产出占位线索；引擎接入后由 evidence_chain 结算",
        })
        dan_evt = make_event("danmaku", sid, rnd, "kanshan", {
            "items": random.sample(MOCK_DANMAKU, 2), "mock": True})
        return [clue_evt, dan_evt]

    def _do_chat(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        target = str(payload.get("target", "")).replace("npc:", "").strip()
        npc = next((n for n in session["npcs"] if n["id"] == target), None)
        if npc is None:
            ids = "/".join(n["id"] for n in session["npcs"][:4])
            known = "…"
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "target_not_found", "target": target,
                "notice": f"目标 NPC 不存在（可用示例：{ids}{known}）",
                "mock": True})]
        text = str(payload.get("text", ""))[:500]
        reply, _hits = sanitize_text(
            f"（mock 台词）{npc['name']}：「{random.choice(MOCK_REPLIES)}」")
        chat_evt = make_event("chat", sid, rnd, f"npc:{npc['id']}", {
            "reply_to": actor, "player_text": text, "text": reply,
            "mock": True,
            "notice": "mock 模板台词，非真实 AI 生成；C 窗口 Agent 接入后替换",
        })
        dan_evt = make_event("danmaku", sid, rnd, "kanshan", {
            "items": random.sample(MOCK_DANMAKU, 2), "mock": True})
        return [chat_evt, dan_evt]

    def _do_skill(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        skill = str(payload.get("skill", "truth_check"))
        if skill == "truth_check":       # 求真：辟谣降热
            delta = -6
        elif skill == "pollution_stir":  # 污染：带节奏升热
            delta = +6
        else:
            delta = 0
        session["heat"] = max(0, min(100, session.get("heat", 30) + delta))
        return [make_event("faction_skill", sid, rnd, actor, {
            "skill": skill, "heat_delta": delta,
            "heat_after": session["heat"],
            "effect": "mock 占位结算；引擎接入后由 resolver/opinion_feed 结算",
            "mock": True})]

    def _do_counsel(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        card = str(payload.get("card", "")).strip()
        target = str(payload.get("target", "")).replace("npc:", "").strip()
        npc = next((n for n in session["npcs"] if n["id"] == target), None)
        if npc is None:
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "target_not_found", "target": target,
                "notice": "开导目标 NPC 不存在", "mock": True})]
        heartache = MOCK_HEARTACHE.get(npc["id"], "")
        success = bool(card) and card == heartache   # 心病匹配表（mock 口径）
        if success:
            session["heat"] = max(0, session.get("heat", 30) - 4)
        else:
            session["heat"] = min(100, session.get("heat", 30) + 4)
        result_evt = make_event("counsel_result", sid, rnd, actor, {
            "card": card, "target": f"npc:{npc['id']}", "success": success,
            "effect": ("memory_unlock + buff_ap（mock）" if success
                       else "卡与心病不匹配 → 群嘲演出（mock），热度 +4"),
            "heat_after": session["heat"], "mock": True,
            "notice": "mock 结算；引擎接入后由 knowledge_cards 按心病匹配表结算",
        })
        events = [result_evt]
        if success:
            events.append(make_event("memory_unlock", sid, rnd, actor, {
                "owner": f"npc:{npc['id']}", "unlocked_layers": ["heart"],
                "mock": True}))
        return events

    def _do_vote(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        target = str(payload.get("target", "")).replace("npc:", "").strip()
        if not any(n["id"] == target for n in session["npcs"]):
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "target_not_found", "target": target,
                "notice": "投票目标 NPC 不存在", "mock": True})]
        session["votes"][actor] = f"npc:{target}"
        players_n = max(1, len(session["players"]))
        vote_evt = make_event("vote", sid, rnd, actor, {
            "target": f"npc:{target}", "voters": len(session["votes"]),
            "needed": players_n, "mock": True})
        if len(session["votes"]) < players_n:
            return [vote_evt]
        # 全员投完 → mock 结算
        tally: dict[str, int] = {}
        for t in session["votes"].values():
            tally[t] = tally.get(t, 0) + 1
        top = max(tally.items(), key=lambda kv: kv[1])
        winners = [t for t, c in tally.items() if c == top[1]]
        accused = winners[0] if len(winners) == 1 else "hung"
        session["status"] = "ended"
        ending_evt = make_event("ending", sid, rnd, "kanshan", {
            "accused": accused, "tally": tally,
            "flaw_count": session.get("flaw_count", 0),
            "outcome": ("hung" if accused == "hung"
                        else ("truth_win" if any(n["id"] == accused.split(":")[-1]
                                and n["faction"] == "pollution"
                                for n in session["npcs"])
                              else "pollution_win")),
            "mock": True,
            "notice": "mock 结局结算；引擎接入后由 resolver 结局矩阵（含 boss_layer）结算",
        })
        return [vote_evt, ending_evt]

    def _do_advance(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid = session["session_id"]
        stage = session.get("stage", "break_ice")
        idx = STAGES.index(stage) if stage in STAGES else 0  # 非法 stage 防御
        if idx >= len(STAGES) - 1:
            session["status"] = "ended"
            return [make_event("ending", sid, session["round"], "kanshan", {
                "accused": None, "tally": session.get("votes", {}),
                "outcome": "time_out", "mock": True,
                "notice": "复盘阶段已尽，对局结束（mock）"})]
        new_stage = STAGES[idx + 1]
        session["stage"] = new_stage
        session["stage_name"] = STAGE_NAMES[new_stage]
        session["round"] = idx + 2
        session["actions_left"] = STAGE_AP[new_stage]
        sys_evt = make_event("system", sid, session["round"], "kanshan", {
            "event": "stage_changed", "stage": new_stage,
            "stage_name": STAGE_NAMES[new_stage],
            "actions_left": session["actions_left"],
            "notice": f"进入「{STAGE_NAMES[new_stage]}」"
                      f"（允许：{'/'.join(sorted(STAGE_ACTIONS[new_stage])) or '无'}）",
            "mock": True})
        if new_stage == "review":
            session["status"] = "ended"
            sys_evt["payload"]["notice"] += "；进入复盘即视为对局结束（mock 简化）"
        return [sys_evt]
