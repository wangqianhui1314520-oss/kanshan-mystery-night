"""engine_driver — B 引擎（engine/ 七模块）接线适配层。

与 MockStateMachine 同签名（create_session / apply_action），由 main.py 按开关
ZHIHU_GAME_USE_MOCK_ENGINE 选择（默认 0 = 真实引擎；=1 回退 mock）。

接线原则（零越界：engine/ 只读导入，不改其任何文件）：
- StageMachine：阶段/轮/AP 单一事实源（sm.can() 决定动作合法性，避免双份白名单）；
- EvidenceChain：搜证主循环 ec.search / 条件线索 release / 证据合成 try_compose /
  破绽 flaw_count·boss_ready / 篡改点 ingest_clue；
- MemorySystem：双层记忆 unlock_next（counsel/memory_fix）→ 篡改点转线索卡；
- KnowledgeSystem：抽卡 draw / 心病匹配 counsel / 心晴诊室 clinic_settlement；
- OpinionFeed：热搜面板 refresh / 买热搜 buy_heat / 辟谣 refute（attach_knowledge 注入）；
- Timeline：容错加载（缺失置 None，搜证链不依赖）；
- Resolver：AP 细则（search=1 / counsel=2 / skill=1、refute/buy_heat/memory_fix=2）
  与 8+2 结局矩阵 matrix_ending / 指认裁决 resolve_accusation·resolve_boss_accusation。

B 组要求的 F 侧联动（engine/STATUS.md §五-遗留 1）全部落地：
- EvidenceChain.sync_context(memory_versions/counsel_cards/chat_keywords/review_flags)
- OpinionFeed.attach_knowledge(...)
- StageMachine.session_id 回填
- chat:keyword_* 对话框触发线索（clue_031）、review:credits 复盘页线索（clue_032）

会话恢复：session["actions"] 记录成功动作序列（type/actor/payload），
服务重启后按固定 seed 重建引擎实例并确定性回放（引擎全部裁决为确定性，无 AI 参与）。
"""
import json
import time
from pathlib import Path

from engine import difficulty, echo_log, evidence_chain, judge_debate, knowledge_cards, memory_system, opinion_feed, party, pollution_check, resolver, stage_machine, timeline, truth_profile

from .mock_engine import MOCK_DANMAKU, STAGE_NAMES, make_event
from .safety import sanitize_text

ACTION_COST = {"search": 1, "chat": 0, "counsel": 2, "vote": 0, "advance": 0}
SKILL_COST = {"refute": 2, "buy_heat": 2, "memory_fix": 2,
              "puzzle": 0, "bid_headline": 0,
              "pollution_open": 0, "pollution_mark": 1,
              "stealth_photo": 2, "draw_card": 1,
              "closing_speech": 0, "hammer_vote": 0,
              "cocoon_break": 0, "evidence_pin": 0, "defect": 0,
              "judge_line": 0,
              "flood_comments": 2, "report_spam": 2, "plant_fake": 1,
              "flip_side": 0, "quiz_draw": 0, "quiz_answer": 0,
              "radio_tune": 0, "radio_request": 1, "first_vote_cast": 0,
              "unlock_office": 0, "expose_v587": 0}  # 其余 skill=1
# 已注册技能白名单（P1：未知技能必须零扣费）。= SKILL_COST 全集 + 引擎
# _do_skill 有分支但成本走默认 1 的心声/辩论/侦察系；collect / share_photo /
# cross_check / stealth_photo 由 main.py RT_SKILL_FLOWS 分流，不经此处扣费。
REGISTERED_SKILLS = frozenset(SKILL_COST) | {
    "echo_open", "echo_defend", "debate_open", "debate_submit", "truth_check"}
SALT_EGG_IDS = frozenset({"clue_017", "clue_018", "clue_019", "clue_020", "clue_021"})
QUIZ_BANK = [
    {"q": "横幅上写的八个字是？", "options": ["不出真相不出此门", "不开门不出门", "真不出门了"]},
    {"q": "案发夜 DM 的口头禅是？", "options": ["叮——", "汪——", "喵——"]},
    {"q": "监控被删除的时段是？", "options": ["21:07-21:15", "22:30-22:40", "全删了"]},
    {"q": "删除监控用的账号权限是？", "options": ["局长级 KS-000", "实习生号", "访客号"]},
    {"q": "看山的鱼干口味是？", "options": ["彩虹鳟鱼味", "金枪鱼味", "香辣味"]},
    {"q": "热搜热度曲线从几点开始\"纪律严明\"？", "options": ["21:10", "22:00", "23:00"]},
    {"q": "路人甲的口供把什么说成了什么？", "options": ["代班→值班", "值班→代班", "上班→下班"]},
    {"q": "水军矩阵有多少个设备指纹同源的号？", "options": ["47", "14", "404"]},
    {"q": "看山Bot 删日志后留下了什么？", "options": ["哈希值 A3F9-77C2", "道歉信", "什么都没留"]},
    {"q": "盐值君在门禁系统留言板上写了？", "options": ["建议关注", "强烈谴责", "我不管了"]},
    {"q": "流量酱真正在后台待了多久？", "options": ["15 分钟", "0 分钟", "3 小时"]},
    {"q": "笔上仙的剧中剧叫？", "options": ["学科修仙", "修仙学科", "学科修罗场"]},
    {"q": "沉底君被折叠的答案序号是？", "options": ["第 7 章/第 7 篇", "第 1 章", "第 100 章"]},
    {"q": "V587 的老号曾用什么身份活跃？", "options": ["侦探爱好者联盟", "钓鱼佬联盟", "吃瓜联盟"]},
    {"q": "集齐几个破绽可以指认 DM？", "options": ["5", "3", "2"]},
    {"q": "系统唤醒词是？", "options": ["看山，关门", "看山，开门", "芝麻关门"]},
    {"q": "心晴自习室的正确用法是？", "options": ["抽知识卡开导心病", "睡午觉", "避难"]},
    {"q": "辟谣需要消耗？", "options": ["2AP+对应知识卡", "0AP", "喊得够大声"]},
    {"q": "二十年前的大力丸在哪里被搜出？", "options": ["空调机房", "茶水间", "天台"]},
    {"q": "终极结局的名字是？", "options": ["看山还是山", "看山不是山", "看山去哪了"]},
]
RADIO_LINES = [
    "【广播台】现在是档案局时间。封控第 {n} 小时，泡面消耗 4 桶，线索 {c} 条，真相进度：本台不便透露。",
    "【广播台】天气预报：档案局今夜有雾，能见度不足一条热搜。请各位不要出门——反正门也锁着。",
    "【广播台】本台提醒：折叠区怨灵沉底君的发言没有被折叠，请大家正常倾听，不要围观。",
    "【广播台】寻物启事：一袋彩虹鳟鱼味鱼干，最后出现于 21:00 前的档案室。知情者请勿私聊，直接喊出来。",
    "【广播台】寻人启事：首席侦探刘看山，男，北极狐，最后出现时说「谁都不许跟来」。",
    "【广播台】点播台规则：1 行动点 = 30 秒广播时间。本台保留因内容太尬而提前掐断的权利。",
]
PIN_CORE_NODES = ("tn_01", "tn_02", "tn_03", "tn_04", "tn_05", "tn_06")
# 评委线起步包：横幅 tn_02 + 请假条 tn_01 + 热搜曲线 tn_05/tn_06 → 核心 4/6
JUDGE_LINE_CLUES = ("clue_001", "clue_002", "clue_005")
# 房间模式搜证章出门条件：前端 mock 认 clue_021（芯片空盒）；
# 真引擎 clue_021 是天台彩蛋、clue_032 是终局复盘破绽，不能当出门钥匙。
# 用第一章就能搜到的公开线索（工位/档案室/前台/茶水间）对齐「先搜再进下一幕」。
PARTY_CH1_KEYS = frozenset({
    # canonical clue_028 is the first-act boss flaw found at 看山工位/鱼干.
    "clue_021", "clue_028", "clue_001", "clue_002", "clue_004", "clue_006", "clue_007",
})
DEFECT_CHARS = ("char_03", "char_04")
ICEBREAKER_SKILLS = frozenset({
    "cocoon_break", "evidence_pin", "defect", "judge_line",
    "pollution_open", "pollution_mark",
    "echo_open", "echo_defend",
    "debate_open", "debate_submit",
    "quiz_draw", "quiz_answer", "radio_tune", "radio_request",
    "first_vote_cast",
})
SEED = 20260912  # 固定种子：抽卡/回放确定性
# 前端 loc_* → scene_map key（引擎只认 key 或中文名）
LOC_ALIASES = {
    "loc_reception": "reception",
    "loc_desk": "desk_kanshan",
    "loc_teahouse": "teahouse",
    "loc_locker": "parcel_locker",
    "loc_monitor": "monitor_room",
    "loc_server": "server_room",
    "loc_archive": "archive_room",
    "loc_hotfeed": "hotfeed_backstage",
    "loc_ac": "hvac_room",
    "loc_roof": "roof",
    "loc_clinic": "study_room",
    "loc_office": "director_office",
}


def _norm_npc(target: str) -> str:
    return str(target or "").replace("npc:", "").strip()


def _ai_speaker_char(actor: str) -> str | None:
    """ai:char_03 / player:ai:char_03 → char_03；非空席 AI 返回 None。"""
    a = str(actor or "")
    if a.startswith("player:ai:"):
        return a[len("player:ai:"):] or None
    if a.startswith("ai:"):
        return a[3:] or None
    return None


def _skill_name(payload: dict | None) -> str:
    p = payload or {}
    return str(p.get("skill") or p.get("kind") or "truth_check")


def _ambient_danmaku(n: int = 2) -> list[str]:
    return [sanitize_text(d)[0] for d in MOCK_DANMAKU[:n]]


class EngineDriver:
    def __init__(self, scenario_dir: Path):
        self.scenario_dir = Path(scenario_dir)
        scenario_path = self.scenario_dir / "scenario.json"
        self.scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        # 引擎七模块组装（每次 create/replay 各建一套实例）
        self.sm = stage_machine.StageMachine(self.scenario)
        self.ec = evidence_chain.EvidenceChain(self.scenario_dir)
        self.ms = memory_system.MemorySystem()
        self.ms.load(str(self.scenario_dir))
        self.ks = knowledge_cards.KnowledgeSystem(seed=SEED)
        self.ks.load(str(self.scenario_dir))
        self.of = opinion_feed.OpinionFeed()
        self.of.load(str(self.scenario_dir))
        self.of.attach_knowledge(self._card_topic)
        self.pc = pollution_check.PollutionCheck(seed=SEED)
        self.pc.load(str(self.scenario_dir))
        self.el = echo_log.EchoLog()
        self.jd = judge_debate.JudgeDebate()
        # S3/S4 行为计数（结算画像用，零 AI 参与）
        self.echo_defended = False
        self.buy_heat_count = 0
        self.refute_count = 0
        try:
            self.tl = timeline.Timeline(self.scenario_dir)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self.tl = None  # timeline 缺失容错（引擎偏离 #7：其为必交付件，但搜证链不依赖）
        self.rv = resolver.Resolver()
        self.truth = self._load_truth()
        self._roster = self._load_roster()
        # V31：房间级多人同场（PartyBoard 阵营暗置发牌——faction_of() 结果绝不透出前端）
        self.pb = party.PartyBoard.from_roster(self._roster, seed=SEED)
        self.dd = difficulty.DifficultyDirector()
        self._locations = set(self.scenario.get("scene_map", {}).keys())
        self._loc_names = {  # scene_map key(英文 id) → 线索 location 字段（中文名）
            k: str(v.get("name", k)) if isinstance(v, dict) else str(v)
            for k, v in self.scenario.get("scene_map", {}).items()}
        self._linear_acts = any(  # D 内容结构判定：round_table 为独立幕 → 幕线性推进
            a.get("stage") == "round_table" for a in self.scenario.get("acts", []))
        # 会话级标志（结局矩阵输入）
        self.plot_fragments = 0
        self.boss_key = False
        self.votes: dict[str, str] = {}
        self.players: list[str] = []
        self._first_vote_sent = False  # V4 综艺：first_vote 只发一次（圆桌幕结束）
        self._radio_sent_rounds: set[int] = set()
        self.v587_exposed = False
        self.search_bias: dict[str, int] = {}
        self.cocoon_active = False
        self.cocoon_broken = 0
        self.evidence_links: list[dict] = []
        self.defection: dict[str, dict] = {}
        # 热搜竞价轮次（契约 §3.6 增补：headline_open/bid/outbid/settle + bid_pass）。
        # 窗口懒结算：deadline 到点后由下一动作/advance 结算；幕结束强制结算。
        self._headline_window: dict | None = None
        self._headline_seq = 0

    # ------------------------------------------------------- 热搜竞价窗口
    HEADLINE_WINDOW_SECONDS = 90  # 竞价窗口时长（懒结算，无真定时器）
    HEADLINE_MIN_BID = 1

    def _open_headline_window(self, session: dict, reason: str) -> dict | None:
        """开启竞价窗口并广播 headline_open（同 round 幂等，不重开）。"""
        rnd = int(session.get("round") or 1)
        if self._headline_window is not None:
            if self._headline_window["round"] == rnd:
                return None  # 幂等：同 round 已有窗口
            return None  # 异常态：旧窗口未结算则不重开（等懒结算/幕结束清算）
        self.of.open_headline_bidding(rnd)
        self._headline_seq += 1
        window = {
            "window_id": f"headline_w{self._headline_seq}_r{rnd}",
            "round": rnd,
            "deadline_ts": time.time() + self.HEADLINE_WINDOW_SECONDS,
            "min_bid": self.HEADLINE_MIN_BID,
            "frozen": {},   # actor -> 已冻结 AP（反超退还，胜者结算扣除）
            "passed": [],   # bid_pass 放弃名单
        }
        self._headline_window = window
        topics = [{"id": p["id"], "title": p.get("title", p["id"]),
                   "is_fake": bool(p.get("is_fake"))}
                  for p in self.of.refresh(rnd)]
        return make_event("headline_open", session["session_id"], rnd, "kanshan", {
            "window_id": window["window_id"], "round": rnd,
            "deadline_ts": window["deadline_ts"],
            "deadline_in": self.HEADLINE_WINDOW_SECONDS,
            "topics": topics, "min_bid": window["min_bid"],
            "reason": reason, "source": "engine"})

    def _headline_freeze_ap(self, session: dict, actor: str, amount: int,
                            prev_frozen: int) -> str | None:
        """出价冻结 AP：先退旧冻结再冻新额。返回错误文案或 None（成功）。"""
        if actor.startswith("ai:") or actor.startswith("player:ai:"):
            return None  # 空席/AI 席不占共享池（与旧 vacant_ai 语义一致）
        if prev_frozen:
            self._headline_refund_ap(session, actor, prev_frozen)
        if session.get("mode") == "party":
            if actor not in self.pb.ap_state():
                return "party 模式需先入座（POST /api/session/{id}/join）再出价"
            if not self.pb.spend(actor, amount):
                return (f"行动力不足（你剩 {self.pb.ap_state().get(actor, 0)}，"
                        f"需 {amount}）；party 模式每人每轮 3 点")
            return None
        if self.sm.actions_left < amount:
            return (f"行动力不足（剩 {self.sm.actions_left}，需 {amount}）；"
                    f"可 advance 结束本轮")
        self.sm.actions_left -= amount
        return None

    def _headline_refund_ap(self, session: dict, actor: str, amount: int) -> None:
        """退还冻结 AP（被反超/流拍/改价）。"""
        if amount <= 0 or actor.startswith("ai:") or actor.startswith("player:ai:"):
            return
        if session.get("mode") == "party" and actor in self.pb.ap_state():
            self.pb.refund(actor, amount)
        elif session.get("mode") != "party":
            self.sm.actions_left += amount

    def _settle_headline_window(self, session: dict, reason: str = "deadline") -> list[dict]:
        """结算未决窗口并广播 headline_settle（最高价胜出/流拍），退未胜者冻结。"""
        window = self._headline_window
        if window is None:
            return []
        sid, rnd = session["session_id"], int(session.get("round") or 1)
        result = self.of.settle_headline()
        winner = result.get("winner")
        for a, amt in list(window["frozen"].items()):
            if winner is None or a != winner:
                self._headline_refund_ap(session, a, int(amt))
        self._headline_window = None
        post_id = result.get("post_id")
        title = (self.of._posts.get(post_id) or {}).get("title") if post_id else None
        if winner is None:
            effect = (result.get("note") or "流拍：头条位空转")
            effect += f"（当前热度 {self.of.heat}）"
        else:
            effect = (f"《{title or post_id}》登上头条并置顶，热度涨至 {self.of.heat}；"
                      f"头条话题可信度权重上升")
        return [make_event("headline_settle", sid, rnd, "kanshan", {
            "window_id": window["window_id"], "winner": winner,
            "amount": int(result.get("amount") or 0),
            "topic_id": post_id, "topic_title": title,
            "effect": effect, "reason": reason, "heat": self.of.heat,
            "source": "engine"}),
            self._hotfeed_event(sid, rnd)]

    def _maybe_settle_headline(self, session: dict) -> list[dict]:
        """懒结算：窗口 deadline 已过则立即结算（下一动作/advance 时检查）。"""
        w = self._headline_window
        if w is not None and time.time() >= w["deadline_ts"]:
            return self._settle_headline_window(session, reason="deadline")
        return []

    def _do_bid_pass(self, session: dict, actor: str, payload: dict) -> list[dict]:
        """bid_pass：本竞价窗口放弃出价（零 AP，不影响已冻结额）。"""
        sid, rnd = session["session_id"], int(session.get("round") or 1)
        events = self._maybe_settle_headline(session)
        window = self._headline_window
        if window is None:
            return events + [make_event("system", sid, rnd, actor, {
                "event": "bid_pass_ignored",
                "notice": "当前没有开启的竞价窗口", "source": "engine"})]
        if actor not in window["passed"]:
            window["passed"].append(actor)
        events.append(make_event("system", sid, rnd, actor, {
            "event": "bid_pass_ack", "window_id": window["window_id"],
            "text": "本轮头条竞标放弃出价", "source": "engine"}))
        return events

    def _note_search_tags(self, tags) -> bool:
        """累加搜证 tag 画像；刚入茧时返回 True。"""
        for t in tags or []:
            t = str(t).strip()
            if not t:
                continue
            self.search_bias[t] = int(self.search_bias.get(t, 0)) + 1
        if not self.cocoon_active and self.search_bias:
            if max(self.search_bias.values()) >= 2:
                self.cocoon_active = True
                return True
        return False

    def _pin_coverage(self) -> dict:
        nodes: set[str] = set()
        for link in self.evidence_links:
            for n in link.get("nodes") or []:
                nodes.add(str(n))
        hit = [n for n in PIN_CORE_NODES if n in nodes]
        return {"hit": hit, "pct": round(len(hit) / len(PIN_CORE_NODES) * 100),
                "total": len(nodes)}

    def _owned_clue(self, session: dict, actor: str, clue_id: str) -> bool:
        if clue_id in self.ec.get_player_clues(actor):
            return True
        return clue_id in (session.get("clues_gained") or [])

    # ---------------------------------------------- V31：party 席位（faction 零透出）
    def join_seat(self, player_id: str, char_id: str | None = None) -> dict:
        """真人入座 PartyBoard（自动分配空位或认领空席/AI 席）。

        首个真人入座时触发阵营暗置发牌；faction_of()/result() 结果只进引擎内部
        （成就/结局裁决），任何事件与 API 响应零透出。
        """
        res = self.pb.join(player_id, char_id)
        if res.get("ok"):
            self.pb.assign_factions()  # 幂等：已发牌则原样返回
            if not res.get("rejoin"):
                self.pb.reset_round_ap()
        return res

    def leave_seat(self, player_id: str) -> dict:
        """掉线：席位保留 + AI 接管标记（对外只说「该角色已由 AI 接管」，不透阵营）。"""
        return self.pb.leave(player_id)

    def seats_public(self) -> list[dict]:
        """公开席位视图：char_id/player_id/connected/ai_takeover/is_ai——无 faction。"""
        return self.pb.seats()

    def restore_party(self, snap: dict):
        """回放重建时恢复 PartyBoard（seed 重放 + snapshot 双保险）。"""
        self.pb.restore(snap)

    def party_snapshot(self) -> dict:
        return self.pb.snapshot()

    # ------------------------------------------------------------- 装载辅助
    def _load_truth(self) -> dict:
        try:
            return json.loads((self.scenario_dir / "truth.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _load_roster(self) -> list[dict]:
        roster = []
        cdir = self.scenario_dir / "characters"
        if cdir.is_dir():
            for f in sorted(cdir.glob("char_*.json")):
                try:
                    c = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                roster.append({"id": c.get("id", f.stem),
                               "name": c.get("name", f.stem),
                               "archetype": c.get("archetype", ""),
                               "faction": c.get("faction", "swayable")})
        return roster or [{"id": f"char_{i:02d}", "name": f"NPC_{i:02d}",
                           "archetype": "", "faction": "swayable"} for i in range(1, 9)]

    def _card_topic(self, card_id: str):
        card = self.ks.card(card_id)
        return card.get("topic_tag") if card else None

    # --------------------------------------------------- V4 综艺阶段事件（G3）
    def _case_intro_event(self, sid: str) -> dict:
        """V4 §一②案件介绍：建局后由 DM（看山系统音）播报案件卷宗数据。

        标题/简介读 scenario.json；证物清单只收 public 层线索（name/location，
        不带 fact/linked_truth_nodes——零剧透确定性截取）；署名读 truth.json。
        """
        evidence = []
        for cid in sorted(self.ec.pool.keys()):
            clue = self.ec.pool[cid]
            if clue.get("tier") == "public":
                evidence.append({"id": clue.get("id", cid),
                                 "name": clue.get("name", ""),
                                 "location": clue.get("location", "")})
        return make_event("system", sid, 1, "dm", {
            "event": "case_intro",
            "title": self.scenario.get("title", ""),
            "genre": self.scenario.get("genre", ""),
            "summary": self.scenario.get("summary", ""),
            "evidence": evidence,
            "attribution": self.truth.get("attribution", ""),
            "source": "engine"})

    # ------------------------------------------------------------- 建局
    def create_session(self, mode: str, host_player: str = "player:1",
                       session_id: str | None = None) -> dict:
        self.sm.session_id = session_id or ""
        self.ks.set_round(1)  # 急诊红灯轮次注入（V31：set_round 由 F 每轮调用）
        now = time.time()
        # Count only roles with runtime-readable booklets. Generated packs are
        # audited before HTTP creation; the same calculation keeps direct driver
        # callers and restored sessions consistent.
        ai_seat_count = 0
        if mode != "party" and self.scenario_dir.name.startswith("gen_"):
            try:
                from engine.booklet import load_library
                ai_seat_count = len([
                    rid for rid in load_library(self.scenario_dir).role_ids()
                    if rid != "investigator"
                ])
            except Exception:
                ai_seat_count = 0
        session = {
            "session_id": session_id or f"s_{time.strftime('%Y%m%d')}_{int(now * 1000) % 100000000:08d}",
            "mode": mode,
            "engine": "engine_v3",
            "created_at": now,
            "round": 1,
            "stage": self.sm.stage.value,
            "stage_name": STAGE_NAMES.get(self.sm.stage.value, self.sm.stage.value),
            "actions_left": self.sm.actions_left,
            "players": [{"player_id": host_player, "faction": "truth",
                         "joined_at": now}],
            "npcs": [dict(n) for n in self._roster],
            "clue_pool_size": len(self.ec.pool),
            "clues_gained": [],
            "votes": {},
            "heat": self.of.heat,
            "flaw_count": 0,
            "counsel_count": 0,
            "held_cards": [],
            "evidence_cards": [],
            "plot_fragments": 0,
            "boss_key": False,
            "quiz_score": 0,
            "zans": 0,
            "office_open": False,
            "v587_exposed": False,
            "pollution": self.pc.summary(),
            "echo": self.el.summary(),
            "debate": self.jd.summary(),
            "profile": None,
            "boss_ready": self.ec.boss_ready(),
            # Only an explicit judge-line handshake can enable the demo gate.
            "demo_bypass": False,
            "status": "playing",
            "actions": [],
            "events": [],
            "booklet_roles": {host_player: "investigator"},
            "ai_seat_count": ai_seat_count,
        }
        # V4 综艺：建局即产出案件介绍（案件卷宗页数据源，REST/WS 回放均可见）
        session["events"].append(self._case_intro_event(session["session_id"]))
        if mode in ("quick", "daily"):
            self.sm.advance()
            session["stage"] = self.sm.stage.value
            session["stage_name"] = STAGE_NAMES.get(self.sm.stage.value, self.sm.stage.value)
            session["actions_left"] = self.sm.actions_left
            if mode == "quick":
                session["events"].append(make_event("system", session["session_id"], 1, "dm", {
                    "event": "mode_setup", "mode": "quick",
                    "text": "快速局：已跳过破冰，直接搜证/对质",
                    "source": "engine"}))
            else:
                session["events"].append(make_event("system", session["session_id"], 1, "dm", {
                    "event": "daily_topic", "topic": "#档案局夜班纪律#",
                    "text": "每日挑战已开：今日词条挂钩一则衍生谣言",
                    "source": "engine"}))
        return session

    # ------------------------------------------------------------- 动作分发
    def memory_view(self, char_id: str) -> dict:
        from dataclasses import asdict
        unlocked = char_id in self.ms._heart_unlocked
        blocks = self.ms.visible_blocks(char_id, include_heart=unlocked)
        return {"char_id": char_id, "version": self.ms.current_version(char_id),
                "blocks": [asdict(b) for b in blocks],
                "heart_unlocked": any(b.layer == "heart" for b in blocks),
                "can_repair": self.ms._next_version(char_id) is not None,
                "tamper_available": self.ms.tamper_available()}

    def apply_action(self, session: dict, action_type: str, actor: str,
                     payload: dict, *, allow_ai: bool = False
                     ) -> tuple[list[dict], str | None]:
        if action_type not in ("search", "chat", "skill", "counsel", "vote",
                               "advance", "bid_pass"):
            return [], (f"未支持的客户端动作类型：{action_type}"
                        f"（契约 §3.6 仅限 search/chat/skill/counsel/vote/advance"
                        f"+增补 bid_pass）")
        if session.get("status") != "playing":
            return [], f"对局已结束（status={session.get('status')}），无法继续动作"
        if not self.sm.can(action_type):
            finale_skill = (self.sm.stage.value == "accuse" and action_type == "skill"
                and _skill_name(payload) in ("bid_headline", "refute", "buy_heat", "flood_comments", "report_spam", "truth_check"))
            # bid_pass：仅在竞价窗口开启时放行（本窗口放弃出价，零 AP）
            bid_pass_ok = (action_type == "bid_pass"
                           and self._headline_window is not None)
            # 破冰幕 StageMachine 关掉整类 skill；图钉/破茧/策反是 0 点收证，单独放行
            if (not finale_skill and not bid_pass_ok
                    and not (action_type == "skill" and _skill_name(payload) in ICEBREAKER_SKILLS)):
                allowed = sorted(a for a in ("search", "chat", "skill", "counsel",
                                             "vote", "advance") if self.sm.can(a))
                return [], (f"当前阶段「{STAGE_NAMES.get(self.sm.stage.value, self.sm.stage.value)}」"
                            f"不允许动作 {action_type}（引擎裁决，允许：{'/'.join(allowed) or '无'}）")
        actor = (actor or "player:1").strip()
        vacant_ai = bool(allow_ai and (
            actor.startswith("ai:") or actor.startswith("player:ai:")))
        if actor.startswith("ai:"):
            if not allow_ai:
                return [], "actor 必须为 player:{id}（npc/dm 事件由服务端发出）"
        elif not actor.startswith("player:"):
            return [], "actor 必须为 player:{id}（npc/dm 事件由服务端发出）"
        # 空席 AI 不当真人入列（避免冒领共享席 / 把 faction 写进 players）
        if (actor.startswith("player:") and not vacant_ai and all(
                p["player_id"] != actor for p in session["players"])):
            session["players"].append({"player_id": actor, "faction": "truth",
                                       "joined_at": time.time()})
        payload = dict(payload or {})
        # vote 不在此处硬门禁：party 的"≥2 张证据卡"由 _do_vote 软门禁以
        # vote_rejected 事件呈现；单人模式由 resolver 结算 valid 语义判定。
        # 这样既符合 GAME_DESIGN_V3 §3.6（结算层校验），又不与客户端预检冲突。
        if action_type == "skill":
            payload["skill"] = _skill_name(payload)
        if action_type == "search" and not str(payload.get("keyword", "")).strip():
            return [], "搜证需要关键词"
        cost = ACTION_COST.get(action_type, 0)
        if action_type == "skill":
            skill = payload.get("skill", "truth_check")
            if skill not in REGISTERED_SKILLS:
                # P1 修复：未知/未注册技能零扣费——此前 SKILL_COST.get(skill, 1)
                # 会先扣 1 点行动力再回 bad_skill 事件，白扣 AP。
                return [make_event("system", session.get("session_id", ""),
                                   session.get("round", 1), "dm", {
                    "event": "bad_skill", "ok": False,
                    "notice": f"未知技能：{skill}（服务端未注册，行动力未扣除）",
                    "source": "engine"})], None
            cost = SKILL_COST.get(skill, 1)
            if skill == "bid_headline":
                amount = payload.get("amount")
                if type(amount) is not int or amount < 1 or amount > 12:
                    return [], "竞标出价须为 1–12 的整数行动点"
                topic_id = str(payload.get("post") or payload.get("topic") or "").strip()
                if topic_id not in self.of._posts:
                    return [], "请选择一条当前可见热搜"
                if self.sm.stage.value not in ("round_table", "accuse"):
                    return [], "圆桌讨论后才可争取头条"
                if self._headline_window is not None:
                    # 窗口竞价：出价仅冻结 AP（handler 内处理，反超退还/胜者结算扣除），
                    # 标准扣费路径 cost=0，避免双扣。
                    payload["_hl_window_open"] = True  # 分发前懒结算可能到期清算窗口
                    if amount < int(self._headline_window["min_bid"]):
                        return [], (f"出价不得低于底价 "
                                    f"{self._headline_window['min_bid']} 点行动点")
                    cost = 0
                else:
                    cost = amount  # 无开启窗口：旧一次性语义（开窗+出价+立即结算）
            if skill == "puzzle":
                from collections import Counter
                target = _norm_npc(payload.get("target"))
                proposal = payload.get("proposal")
                blocks = self.ms.visible_blocks(target, include_heart=True)
                if not blocks or not isinstance(proposal, list) or not all(isinstance(x, str) for x in proposal):
                    return [], "请选择一位有记忆的角色并提交记忆块排序"
                if Counter(proposal) != Counter(b.id for b in blocks):
                    return [], "记忆已更新或排序不完整，请重新打开拼图"
                if self.ms.tamper_available() < 2:
                    return [], "拼图对质需要 2 个篡改点"
        # AP 分流：party 模式真人各算各的（PartyBoard 池，每轮 3）；其余走幕配额池
        party_mode = session.get("mode") == "party"
        ap_actor = actor
        if vacant_ai:
            cid = _ai_speaker_char(actor)
            if cid:
                ap_actor = f"ai:{cid}"
        if party_mode and vacant_ai and ap_actor not in self.pb.ap_state():
            try:
                self.pb.ensure_ap(ap_actor)
            except AttributeError:
                self.pb._ap.setdefault(ap_actor, 3)
            if ap_actor not in self.pb.ap_state():
                self.pb._ap.setdefault(ap_actor, 3)
        if cost > 0:
            if party_mode and ap_actor in self.pb.ap_state():
                if not self.pb.spend(ap_actor, cost):
                    return [], (f"行动力不足（你剩 {self.pb.ap_state().get(ap_actor, 0)}，"
                                f"需 {cost}）；party 模式每人每轮 3 点")
            elif vacant_ai:
                pass  # 空席不偷玩家共享 AP，也不因未入座拒绝
            elif party_mode:
                return [], "party 模式需先入座（POST /api/session/{id}/join）再行动"
            elif session.get("actions_left", 0) < cost:
                return [], (f"行动力不足（剩 {session.get('actions_left', 0)}，需 {cost}）；"
                            f"可 advance 结束本轮")

        # 热搜竞价窗口懒结算（契约：下一动作/advance 时检查 deadline，无需真定时器）
        lazy_events = self._maybe_settle_headline(session)
        events = getattr(self, f"_do_{action_type}")(session, actor, payload or {})
        if lazy_events:
            events = lazy_events + events
        if cost > 0 and any((e.get("payload") or {}).get("event") == "bad_location"
                            for e in events):
            if party_mode:
                self.pb.refund(ap_actor, cost)
            cost = 0
        if (cost > 0 and not vacant_ai
                and not (party_mode and ap_actor in self.pb.ap_state())):
            self.sm.actions_left -= cost
        session["actions_left"] = self.sm.actions_left
        if party_mode:
            session["ap_state"] = self.pb.ap_state()
            session["seats"] = self.seats_public()
        session["round"] = max(1, session.get("round", 1))
        session["heat"] = self.of.heat
        session["flaw_count"] = self.ec.flaw_count()
        session["boss_ready"] = self.ec.boss_ready()
        session["counsel_count"] = self.ks.clinic_settlement()["counsel_count"]
        session["held_cards"] = [c.get("id") for c in self.ks.held_cards()]
        session["evidence_cards"] = [e["evidence_id"] for e in self.ec.evidence_cards()]
        session["pollution"] = self.pc.summary()
        session["echo"] = self.el.summary()
        session["debate"] = self.jd.summary()
        session["search_bias"] = dict(self.search_bias)
        session["cocoon"] = {"active": self.cocoon_active, "broken": self.cocoon_broken}
        session["evidence_links"] = list(self.evidence_links)
        session["defection"] = dict(self.defection)
        session["votes"] = dict(self.votes)
        all_clues: set[str] = set()
        for p in session["players"]:
            all_clues.update(self.ec.get_player_clues(p["player_id"]))
        session["clues_gained"] = sorted(all_clues)
        salt_n = len(SALT_EGG_IDS & all_clues)
        self.plot_fragments = max(int(self.plot_fragments or 0), salt_n)
        session["plot_fragments"] = self.plot_fragments
        session["v587_exposed"] = bool(session.get("v587_exposed") or self.v587_exposed)
        session["stage"] = self.sm.stage.value
        session["stage_name"] = STAGE_NAMES.get(self.sm.stage.value,
                                                self.sm.stage.value)
        session["actions"].append({"type": action_type, "actor": actor,
                                   "payload": payload or {}})
        session["party"] = self.party_snapshot()  # 阵营暗置数据仅存服务端档，前端零透出
        session["updated_at"] = time.time()
        if party_mode:
            events.append(make_event("system", session["session_id"],
                                     session.get("round", 1), actor, {
                "event": "ap_sync",
                "apSet": self.pb.ap_state().get(ap_actor, 0),
                "apMax": 3, "player_id": actor}))
        elif cost > 0 and not vacant_ai:
            events.append(make_event("system", session["session_id"],
                session.get("round", 1), actor, {"event": "ap_sync",
                "apSet": session["actions_left"], "player_id": actor}))
        return events, None

    # ------------------------------------------------------------------ chat
    def _do_chat(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        text = str(payload.get("text", ""))[:500]
        target = _norm_npc(payload.get("target") or payload.get("char_id"))
        events: list[dict] = []
        # 0) 回声档案（S1）：只记玩家自己的原话，终局由 DM 投影使用
        if text.strip():
            self.el.add(actor, text, target, rnd)
            speaker = _ai_speaker_char(actor)
            chat_pl = {
                "actor_kind": "npc" if speaker else "player", "text": text,
                "char_id": speaker or target,
                "target": f"npc:{target}" if target else "",
                "player_id": actor}
            if payload.get("whisper"):
                chat_pl["whisper"] = True
                chat_pl["to"] = str(payload.get("to") or "")
            events.append(make_event("chat", sid, rnd, actor, chat_pl))
        # 1) 【已打码】彩蛋（引擎确定性词表）
        bake = self.sm.bake_check(text)
        if bake:
            bake["session_id"] = sid
            bake["round"] = rnd
            events.append(bake)
        # 2) chat:keyword_* 对话框触发线索（kanshan 扩展语法，B 引擎已实现）
        for clue in list(self.ec.pool.values()):
            cond = str(clue.get("unlock_condition", ""))
            if not cond.startswith("chat:keyword_"):
                continue
            kw = cond[len("chat:keyword_"):].strip()
            if kw and kw in text:
                self.ec.sync_context(chat_keywords=[kw])
                got = self.ec.release(clue["id"], actor)
                if got:
                    events.append(self._clue_event(sid, rnd, actor, got,
                                                   trigger=f"chat:{kw}"))
        # 3) NPC 演出为 C 组职责（llm_client/npc_agent）：未接前诚实占位，不伪造台词
        npc = next((n for n in self._roster if n["id"] == target), None)
        if npc is not None:
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "npc_pending", "target": f"npc:{npc['id']}",
                "notice": f"{npc['name']}的演出由 C 组 Agent 接入（llm_client）；"
                          f"引擎已结算本条对话的确定性联动（关键词线索/打码彩蛋）",
                "reply_to": actor, "player_text": text}))
        events.append(make_event("danmaku", sid, rnd, "kanshan", {
            "items": _ambient_danmaku(), "source": "ambient"}))
        return events

    # ----------------------------------------------------------------- search
    def _do_search(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        raw_loc = str(payload.get("location", "")).strip()
        keyword = str(payload.get("keyword", "")).strip()
        known_names = set(self._loc_names.values())
        # 本局 scene_map 已是 loc_*（工作台快本）时，不要先译成看山旧 key
        if raw_loc not in self._loc_names and raw_loc not in known_names:
            raw_loc = LOC_ALIASES.get(raw_loc, raw_loc)
        # location 三口径：本局 loc_* / scene_map key / 中文名
        if raw_loc in self._loc_names:
            location = self._loc_names[raw_loc]
        elif raw_loc in set(self._loc_names.values()):
            location = raw_loc
        else:
            sample = "/".join(sorted(self._locations)[:6])
            return [make_event("system", sid, rnd, "dm", {
                "event": "bad_location", "location": raw_loc,
                "notice": f"未知搜证地点（scene_map key 示例：{sample}…，"
                          f"亦可直接用中文名如「看山工位」）"})]
        res = self.ec.search(location, keyword, actor,
                             round_no=session["round"])
        events: list[dict] = []
        if not res.get("hit"):
            # 将引擎的非剧透关键词提示显式传给客户端，避免搜错后只能看到
            # 环境描写而不知道如何继续。
            events.append(make_event("search_result", sid, rnd, actor, {
                "location": location, "keyword": keyword, "hit": False,
                "ambient": (res.get("env_clue") or {}).get("fact", ""),
                "hint": res.get("hint"), "source": "engine"}))
        for clue in res["clues"]:
            events.append(self._clue_event(sid, rnd, actor, clue,
                                           location_status=res["location_status"],
                                           heat=res["heat"]))
        if res.get("env_clue"):
            events.append(self._clue_event(sid, rnd, actor, res["env_clue"],
                                           location_status=res["location_status"],
                                           heat=res["heat"],
                                           note="环境线索" if not res["disturb"] else "搜证冲突痕迹"))
        if any(self.ec.tier_of(c) == "boss_flaw" for c in res["clues"]):
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "flaw_progress",
                "text": f"叮——看山的行为出现了第 {self.ec.flaw_count()}/5 处破绽",
                "flaw_count": self.ec.flaw_count()}))
            if self.ec.boss_ready():
                events.append(make_event("system", sid, rnd, "dm", {
                    "event": "boss_ready",
                    "text": "叮——5 处破绽集齐，圆桌按钮「指认：DM」已解锁",
                    "flaw_count": self.ec.flaw_count()}))
        # 搜证附带：知识卡抽取（全队共享池）
        drawn = self.ks.draw(actor)
        if drawn:
            card = drawn["card"]
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "card_drawn", "card": {"id": card.get("id"),
                                                "title": card.get("title"),
                                                "author": card.get("author"),
                                                "topic_tag": card.get("topic_tag"),
                                                "binds": card.get("binds")},
                "text": f"叮——心晴自习室抽到知识卡《{card.get('title')}》"
                        f"（作者：{card.get('author')}）"}))
        # 证据合成（3 条同 truth_node）
        composed = self.ec.try_compose(actor)
        if composed:
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "evidence_composed",
                "text": f"叮——证据合成成功：{len(composed['clue_ids'])} 条线索指向同一真相节点",
                "evidence": composed}))
        if not events:
            memo = self.dd.memo_for(self.ec, location, actor)
            if memo:
                events.append(make_event("system", sid, rnd, "dm", {
                    "event": "memo", "text": memo.get("text", ""),
                    "notice": "档案局备忘录（点方向不泄底）", "source": "engine"}))
            else:
                events.append(make_event("system", sid, rnd, "dm", {
                    "event": "search_empty_result",
                    "text": "什么都没搜到（引擎未发放任何线索）",
                    "notice": "什么都没搜到（引擎未发放任何线索）"}))
        tag_src = list(res.get("clues") or [])
        if res.get("env_clue"):
            tag_src.append(res["env_clue"])
        tags: list[str] = []
        for c in tag_src:
            tags.extend(c.get("tags") or [])
        if not tags:
            # 搜空也记偏执：地点池 tag（中文名 / scene key / loc_* 都对上）
            loc_keys = {location, raw_loc}
            for c in self.ec.pool.values():
                if str(c.get("location") or "") in loc_keys:
                    tags.extend(c.get("tags") or [])
        if keyword:
            tags.append(keyword)
        if self._note_search_tags(tags):
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "cocoon_enter", "bias": dict(self.search_bias),
                "text": "叮——算法已读懂你的口味：热搜开始只喂你爱看的。",
                "source": "engine"}))
        return events

    def _clue_event(self, sid: str, rnd: int, actor: str, clue: dict,
                    location_status: str | None = None, heat: int | None = None,
                    trigger: str | None = None, note: str | None = None) -> dict:
        payload = {
            "clue_id": clue["id"], "tier": self.ec.tier_of(clue),
            "name": clue.get("name", ""), "text": clue.get("fact", ""),
            "flavor_hint": clue.get("flavor_hint", ""),
            "location": clue.get("location", ""),
            "linked_truth_nodes": clue.get("linked_truth_nodes", []),
            "tags": clue.get("tags") or [],
            "flaw_id": clue.get("flaw_id"),
            "danmaku": _ambient_danmaku(), "source": "engine",
        }
        if location_status:
            payload["location_status"] = location_status
        if heat is not None:
            payload["heat"] = heat
        if trigger:
            payload["trigger"] = trigger
        if note:
            payload["note"] = note
        cid = clue.get("id")
        if cid in SALT_EGG_IDS:
            held = {x for x in SALT_EGG_IDS if self.ec.released.get(x)}
            self.plot_fragments = max(int(self.plot_fragments or 0), len(held))
        return make_event("clue_gained", sid, rnd, actor, payload)

    # ---------------------------------------------------------------- counsel
    def _do_counsel(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        card_id = str(payload.get("card", "")).strip()
        target = _norm_npc(payload.get("target"))
        # G10 修复：开导前校验卡片已抽取（防绕过自习室抽卡设计）
        held = {c.get("id") for c in self.ks.held_cards()}
        if card_id and card_id not in held:
            return [make_event("system", sid, rnd, "dm", {
                "event": "card_not_held",
                "notice": f"知识卡 {card_id} 尚未在心晴自习室抽取，无法使用",
                "source": "engine"})]
        res = self.ks.counsel(actor, target, card_id)
        events = [make_event("counsel_result", sid, rnd, actor, {
            "card": card_id, "target": f"npc:{target}",
            "matched": res["matched"], "effect": res.get("effect"),
            "transcript_hint": res.get("transcript_hint", ""),
            "unlocked": res.get("unlocked"), "source": "engine"})]
        if not res["matched"]:
            events.append(make_event("danmaku", sid, rnd, "kanshan", {
                "items": ["答非所问预警", "没知识还硬开导", "群嘲x1"], "source": "ambient"}))
            return events
        # 开导演算联动（B 引擎裁决）
        self.ec.sync_context(counsel_cards=[card_id])
        self.ec.sync_context(memory_versions={
            n["id"]: self.ms.current_version(n["id"]) for n in self._roster})
        effect = res.get("effect")
        if effect == "memory_unlock":
            events.extend(self._unlock_memory(sid, rnd, actor, target, "counsel"))
        elif effect == "buff_ap":
            self.sm.actions_left += 1
        elif effect == "plot_fragment":
            self.plot_fragments += 1
        elif effect == "boss_key":
            self.boss_key = True
        # 开导成功即发放 counsel:<card_id> 条件线索。
        # kc_06 效果是 memory_unlock，旧逻辑只在 evidence 分支放 clue_030，玩家卡在 3/5。
        for clue in list(self.ec.pool.values()):
            if str(clue.get("unlock_condition", "")) != f"counsel:{card_id}":
                continue
            got = self.ec.release(clue["id"], actor)
            if not got:
                continue
            events.append(self._clue_event(sid, rnd, actor, got,
                                           trigger=f"counsel:{card_id}"))
            if self.ec.tier_of(got) == "boss_flaw":
                events.append(make_event("system", sid, rnd, "dm", {
                    "event": "flaw_progress",
                    "text": f"叮——看山的行为出现了第 {self.ec.flaw_count()}/5 处破绽",
                    "flaw_count": self.ec.flaw_count()}))
        session["plot_fragments"] = self.plot_fragments
        session["boss_key"] = self.boss_key
        return events

    def _unlock_memory(self, sid: str, rnd: int, actor: str,
                       char_id: str, reason: str) -> list[dict]:
        """记忆解锁 + 篡改点自动转线索卡入证据链（memory_system 裁决）。"""
        mres = self.ms.unlock_next(char_id, reason)
        events = []
        if mres.get("status") == "ok":
            events.append(make_event("memory_unlock", sid, rnd, actor, {
              "owner": f"npc:{char_id}",
                **self.memory_view(char_id),
                "unlocked_version": mres["unlocked_version"],
                "revealed": len(mres.get("revealed_blocks", [])),
                "reason": reason, "source": "engine"}))
            for tp in mres.get("tamper_points", []):
                self.ec.ingest_clue(tp["clue_card"], owner=actor)
                events.append(self._clue_event(sid, rnd, actor, tp["clue_card"],
                                               note=f"篡改点 {tp['id']}"))
        return events

    # ------------------------------------------------------------------ skill
    def _do_skill(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        skill = _skill_name(payload)
        # 机制幕门控（A 裁决）：心声系（memory_fix）第二幕解锁；舆论系（refute/buy_heat）第三幕解锁
        ACT_NOW = {"break_ice": 1, "investigate": 2, "round_table": 3, "accuse": 4}
        act_now = ACT_NOW.get(self.sm.stage.value, 2)
        if act_now < 2 and skill not in ICEBREAKER_SKILLS:
            return [make_event("system", sid, rnd, "dm", {
                "event": "locked",
                "notice": "破冰阶段仅可对话——搜证、开导、舆论技能将在搜证幕起陆续解锁",
                "source": "engine"})]
        if skill == "refute":
            post_id = str(payload.get("post", ""))
            card_id = str(payload.get("card", ""))
            res = self.of.refute(actor, post_id, card_id)
            ammo_spent = 0
            if res.get("ok"):
                self.refute_count += 1
                ammo_spent = self.pc.spend_ammo(1)
                if ammo_spent:
                    extra = -2
                    self.of.apply_heat(extra)
                    res["heat_delta"] = int(res.get("heat_delta") or 0) + extra
                    res["heat"] = self.of.heat
            ok_text = f"辟谣成功：热度 {res['heat_delta']:+d}"
            if ammo_spent:
                ok_text += f"（对照弹药加码，热度再降 2，剩余弹药 {self.pc.ammo()}）"
            fail_text = (f"辟谣失败（{res.get('reason')}）：热度反涨 +{res['heat_delta']}，"
                         f"弹幕群嘲{'：' + '；'.join(res.get('crowd_mocks', [])[:2]) if res.get('crowd_mocks') else ''}")
            events = [make_event("system", sid, rnd, "dm", {
                "event": "refute_result", "ok": res["ok"],
                "post": post_id, "card": card_id,
                "heat_delta": res["heat_delta"], "heat": self.of.heat,
                "unlocked_clue": res.get("unlocked_clue"),
                "crowd_mocks": res.get("crowd_mocks", []),
                "ammo_spent": ammo_spent, "ammo": self.pc.ammo(),
                "text": ok_text if res["ok"] else fail_text,
                "source": "engine"})]
            if res.get("unlocked_clue") and self.ec.clue(res["unlocked_clue"]):
                got = self.ec.release(res["unlocked_clue"], actor)
                if got:
                    events.append(self._clue_event(sid, rnd, actor, got,
                                                   trigger=f"refute:{post_id}"))
            events.append(self._hotfeed_event(sid, rnd))
            return events
        if skill == "buy_heat":
            res = self.of.buy_heat(actor, str(payload.get("post", "")))
            if res.get("ok"):
                self.buy_heat_count += 1
            return [make_event("system", sid, rnd, "dm", {
                "event": "buy_heat_result", "ok": res["ok"], "reason": res.get("reason"),
                "heat": res["heat"], "heat_delta": res["heat_delta"],
                "text": (f"买热搜成功：《{res.get('title', '')}》置顶，热度 {res['heat']:+d}"
                         if res["ok"] else f"买热搜失败（{res.get('reason')}）"),
                "source": "engine"}),
                self._hotfeed_event(sid, rnd)]
        if skill == "memory_fix":
            target = _norm_npc(payload.get("target"))
            if not any(n["id"] == target for n in self._roster):
                return [make_event("system", sid, rnd, "dm", {
                    "event": "bad_target", "notice": f"记忆修复目标不存在：{target}"})]
            events = self._unlock_memory(sid, rnd, actor, target, "memory_fix")
            if not events:
                events = [make_event("system", sid, rnd, "dm", {
                    "event": "memory_no_op",
                    "text": f"{target} 的记忆已是最新版本，无可修复出入"})]
            return events
        if skill == "puzzle":
            target = _norm_npc(payload.get("target"))
            self.ms.spend_tamper_points(2)
            result = self.ms.puzzle_judge(target, payload["proposal"])
            return [make_event("system", sid, rnd, actor, {
                "event": "puzzle_result", "char_id": target, "ok": True,
                "correct": result["correct"], "tamper_available": self.ms.tamper_available(),
                "notice": "时间线排序正确。" if result["correct"] else "排序有出入，再核对各段记忆的时间。",
                "source": "engine"})]
        if skill == "bid_headline":
            topic_id = str(payload.get("post") or payload.get("topic") or "").strip()
            faction = self.pb.faction_of(actor) or "truth"
            window = self._headline_window
            if window is None:
                if payload.get("_hl_window_open"):
                    # 校验时窗口尚在、分发前懒结算恰好到期清算 → 迟到出价拒绝（零扣费）
                    return [make_event("system", sid, rnd, actor, {
                        "event": "bid_rejected",
                        "notice": "竞价窗口已截止并结算，本次出价未受理（行动力未扣除）",
                        "source": "engine"})]
                # 向后兼容硬约束：无开启窗口 → 旧一次性语义（自动开窗+出价+立即结算），
                # 既有测试 / 单人 mock / 存档不受影响。
                self.of.open_headline_bidding(rnd)
                bid = self.of.bid_headline(actor, faction, payload["amount"], post_id=topic_id)
                result = self.of.settle_headline()
                return [make_event("system", sid, rnd, actor, {
                    "event": "headline_result", "source": "engine", "cost": payload["amount"],
                    "bid": {k: v for k, v in bid.items() if k != "faction"},
                    "settle": {k: result.get(k) for k in ("ok", "winner", "post_id", "amount")},
                    "result_line": "所选帖子已登上头条；置顶不会改变证据真假。",
                    "heatSet": self.of.heat}), self._hotfeed_event(sid, rnd)]
            # 窗口竞价语义：先懒结算过期窗口 → 出价冻结 AP → 广播 headline_bid
            events = self._maybe_settle_headline(session)
            window = self._headline_window
            if window is None:
                return events + [make_event("system", sid, rnd, actor, {
                    "event": "bid_rejected",
                    "notice": "竞价窗口已截止并结算，本次出价未受理（行动力未扣除）",
                    "source": "engine"})]
            amount = int(payload["amount"])
            prev_frozen = int(window["frozen"].get(actor, 0))
            bids_before = list(self.of._headline["bids"]) if self.of._headline else []
            prev_top = None
            if bids_before:
                _max = max(b["amount"] for b in bids_before)
                prev_top = next(b for b in bids_before if b["amount"] == _max)
            freeze_err = self._headline_freeze_ap(session, actor, amount, prev_frozen)
            if freeze_err:
                return events + [make_event("system", sid, rnd, actor, {
                    "event": "bid_rejected", "notice": freeze_err,
                    "source": "engine"})]
            window["frozen"][actor] = amount
            bid = self.of.bid_headline(actor, faction, amount, post_id=topic_id)
            if not bid.get("ok"):
                # 引擎拒收（理论不可达：窗口已同步开启）：退还冻结并如实上报
                self._headline_refund_ap(session, actor, amount)
                window["frozen"].pop(actor, None)
                return events + [make_event("system", sid, rnd, actor, {
                    "event": "bid_rejected",
                    "notice": f"出价未被受理（{bid.get('reason')}）",
                    "source": "engine"})]
            bids_now = self.of._headline["bids"]
            top_amount = max(b["amount"] for b in bids_now)
            top_bid = next(b for b in bids_now if b["amount"] == top_amount)
            is_top = top_bid["actor"] == actor  # 平价先到先得（引擎 list 序）
            events.append(make_event("headline_bid", sid, rnd, actor, {
                "window_id": window["window_id"], "bidder": actor,
                "amount": amount, "is_top": is_top, "top_amount": top_amount,
                "source": "engine"}))
            if (is_top and prev_top is not None and prev_top["actor"] != actor
                    and prev_top["amount"] < amount):
                # 原最高者被反超：退还其冻结 AP，并向其提示（可并入 headline_bid
                # is_top=false 处理，但事件按契约独立存在）
                self._headline_refund_ap(
                    session, prev_top["actor"], int(window["frozen"].pop(prev_top["actor"], 0)))
                events.append(make_event("headline_outbid", sid, rnd,
                                         prev_top["actor"], {
                    "window_id": window["window_id"], "bidder": actor,
                    "prev_bidder": prev_top["actor"],
                    "prev_amount": int(prev_top["amount"]), "new_amount": amount,
                    "source": "engine"}))
            return events
        if skill == "pollution_open":
            case = self.pc.open_case(actor)
            if not case:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "pollution_done", "summary": self.pc.summary(),
                    "text": "全部对照题已完成——水军的话术已经被你拆干净了。",
                    "source": "engine"})]
            return [make_event("system", sid, rnd, "dm", {
                "event": "pollution_case", "case": case,
                "text": f"对照题《{case['title']}》（原作者 {case['author']}）："
                        f"下栏是水军改写版，圈出被植入的 {case['changed_total']} 处操纵。",
                "summary": self.pc.summary(), "source": "engine"})]
        if skill == "pollution_mark":
            pc_id = str(payload.get("case", ""))
            picks = [str(p) for p in (payload.get("picks") or [])]
            res = self.pc.mark(actor, pc_id, picks)
            if not res.get("ok"):
                return [make_event("system", sid, rnd, "dm", {
                    "event": "bad_target",
                    "notice": res.get("transcript_hint", "对照题不存在")})]
            if res.get("heat_delta"):
                self.of.apply_heat(res["heat_delta"])
            if res.get("ap_refund"):
                self.sm.actions_left += int(res["ap_refund"])
            return [make_event("system", sid, rnd, "dm", {
                "event": "pollution_result", "case_id": pc_id,
                "correct": res["correct"], "missed": res["missed"],
                "wrong": res["wrong"], "passed": res["passed"],
                "changed_total": res["changed_total"], "ammo": res["ammo"],
                "ammo_earned": self.pc.ammo_earned(),
                "first_try": res.get("first_try"),
                "ap_refund": res.get("ap_refund", 0),
                "heat_delta": res.get("heat_delta", 0), "heat": self.of.heat,
                "revealed": res.get("revealed", []),
                "text": res["transcript_hint"],
                "summary": self.pc.summary(), "source": "engine"})]
        if skill == "echo_open":
            ch = self.el.challenge(actor)
            return [make_event("system", sid, rnd, "dm", {
                "event": "echo_challenge", "challenge": ch,
                "log": self.el.log(actor), "summary": self.el.summary(actor),
                "text": ch.get("text", ""), "source": "engine"})]
        if skill == "echo_defend":
            res = self.el.defend(actor, [int(p) for p in (payload.get("picks") or [])
                                         if str(p).lstrip("-").isdigit()])
            events = []
            if res.get("passed"):
                self.sm.actions_left += 1            # 自证成功返还 1 AP
                self.echo_defended = True
                self.ec.sync_context(echo_flags={"contradiction"})
                got = self.ec.release("clue_033", actor)
                if got:
                    events.append(self._clue_event(sid, rnd, actor, got,
                                                   trigger="echo:contradiction"))
            events.insert(0, make_event("system", sid, rnd, "dm", {
                "event": "echo_defend_result", "passed": bool(res.get("passed")),
                "mode": res.get("mode"), "reason": res.get("reason"),
                "ap_refund": 1 if res.get("passed") else 0,
                "text": res.get("transcript_hint", ""), "source": "engine"}))
            return events
        if skill == "debate_open":
            st = self.jd.open_case(self.of.heat)
            return [make_event("system", sid, rnd, "judge", {
                "event": "debate_open", "stance": st["stance"], "score": st["score"],
                "need": st["need"], "summary": self.jd.summary(),
                "text": st["text"], "source": "engine"})]
        if skill == "debate_submit":
            claim = str(payload.get("claim", ""))[:500]
            ctx = {
                "evidence_terms": [c.get("name", "") for c in self.ec.evidence_cards()]
                + [self.ec.clue(cid).get("name", "")
                   for cid in session.get("clues_gained", []) if self.ec.clue(cid)],
                "card_titles": [c.get("title", "") for c in self.ks.held_cards()],
                "echo_ok": self.echo_defended,
                "heat": self.of.heat,
            }
            res = self.jd.submit(actor, claim, ctx)
            events = [make_event("system", sid, rnd, "judge", {
                "event": "debate_result", "gain": res["gain"], "total": res["total"],
                "stance": res["stance"], "convinced": res["convinced"],
                "reasons": res.get("reasons", []), "summary": self.jd.summary(),
                "text": res["transcript_hint"], "source": "engine"})]
            if res.get("convinced"):
                self.ec.sync_context(debate_flags={"convinced"})
                got = self.ec.release("clue_034", actor)
                if got:
                    events.append(self._clue_event(sid, rnd, actor, got,
                                                   trigger="debate:convinced"))
            return events
        if skill == "judge_line":
            # Persist the handshake so a later bypass cannot be forged on a normal room.
            if payload.get("demo_bypass") is True:
                session["demo_bypass"] = True
            events: list[dict] = []
            if self.sm.stage == stage_machine.Stage.BREAK_ICE:
                self.sm.advance()
                events.append(make_event("system", sid, rnd, "dm", {
                    "event": "stage_changed", "stage": self.sm.stage.value,
                    "stage_name": STAGE_NAMES.get(self.sm.stage.value,
                                                  self.sm.stage.value),
                    "actions_left": self.sm.actions_left,
                    "source": "judge_line"}))
            granted: list[str] = []
            for cid in JUDGE_LINE_CLUES:
                if not self._owned_clue(session, actor, cid):
                    got = self.ec.release(cid, actor)
                    if got:
                        events.append(self._clue_event(
                            sid, rnd, actor, got, trigger="judge_line"))
                        granted.append(cid)
                else:
                    granted.append(cid)
                if any((l.get("clue_id") or l.get("clueId")) == cid
                       for l in self.evidence_links):
                    continue
                clue = self.ec.clue(cid)
                if not clue:
                    continue
                nodes = [str(n) for n in (clue.get("linked_truth_nodes") or [])
                         if str(n).startswith("tn_")]
                self.evidence_links.append(
                    {"clue_id": cid, "clueId": cid, "nodes": nodes})
                events.append(make_event("system", sid, rnd, "dm", {
                    "event": "evidence_pin", "clueId": cid, "clue_id": cid,
                    "nodes": nodes, "coverage": self._pin_coverage(),
                    "silent": True, "source": "engine"}))
            cov = self._pin_coverage()
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "judge_line_ready", "granted": granted,
                "coverage": cov, "stage": self.sm.stage.value,
                "text": (f"评委线已开：对照 → 回声 → 法官 → 画像"
                         f"（拼图覆盖 {cov['pct']}%）"),
                "source": "engine"}))
            return events
        if skill == "evidence_pin":
            clue_id = str(payload.get("clueId") or payload.get("clue_id") or "").strip()
            if not clue_id:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "pin_rejected", "notice": "缺少线索 id", "source": "engine"})]
            if not self._owned_clue(session, actor, clue_id):
                return [make_event("system", sid, rnd, "dm", {
                    "event": "pin_rejected", "clue_id": clue_id,
                    "notice": "还没搜到这条线索", "source": "engine"})]
            clue = self.ec.clue(clue_id)
            if not clue:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "pin_rejected", "clue_id": clue_id,
                    "notice": "线索不存在", "source": "engine"})]
            if any((l.get("clue_id") or l.get("clueId")) == clue_id
                   for l in self.evidence_links):
                return [make_event("system", sid, rnd, "dm", {
                    "event": "pin_rejected", "clue_id": clue_id,
                    "notice": "这条已在拼图上", "source": "engine"})]
            nodes = list(clue.get("linked_truth_nodes") or [])
            self.evidence_links.append(
                {"clue_id": clue_id, "clueId": clue_id, "nodes": nodes})
            cov = self._pin_coverage()
            return [make_event("system", sid, rnd, "dm", {
                "event": "evidence_pin", "clueId": clue_id, "clue_id": clue_id,
                "nodes": nodes, "coverage": cov,
                "text": f"已钉入证据拼图：覆盖 {cov['pct']}% 核心真相节点",
                "source": "engine"})]
        if skill == "cocoon_break":
            if not self.cocoon_active:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "cocoon_rejected",
                    "notice": "你还没掉进茧房，破什么茧", "source": "engine"})]
            if self.cocoon_broken > 0:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "cocoon_rejected",
                    "notice": "茧已破，保持清醒就好", "source": "engine"})]
            self.cocoon_broken += 1
            return [make_event("system", sid, rnd, "dm", {
                "event": "cocoon_break", "broken": self.cocoon_broken,
                "text": "🦋 破茧成功——你主动戳穿了算法投喂，异见重新可见",
                "source": "engine"})]
        if skill == "defect":
            cid = _norm_npc(payload.get("charId") or payload.get("char_id"))
            if cid not in DEFECT_CHARS:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "defect_rejected",
                    "notice": "这位不是被裹挟者", "source": "engine"})]
            if (self.defection.get(cid) or {}).get("flipped"):
                return [make_event("system", sid, rnd, "dm", {
                    "event": "defect_rejected",
                    "notice": "已经策反过了", "source": "engine"})]
            cov = self._pin_coverage()
            if cov["pct"] < 50:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "defect_rejected", "coverage": cov,
                    "notice": (f"证据不足，无法说服被裹挟者跳反"
                               f"（需 ≥50% 真相节点，当前 {cov['pct']}%）"),
                    "source": "engine"})]
            self.defection[cid] = {"flipped": True, "by": actor}
            return [make_event("system", sid, rnd, "dm", {
                "event": "defect", "charId": cid, "char_id": cid,
                "coverage": cov, "text": "策反成功", "source": "engine"})]
        if skill == "draw_card":
            drawn = None
            failed = False
            try:
                drawn = self.ks.draw(actor)
            except Exception:
                failed = True
            card = drawn.get("card") if isinstance(drawn, dict) else None
            if not isinstance(card, dict):
                empty = not failed and drawn is None
                return [make_event("system", sid, rnd, "dm", {
                    "event": "card_drawn",
                    "notice": "知识卡已全部集齐" if empty else "抽卡失败",
                    "text": ("十张知识卡已全部集齐" if empty
                             else "抽卡失败，未发放知识卡"),
                    "source": "engine"})]
            face = {"id": card.get("id"), "title": card.get("title"),
                    "author": card.get("author")}
            return [
                make_event("faction_skill", sid, rnd, actor, {
                    "kind": "draw_card", "kc_id": face.get("id"),
                    "card": dict(face),
                    "danmaku": ["抽卡区风景真好看", "知识卡：知乎知识的具象化"]}),
                make_event("system", sid, rnd, "dm", {
                    "event": "card_drawn",
                    "card": dict(face),
                    "text": f"叮——抽到知识卡《{card.get('title')}》",
                    "source": "engine"}),
            ]
        if skill == "closing_speech":
            text = str(payload.get("text", ""))[:200]
            self.pb.final_statement(actor, text)
            return [make_event("system", sid, rnd, actor, {
                "event": "closing_registered", "text": text,
                "player_id": actor})]
        if skill == "hammer_vote":
            target = _norm_npc(payload.get("target"))
            self.pb.hammer_vote(actor, target)
            hr = self.pb.hammer_result()
            return [make_event("system", sid, rnd, actor, {
                "event": "hammer_result", "target": target,
                "most_hammered": hr.get("most_hammered"),
                "tally": hr.get("counts") or {},
                "player_id": actor})]
        if skill in ("flood_comments", "report_spam", "plant_fake", "flip_side",
                     "quiz_draw", "quiz_answer", "radio_tune", "radio_request",
                     "first_vote_cast", "unlock_office", "expose_v587"):
            return self._do_playplus_skill(session, actor, payload, skill, act_now)
        if skill == "truth_check":
            try:
                blocked = self.of.clues_blocked_by_heat()
            except Exception:
                blocked = []
            return [make_event("system", sid, rnd, "dm", {
                "event": "heat_report", "heat": self.of.heat,
                "heat_ratio": self.of.heat_ratio(),
                "blocked_clues": blocked,
                "text": f"当前热度 {self.of.heat}/100"
                        + (f"，{len(blocked)} 条真线索被水军声量淹没" if blocked else ""),
                "source": "engine"})]
        return [make_event("system", sid, rnd, "dm", {
            "event": "bad_skill",
            "notice": "未知技能（可用：refute 辟谣 / buy_heat 买热搜 / "
                      "memory_fix 记忆修复 / truth_check 热度侦察 / "
                      "pollution_open 污染对照 / pollution_mark 提交圈选 / "
                      "echo_open 回声档案 / echo_defend 引自证 / "
                      "debate_open 法官开庭 / debate_submit 陈词辩论 / "
                      "evidence_pin 钉证据 / cocoon_break 破茧 / defect 策反 / "
                      "judge_line 评委线 / flood_comments 控评 / report_spam 举报 / "
                      "plant_fake 投放伪证 / flip_side 翻面 / quiz_draw 快问 / "
                      "radio_tune 广播 / first_vote_cast 举手 / unlock_office 开锁 / "
                      "expose_v587 揭面）"})]

    def _radio_text(self, session: dict, request: bool = False, note: str = "") -> str:
        n = int(session.get("round") or 1)
        c = len(session.get("clues_gained") or [])
        text = RADIO_LINES[(n + (3 if request else 0)) % len(RADIO_LINES)]
        text = text.replace("{n}", str(n)).replace("{c}", str(c))
        if request and note:
            text += " 点播附言：" + str(note)[:40]
        return text

    def _do_playplus_skill(self, session: dict, actor: str, payload: dict,
                           skill: str, act_now: int) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        if skill in ("plant_fake", "flip_side", "unlock_office", "expose_v587") and act_now < 2:
            return [make_event("system", sid, rnd, "dm", {
                "event": "locked",
                "notice": "该技能从搜证幕起解锁", "source": "engine"})]
        if skill in ("flood_comments", "report_spam") and act_now < 3:
            return [make_event("system", sid, rnd, "dm", {
                "event": "locked",
                "notice": "控评/举报是第三幕舆论技", "source": "engine"})]
        if skill == "flood_comments":
            res = self.of.flood_comments(actor, str(payload.get("post") or payload.get("post_id") or ""))
            return [make_event("system", sid, rnd, "dm", {
                "event": "flood_result", "ok": res["ok"], "post": res.get("post_id"),
                "heat": res["heat"], "heat_delta": res["heat_delta"],
                "reason": res.get("reason"),
                "text": ("控评成功：水军声量淹没真线索，热度 +6"
                         if res["ok"] else f"控评失败（{res.get('reason')}）"),
                "source": "engine"}), self._hotfeed_event(sid, rnd)]
        if skill == "report_spam":
            ev = payload.get("evidence") or []
            if not isinstance(ev, list):
                ev = []
            evidence_n = len(ev) or int(payload.get("evidence_n") or 0)
            res = self.of.report_spam(actor, str(payload.get("post") or payload.get("post_id") or ""),
                                      evidence_n=evidence_n)
            return [make_event("system", sid, rnd, "dm", {
                "event": "report_spam_result", "ok": res["ok"], "post": res.get("post_id"),
                "heat": res["heat"], "heat_delta": res["heat_delta"],
                "reason": res.get("reason"),
                "text": ("举报受理：假帖下架，热度 -4"
                         if res["ok"] else f"举报失败（{res.get('reason')}）"),
                "source": "engine"}), self._hotfeed_event(sid, rnd)]
        if skill == "plant_fake":
            if session.get("mode") == "party" and self.pb.faction_of(actor) == "truth":
                return [make_event("system", sid, rnd, "dm", {
                    "event": "plant_fake_result", "ok": False,
                    "notice": "求真阵营不能投放伪证", "source": "engine"})]
            clue_id = str(payload.get("clue") or payload.get("clue_id") or "").strip()
            if not clue_id:
                fake = next((c for _, c in sorted(self.ec.pool.items())
                             if self.ec.tier_of(c) == "fake"), None)
                clue_id = fake["id"] if fake else ""
            got = self.ec.plant_fake(clue_id, actor) if clue_id else None
            events = [make_event("system", sid, rnd, "dm", {
                "event": "plant_fake_result", "ok": bool(got),
                "clue_id": clue_id,
                "text": (f"伪证已混入公开池：《{got.get('name', clue_id)}》——圆桌见真章"
                         if got else "投放失败：只能投放伪造线索"),
                "source": "engine"})]
            if got:
                events.append(self._clue_event(sid, rnd, actor, got, trigger="plant_fake"))
            return events
        if skill == "flip_side":
            clue_id = str(payload.get("clue_id") or payload.get("clue") or "").strip()
            res = self.ec.flip_side(clue_id, actor)
            if not res:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "flip_result", "ok": False, "clue_id": clue_id,
                    "text": "翻面失败：没有背面，或条件未达成，或已经翻过",
                    "source": "engine"})]
            return [make_event("system", sid, rnd, "dm", {
                "event": "flip_result", "ok": True, "clue_id": res["clue_id"],
                "back": res.get("back"), "front": res.get("front"),
                "text": "叮——背面解锁", "source": "engine"})]
        if skill == "quiz_draw":
            quiz = session.setdefault("quiz", {"asked": 0, "score": 0, "seen": [], "idx": None})
            if int(quiz.get("asked") or 0) >= 10:
                session["quiz_score"] = quiz.get("score", 0)
                return [make_event("system", sid, rnd, "dm", {
                    "event": "quiz_question", "asked": quiz["asked"], "score": quiz.get("score", 0),
                    "done": True, "text": "十题已问完。分数已记入本局报告。",
                    "source": "engine"})]
            seen = list(quiz.get("seen") or [])
            left = [i for i in range(len(QUIZ_BANK)) if i not in seen]
            idx = left[0] if left else (int(quiz.get("asked") or 0) % len(QUIZ_BANK))
            row = QUIZ_BANK[idx]
            seen.append(idx)
            quiz["seen"] = seen
            quiz["idx"] = idx
            quiz["q"] = row["q"]
            quiz["options"] = list(row["options"])
            return [make_event("system", sid, rnd, "dm", {
                "event": "quiz_question", "idx": idx, "q": row["q"],
                "options": list(row["options"]), "asked": quiz.get("asked", 0),
                "score": quiz.get("score", 0), "source": "engine"})]
        if skill == "quiz_answer":
            quiz = session.setdefault("quiz", {"asked": 0, "score": 0, "seen": [], "idx": None})
            if quiz.get("idx") is None:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "quiz_result", "ok": False, "toast": "先抽一题",
                    "score": quiz.get("score", 0), "asked": quiz.get("asked", 0),
                    "source": "engine"})]
            try:
                choice = int(payload.get("choice"))
            except (TypeError, ValueError):
                choice = -1
            ok = choice == 0
            quiz["asked"] = int(quiz.get("asked") or 0) + 1
            if ok:
                quiz["score"] = int(quiz.get("score") or 0) + 1
                session["zans"] = int(session.get("zans") or 0) + 2
            quiz["idx"] = None
            quiz["q"] = ""
            session["quiz_score"] = quiz["score"]
            return [make_event("system", sid, rnd, "dm", {
                "event": "quiz_result", "ok": ok, "score": quiz["score"],
                "asked": quiz["asked"], "zans": session.get("zans", 0),
                "toast": "答对。赞数 +2" if ok else "答错。弹幕已经就位，不扣进度。",
                "text": "叮——答对。" if ok else "叮——答错。记住横幅上那八个字就好。",
                "source": "engine"})]
        if skill == "radio_tune":
            return [make_event("system", sid, rnd, "dm", {
                "event": "radio_broadcast", "text": self._radio_text(session, False),
                "request": False, "source": "engine"})]
        if skill == "radio_request":
            return [make_event("system", sid, rnd, "dm", {
                "event": "radio_broadcast",
                "text": self._radio_text(session, True, str(payload.get("note") or "")),
                "request": True, "source": "engine"})]
        if skill == "first_vote_cast":
            target = str(payload.get("target") or "")
            session["first_vote"] = {"target": target, "binding": False}
            return [make_event("system", sid, rnd, "dm", {
                "event": "first_vote_cast", "target": target, "binding": False,
                "text": f"非正式举手：本轮最可疑是 {target}（不影响结局）",
                "source": "engine"})]
        if skill == "unlock_office":
            code = str(payload.get("code") or "").replace(" ", "")
            ok = code == "4729"
            if ok:
                session["office_open"] = True
            return [make_event("system", sid, rnd, "dm", {
                "event": "office_result", "ok": ok,
                "text": ("咔哒——局长办公室门开了。桌上有策划手稿和一袋鱼干。"
                         if ok else "密码不对。金字塔：黄金→砖→泥的层数。"),
                "source": "engine"})]
        if skill == "expose_v587":
            held = set(session.get("clues_gained") or [])
            held.update(self.ec.get_player_clues(actor))
            if "clue_016" not in held and not payload.get("force"):
                return [make_event("system", sid, rnd, "dm", {
                    "event": "v587_exposed", "ok": False,
                    "text": "还没拿到访客登记表，观察笔记不肯翻开。",
                    "source": "engine"})]
            session["v587_exposed"] = True
            self.v587_exposed = True
            return [make_event("system", sid, rnd, "dm", {
                "event": "v587_exposed", "ok": True,
                "text": "V587 三层身份摊开：新用户 → 侦探爱好者联盟 → 看山的影子学徒。",
                "source": "engine"})]
        return [make_event("system", sid, rnd, "dm", {
            "event": "bad_skill", "notice": f"未知技能：{skill}"})]

    def _hotfeed_event(self, sid: str, rnd: int) -> dict:
        return make_event("hotfeed_refresh", sid, rnd, "kanshan", {
            "panel": self.of.refresh(rnd), "heat": self.of.heat,
            "signals": self.of.signal_summary(),
            "heat_ratio": self.of.heat_ratio(), "source": "engine"})

    # ------------------------------------------------------------------- vote
    def _do_vote(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid, rnd = session["session_id"], session["round"]
        evidence = payload.get("evidence") or []
        if session.get("mode") == "party":
            if not isinstance(evidence, list) or len(evidence) < 2:
                return [make_event("system", sid, rnd, "dm", {
                    "event": "vote_rejected",
                    "toast": "指认必须提交 ≥2 张证据卡",
                    "notice": "指认必须提交 ≥2 张证据卡（房间模式由引擎门控，不能空票终局）"})]
        raw = str(payload.get("target", "")).strip()
        target = "dm" if raw in ("dm", "kanshan", "npc:dm") else _norm_npc(raw)
        if target != "dm" and not any(n["id"] == target for n in self._roster):
            return [make_event("system", sid, rnd, "dm", {
                "event": "bad_target", "notice": f"投票目标不存在：{raw}"
                f"（指认 DM 请用 target=\"dm\"，且需破绽 ≥5 才有效）"})]
        self.votes[actor] = target
        # AI 席与真人同权（用户裁决 2026-09-14）：solo 模式 AI 坐席票计入终局
        # 多数决，needed = 真人数 + AI 席数，全员投齐才结算；AI 也可成为
        # 压哨触发终局的那一票。party 模式仍走 G11（AI 只跟真人多数票）。
        ai_expected = int(session.get("ai_seat_count") or 0)
        needed = max(1, len(session["players"]))
        if session.get("mode") != "party" and ai_expected > 0:
            needed += ai_expected
        if session.get("mode") != "party":
            # AI 票照常入账、同权计票、可压哨触发结算；但单人桌上 AI
            # 不应以各自启发式怀疑淹没真人的公开指证（与 party 的
            # _fill_ai_follow_votes 同语义）。无真人票时 AI 保持独立判断。
            self._solo_follow_human_votes()
        events = [make_event("vote", sid, rnd, actor, {
            "target": ("dm" if target == "dm" else f"npc:{target}"),
            "voters": len(self.votes), "needed": needed,
            "evidence": list(evidence) if isinstance(evidence, list) else [],
            "coverage": {"pct": 0},
            "source": "engine"})]
        if len(self.votes) < needed:
            return events  # 等其余席位投票
        if self.sm.stage.value != "accuse":
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "vote_pending",
                "text": "圆桌预投票已记录；终局结算将在「指认」阶段全员到齐后进行",
                "source": "engine"}))
            return events
        # G11：终局多数决。party 只把 AI 空席票写入 PartyBoard（跟真人多数），
        # 真人票只记 self.votes，避免双计或 7 个补位盖过 1 个真人。
        if session.get("mode") == "party":
            self._fill_ai_follow_votes()
        counts: dict[str, int] = {}
        # PartyBoard is canonical for party votes; self.votes may contain
        # AI follow-up votes used for replay, so exclude those here to avoid
        # counting AI seats twice when merging PartyBoard.tally().
        for voter, t in self.votes.items():
            # party 模式 AI 空席票只作回放记录（G11：以 PartyBoard 跟票为准）；
            # solo 模式 AI 席与真人同权，票票计入多数决。
            if _ai_speaker_char(voter) and session.get("mode") == "party":
                continue
            counts[t] = counts.get(t, 0) + 1
        if session.get("mode") == "party":
            try:
                for t, w in (self.pb.tally().get("counts") or {}).items():
                    counts[t] = counts.get(t, 0) + int(w)
            except Exception:
                pass
        top = max(counts.values()) if counts else 0
        leaders = sorted(t for t, w in counts.items() if w == top) if counts else []
        final_target = leaders[0] if len(leaders) == 1 else "hung"
        if final_target == "hung":
            session["status"] = "ended"
            hung_profile = truth_profile.build({
                "clue_count": len(session.get("clues_gained", [])),
                "coverage": 0,
                "pollution": self.pc.summary(),
                "refutes": self.refute_count,
                "buy_heats": self.buy_heat_count,
                "counsel_count": self.ks.clinic_settlement()["counsel_count"],
                "echo": {**self.el.summary(), "defended": self.echo_defended},
                "debate": self.jd.summary(),
                "accused_dm": False,
                "ending": "hung",
                "heat": self.of.heat,
            })
            session["profile"] = hung_profile
            return events + [make_event("ending", sid, rnd, "kanshan", {
                "accused": None, "outcome": "hung", "tally": counts,
                "title": "悬而未决",
                "desc": "票数分裂，真相随夜色搁置——平票也是一种答案。",
                "profile": hung_profile,
                "source": "engine"})]
        events.extend(self._finalize(session, final_target))
        return events

    def _grant_finale_flaws(self, session: dict, actor: str) -> tuple[list[dict], list[str]]:
        """进入指认幕即视为复盘达成：发放 auto_grant_on_boss_final / review:*。

        必须在 vote 之前调用，否则 UI 停在 4/5、「指认：DM」不亮。
        已持有则幂等，只回报 id。
        """
        self.ec.sync_context(review_flags={"credits"})
        sid, rnd = session["session_id"], session.get("round", 1)
        pid = actor if str(actor).startswith("player:") else (
            self.players[0] if self.players else "player:1")
        events: list[dict] = []
        review_clues: list[str] = []
        for clue in list(self.ec.pool.values()):
            auto_grant = clue.get("auto_grant_on_boss_final")
            is_review = str(clue.get("unlock_condition", "")).startswith("review:")
            if not (auto_grant or (auto_grant is None and is_review)):
                continue
            cid = clue["id"]
            if cid in self.ec.get_player_clues(pid):
                review_clues.append(cid)
                continue
            got = self.ec.release(cid, pid)
            if got:
                review_clues.append(got["id"])
                events.append(self._clue_event(
                    sid, rnd, pid, got, trigger="finale_review", note="终局署名破绽"))
        if events:
            events.append(make_event("system", sid, rnd, "dm", {
                "event": "flaw_progress",
                "text": f"叮——复盘署名已入卷，看山破绽 {self.ec.flaw_count()}/5",
                "flaw_count": self.ec.flaw_count()}))
            if self.ec.boss_ready():
                events.append(make_event("system", sid, rnd, "dm", {
                    "event": "boss_ready",
                    "text": "叮——5 处破绽集齐，圆桌按钮「指认：DM」已解锁",
                    "flaw_count": self.ec.flaw_count()}))
        return events, review_clues

    def _finalize(self, session: dict, target: str) -> list[dict]:
        """终局裁决：8+2 结局矩阵（resolver，确定性）。"""
        sid, rnd = session["session_id"], session["round"]
        _granted, review_clues = self._grant_finale_flaws(
            session, self.players[0] if self.players else "player:1")
        counsel_count = self.ks.clinic_settlement()["counsel_count"]
        flaw_count = self.ec.flaw_count()
        solo = (len(session.get("players", [])) == 1
                and session.get("mode") != "party")  # G06：单人保底阈值
        if target == "dm":
            res = self.rv.resolve_boss_accusation(flaw_count, counsel_count)
            matrix = self.rv.matrix_ending(
                boss_accused=True, flaw_count=flaw_count,
                counsel_count=counsel_count, solo=solo,
                pollution_heat=self.of.heat_ratio(),
                v587_exposed=bool(session.get("v587_exposed") or self.v587_exposed),
                plot_fragments=self.plot_fragments, boss_key=self.boss_key)
            accused = "dm"
        else:
            ares = self.rv.resolve_accusation(self.ec.evidence_cards(), target,
                                              self.truth, counsel_count)
            matrix = self.rv.matrix_ending(
                accusation_hit=ares["hit"], coverage=ares["coverage"],
                counsel_count=counsel_count, flaw_count=flaw_count,
                plot_fragments=self.plot_fragments, boss_key=self.boss_key,
                solo=solo, pollution_heat=self.of.heat_ratio(),
                v587_exposed=bool(session.get("v587_exposed") or self.v587_exposed))
            res = ares
            accused = f"npc:{target}"
        # S3 求真相：基于整局真实行为生成可分享画像（确定性，零 AI 参与）
        _clues = session.get("clues_gained", [])
        profile = truth_profile.build({
            "clue_count": len(_clues),
            "coverage": self.rv.truth_coverage(_clues, self.truth),
            "pollution": self.pc.summary(),
            "refutes": self.refute_count,
            "buy_heats": self.buy_heat_count,
            "counsel_count": counsel_count,
            "echo": {**self.el.summary(), "defended": self.echo_defended},
            "debate": self.jd.summary(),
            "accused_dm": target == "dm",
            "ending": matrix["ending"],
            "heat": self.of.heat,
        })
        session["profile"] = profile
        session["status"] = "ended"
        self.votes = dict(self.votes)
        return [make_event("ending", sid, rnd, "kanshan", {
            "accused": accused, "outcome": matrix["ending"],
            "title": matrix["title"], "desc": matrix["desc"],
            "detail": {**matrix["detail"],
                       "vote_result": res, "tally": dict(self.votes),
                       "review_clues": review_clues},
            "counsel_settlement": self.ks.clinic_settlement(),
            "profile": profile,
            "heat_final": self.of.heat,
            "source": "engine"})]

    def _solo_follow_human_votes(self) -> None:
        """乙裁决配套（solo 跟票）：AI 席向真人多数票看齐（覆写既有 AI 票）。

        AI 票照常入 self.votes 并计入终局多数决（同权、可压哨触发结算）；
        无真人票时 AI 保持独立判断，本方法为 no-op。语义与 party 的
        _fill_ai_follow_votes 对齐：单人桌上 AI 席被真人的公开指证说服。
        """
        human_targets = [t for v, t in self.votes.items()
                         if not _ai_speaker_char(v)]
        if not human_targets:
            return
        counts: dict[str, int] = {}
        for t in human_targets:
            counts[t] = counts.get(t, 0) + 1
        follow = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        for voter in list(self.votes):
            if _ai_speaker_char(voter):
                self.votes[voter] = follow

    def _fill_ai_follow_votes(self) -> None:
        """AI 空席跟真人多数票。只写入 PartyBoard，不改 self.votes。"""
        if not self.votes:
            return
        counts: dict[str, int] = {}
        for t in self.votes.values():
            counts[t] = counts.get(t, 0) + 1
        follow = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        for seat in self.pb.seats():
            if not seat.get("is_ai"):
                continue
            cid = seat.get("char_id")
            if cid:
                self.pb.cast_vote(f"ai:{cid}", follow)

    # ---------------------------------------------------------------- advance
    def _do_advance(self, session: dict, actor: str, payload: dict) -> list[dict]:
        sid = session["session_id"]
        demo_bypass = (payload.get("demo_bypass") is True
                       and session.get("demo_bypass") is True)
        if (session.get("mode") == "party"
                and self.sm.stage.value == "investigate"
                and not demo_bypass):
            gained = set(session.get("clues_gained") or [])
            if not (gained & PARTY_CH1_KEYS):
                return [make_event("system", sid, session.get("round", 1), "dm", {
                    "event": "advance_blocked",
                    "toast": "还差关键证物（例如「茶水间的两包泡面」）",
                    "notice": "还差关键证物才能推进指认——提示：去茶水间搜「泡面」、"
                              "前台搜「横幅」、看山工位搜「鱼干」或「请假条」均可"
                              "（2026-09-15 修正：原提示「档案室搜芯片」与实际线索不符，"
                              "曾致 party 对局卡死在搜证幕）"})]
        before = self.sm.stage
        before_act = self.sm.current_act_no()  # V4 综艺：幕切换检测（act_transition）
        events = self._maybe_settle_headline(session)  # 竞价窗口懒结算（截止即拍）
        if self._linear_acts:
            # D 内容为独立幕结构（break_ice/investigate/round_table/accuse）：
            # advance = 幕线性推进（round_table 幕内直接 vote），引擎 advance() 幂等保护末幕
            self.sm.advance()
        elif before in (stage_machine.Stage.INVESTIGATE,
                        stage_machine.Stage.ROUND_TABLE):
            self.sm.end_round()          # rounds_per_act 幕内轮循环（B 引擎语义）
        else:
            self.sm.advance()
        after = self.sm.stage
        if self._headline_window is not None and after != before:
            # 幕/阶段切换：未决竞价窗口强制结算（契约：幕结束强制清算）
            events.extend(self._settle_headline_window(session, reason="act_end"))
        if after != before:
            if after == stage_machine.Stage.INVESTIGATE:
                session["round"] = session.get("round", 1) + 1
                # P1-5 新手引导：首次进入搜证幕的 30 秒玩法卡（确定性播报）
                if not session.get("tutorial_done"):
                    session["tutorial_done"] = True
                    self.sm.push_event(
                        "叮——新手调查员须知：①场景图选地点+输关键词=搜证(1AP)；"
                        "②搜证附带抽知识卡；③行动点每轮 3 点，轮末圆桌对质。"
                        "详见图鉴-玩法说明。", kind="tutorial")
                    self.sm.push_event(
                        "叮——第二幕起解锁记忆修复与知识开导；第三幕解锁热搜舆论。"
                        "破冰期请先和大家聊聊。", kind="tutorial")
                # V31 轮次注入：急诊红灯有效期 + party 全员 AP 重置（每轮 3）
                self.ks.set_round(session["round"])
                self.pb.reset_round_ap()
                self.sm.push_event(
                    f"叮——第 {session['round']} 轮搜证开始，"
                    f"剩余行动点 {self.sm.actions_left}", kind="round_start")
            elif after != before and before is not None:
                # 幕结算：动态难度梯度（DifficultyDirector 确定性规则，assist/normal/hard）
                clues = session.get("clues_gained", [])
                metrics = {"clue_count": len(clues),
                           "coverage": self.rv.truth_coverage(clues, self.truth),
                           "stuck_rounds": 0}
                grade = self.dd.on_act_settled(metrics)
                self.dd.apply(self.ec, self.of)
                events.append(make_event("system", sid, session.get("round", 1), "dm", {
                    "event": "difficulty_set", "gradient": grade["gradient"],
                    "suggest_limit": grade.get("suggest_limit"),
                    "text": "叮——下一幕线索发放梯度已调整（档案局标准流程）",
                    "source": "engine"}))
            events.append(make_event("system", sid, session["round"], "dm", {
                "event": "stage_changed", "stage": after.value,
                "stage_name": STAGE_NAMES.get(after.value, after.value),
                "actions_left": self.sm.actions_left,
                "actSet": {"break_ice": 1, "investigate": 1,
                           "round_table": 2, "accuse": 3}.get(after.value, 1),
                "source": "engine"}))
            if after == stage_machine.Stage.ACCUSE:
                grant_ev, _ = self._grant_finale_flaws(session, actor)
                events.extend(grant_ev)
            # 热搜竞价窗口：进入热搜战阶段（圆桌/指认）即开启 headline_open（同 round 幂等）
            if after in (stage_machine.Stage.ROUND_TABLE,
                         stage_machine.Stage.ACCUSE):
                open_ev = self._open_headline_window(session, reason="进入热搜战阶段")
                if open_ev:
                    events.append(open_ev)
            events.append(self._hotfeed_event(sid, session["round"]))
            # V4 综艺：幕切换转场（act_transition，确定性幕序/引言/转场图）
            after_act = self.sm.current_act_no()
            if after_act != before_act:
                act = (self.scenario.get("acts", [])[after_act - 1]
                       if 0 < after_act <= len(self.scenario.get("acts", [])) else {})
                events.append(make_event("system", sid, session["round"], "dm", {
                    "event": "act_transition", "act_no": after_act,
                    "act_name": act.get("name", ""),
                    "act_brief": act.get("brief", ""),
                    "transition_image": f"/assets/images/act_t{min(after_act, 3)}.png",
                    "stage": after.value,
                    "source": "engine"}))
            # V4 综艺 §一⑥：圆桌幕结束时邀请第一次非正式投票（不影响结局，喂弹幕梗）
            if (before == stage_machine.Stage.ROUND_TABLE
                    and after != before and not self._first_vote_sent):
                self._first_vote_sent = True
                events.append(make_event("system", sid, session["round"], "dm", {
                    "event": "first_vote", "kind": "informal", "binding": False,
                    "poll_id": f"first_vote_{sid}",
                    "targets": [f"npc:{n['id']}" for n in self._roster],
                    "text": "圆桌讨论到此为止——第一次非正式指认：举手表决你"
                            "最怀疑的人（不影响结局，弹幕见真章）",
                    "source": "engine"}))
        else:
            hint = ("已是终局投票阶段：完成指认（vote）即结算结局"
                    if after == stage_machine.Stage.ACCUSE else "阶段无 further 推进")
            events.append(make_event("system", sid, session["round"], "dm", {
                "event": "advance_noop", "stage": after.value,
                "text": f"叮——{hint}", "source": "engine"}))
        for ev in self.sm.system_events():
            ev["session_id"] = sid
            ev["round"] = session["round"]
            events.append(ev)
        rnd_now = int(session.get("round") or 1)
        if rnd_now == 2 and 2 not in self._radio_sent_rounds:
            self._radio_sent_rounds.add(2)
            events.append(make_event("system", sid, rnd_now, "dm", {
                "event": "radio_broadcast", "text": self._radio_text(session, False),
                "request": False, "source": "engine"}))
        return events
