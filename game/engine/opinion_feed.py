"""opinion_feed — 舆论场引擎（热搜/热度值/水军/辟谣）

契约：docs/CONTRACTS.md §3.5；设计：docs/GAME_DESIGN_V3.md 第三幕「热搜疑云」。
职责（确定性裁决，禁止 AI 参与）：
- 每轮刷新热搜面板（预生成帖池按 round 抽取）；
- 热度值系统：热度越高真线索越难解锁；
- 污染阵营技能：买热搜（置顶假线索）/ 水军控评（淹没真线索）；
- 求真阵营技能：官方辟谣 = 2AP + 知识卡 topic_tag 匹配帖 topic_tag 才生效，
  不匹配 → 辟谣失败反涨热度（群嘲演出由 Agent 层渲染）。

实现归 B 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

import json
from pathlib import Path

# 热度阈值：达到后真线索被水军声量淹没（clues_blocked_by_heat 生效）
HEAT_BLOCK_THRESHOLD = 80
HEAT_MAX = 100
HEAT_INIT = 40

# 辟谣失败群嘲文案（设计文档原句 + 欢乐补充，Agent 层可直接渲染）
MOCK_LINES = [
    "没知识还硬辟谣",
    "建议先读两篇知乎再来辟谣",
    "这不是辟谣，这是谣言二创",
]


class OpinionFeed:
    def __init__(self) -> None:
        self._posts: dict[str, dict] = {}       # post_id -> post（hot_post schema）
        self._heat = HEAT_INIT
        self._pinned: set[str] = set()          # 买热搜置顶的假帖
        self._refuted: set[str] = set()         # 已被成功辟谣的帖
        self._unlocked_clues: set[str] = set()  # 辟谣解锁的真线索 id
        self._shown: set[str] = set()           # 已上过面板的帖
        self._knowledge_lookup = None           # callable(card_id) -> topic_tag | None
        self._bets: dict[str, dict] = {}        # 弹幕押注池 bet_id -> {subject, options, wagers}
        self._threshold_delta = 0               # 动态难度热度阈值微调（DifficultyDirector）
        self._headline: dict | None = None      # 头条竞标局 {round, bids}
        self._headline_winner: dict | None = None
        self._refute_streak = 0                 # 连续辟谣成功次数（成就：热搜质检员）
        self._flooded_clues: set[str] = set()   # 控评淹没的真线索（不依赖热度阈值）

    # ----------------------------------------------------------- 知识卡对接
    def attach_knowledge(self, lookup) -> None:
        """注入知识卡查询：lookup(card_id) -> topic_tag | None。

        可传 KnowledgeSystem（自带 refute_allowed 之外的只读接口）或任意 callable。
        """
        self._knowledge_lookup = lookup

    def _card_topic(self, card_id: str) -> str | None:
        if self._knowledge_lookup is None:
            return None
        try:
            return self._knowledge_lookup(card_id)
        except Exception:
            return None

    # ------------------------------------------------------------------ load
    def load(self, scenario_dir: str) -> None:
        """加载 content/scenarios/kanshan/hotfeed/ 帖池。

        容错：目录不存在或为空时静默空载（内容组未交付不阻塞引擎单测）。
        """
        hf_dir = Path(scenario_dir) / "hotfeed"
        self._posts = {}
        if not hf_dir.is_dir():
            return
        for f in sorted(hf_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict) and data.get("id"):
                self._posts[data["id"]] = data
            elif isinstance(data, list):
                for p in data:
                    if isinstance(p, dict) and p.get("id"):
                        self._posts[p["id"]] = p

    # --------------------------------------------------------------- refresh
    def refresh(self, round_no: int) -> list[dict]:
        """本轮热搜面板（6-8 条帖，含水军帖）。

        确定性规则：优先取 round 字段匹配本轮的帖（按 id 排序，至多 8 条），
        不足 6 条时从未展示过的其余帖按 id 补齐；买热搜帖强制置顶。
        """
        matched = sorted([p for p in self._posts.values() if int(p.get("round", 0)) == round_no],
                         key=lambda p: p["id"])
        panel = matched[:8]
        if len(panel) < 6:
            rest = sorted([p for p in self._posts.values()
                           if p["id"] not in {q["id"] for q in panel}
                           and p["id"] not in self._shown],
                          key=lambda p: p["id"])
            panel = panel + rest[: 6 - len(panel)]
        for p in panel:
            self._shown.add(p["id"])
        # 置顶买热搜帖
        pinned = [p for p in self._posts.values() if p["id"] in self._pinned]
        result = [self._display(p) for p in pinned if p["id"] not in {q["id"] for q in panel}]
        result += [self._display(p) for p in panel]
        return result

    def _display(self, post: dict) -> dict:
        d = dict(post)
        d["_pinned"] = post["id"] in self._pinned
        d["_refuted"] = post["id"] in self._refuted
        # 三维舆论指标：兼容旧 heat 字段，同时让玩家知道“热”不等于“真”。
        base = max(0, min(100, int(post.get("heat_delta", 5)) * 4 + 40))
        d["signals"] = {
            "exposure": min(100, base + (20 if d["_pinned"] else 0)),
            "credibility": 0 if d["_refuted"] else None,
            "emotion": min(100, 45 + (10 if d["_pinned"] else 0)),
        }
        return d

    def signal_summary(self) -> dict:
        """返回当前曝光/可信度/情绪三维状态，旧客户端可继续只读 heat。"""
        fake = len(self._pinned)
        refuted = len(self._refuted)
        return {"exposure": min(100, self._heat + fake * 3),
                "credibility": max(0, min(100, 60 + refuted * 5 - fake * 4)),
                "emotion": max(0, min(100, 40 + self._heat // 3 + fake * 4))}

    # ------------------------------------------------------------------ heat
    @property
    def heat(self) -> int:
        """当前热度值（0-100）。"""
        return self._heat

    def _add_heat(self, delta: int) -> int:
        self._heat = max(0, min(HEAT_MAX, self._heat + int(delta)))
        return self._heat

    def apply_heat(self, delta: int) -> int:
        """外部模块（污染对照等）调整热度的公开入口，避免越界访问私有方法。"""
        return self._add_heat(delta)

    # -------------------------------------------------------------- buy_heat
    def buy_heat(self, actor: str, post_id: str) -> dict:
        """污染阵营买热搜：置顶假线索（扣行动力由 resolver 校验）。

        只能置顶 is_fake=True 的水军帖；返回 {ok, post_id, heat, heat_delta, reason}。
        """
        post = self._posts.get(post_id)
        if not post:
            return {"ok": False, "post_id": post_id, "heat": self._heat,
                    "heat_delta": 0, "reason": "post_not_found"}
        if not post.get("is_fake"):
            return {"ok": False, "post_id": post_id, "heat": self._heat,
                    "heat_delta": 0, "reason": "not_fake_post"}
        self._pinned.add(post_id)
        delta = int(post.get("heat_delta", 5))
        heat = self._add_heat(delta)
        return {"ok": True, "post_id": post_id, "heat": heat, "heat_delta": delta,
                "reason": "pinned", "title": post.get("title", "")}

    def flood_comments(self, actor: str, post_id: str) -> dict:
        """污染阵营「水军控评」：帖必须存在；热度 +6；带 clue_ref 且未辟谣则记入淹没。"""
        _ = actor
        post = self._posts.get(post_id)
        if not post:
            return {"ok": False, "post_id": post_id, "heat": self._heat,
                    "heat_delta": 0, "reason": "post_not_found"}
        heat = self._add_heat(6)
        clue = post.get("clue_ref")
        if clue and post_id not in self._refuted:
            self._flooded_clues.add(str(clue))
        return {"ok": True, "post_id": post_id, "heat": heat, "heat_delta": 6,
                "reason": "flooded", "title": post.get("title", "")}

    def report_spam(self, actor: str, post_id: str, evidence_n: int = 0) -> dict:
        """求真阵营「举报水军」：帖必须 is_fake；evidence_n>=1 才成功，热度 -4 并标已辟谣。"""
        _ = actor
        post = self._posts.get(post_id)
        if not post:
            return {"ok": False, "post_id": post_id, "heat": self._heat,
                    "heat_delta": 0, "reason": "post_not_found"}
        if not post.get("is_fake"):
            return {"ok": False, "post_id": post_id, "heat": self._heat,
                    "heat_delta": 0, "reason": "not_fake"}
        if int(evidence_n or 0) < 1:
            return {"ok": False, "post_id": post_id, "heat": self._heat,
                    "heat_delta": 0, "reason": "need_evidence"}
        heat = self._add_heat(-4)
        self._refuted.add(post_id)
        clue = post.get("clue_ref")
        if clue:
            self._flooded_clues.discard(str(clue))
        return {"ok": True, "post_id": post_id, "heat": heat, "heat_delta": -4,
                "reason": "reported", "title": post.get("title", "")}

    # ---------------------------------------------------------------- refute
    def refute(self, actor: str, post_id: str, knowledge_card_id: str) -> dict:
        """官方辟谣：卡 topic_tag 匹配 → 降热度+解锁真线索；否则反涨。

        返回 {ok, heat_delta, unlocked_clue, crowd_mocks: list[str]}。
        """
        post = self._posts.get(post_id)
        if not post:
            return {"ok": False, "heat_delta": 0, "unlocked_clue": None,
                    "crowd_mocks": [], "reason": "post_not_found"}
        post_tag = str(post.get("topic_tag", ""))
        card_tag = self._card_topic(knowledge_card_id)
        matched = card_tag is not None and card_tag.strip() == post_tag.strip()
        if not matched:
            # 辟谣失败：热搜反涨（群嘲弹幕由 Agent 层渲染）
            self._refute_streak = 0
            delta = int(post.get("heat_delta", 5))
            heat = self._add_heat(delta)
            return {"ok": False, "heat_delta": delta, "unlocked_clue": None,
                    "crowd_mocks": list(MOCK_LINES), "heat": heat,
                    "reason": "tag_mismatch", "card_tag": card_tag, "post_tag": post_tag}
        # 辟谣成功：降热度、标记已辟谣、解锁帖内真线索
        self._refute_streak += 1
        delta = -int(post.get("heat_delta", 5))
        heat = self._add_heat(delta)
        self._refuted.add(post_id)
        clue = post.get("clue_ref")
        if clue:
            self._unlocked_clues.add(clue)
        return {"ok": True, "heat_delta": delta, "unlocked_clue": clue,
                "crowd_mocks": [], "heat": heat, "reason": "refuted",
                "title": post.get("title", "")}

    # --------------------------------------------------------------- blocked
    def clues_blocked_by_heat(self) -> list[str]:
        """当前被高热度淹没的真线索 id 列表。

        阈值 = HEAT_BLOCK_THRESHOLD + 动态难度微调（assist +10 更难淹没 / hard -10 更易淹没）；
        命中阈值的帖池中带 clue_ref 的真帖（未辟谣、线索未解锁）对应真线索被淹没。
        """
        blocked: list[str] = []
        if self._heat >= HEAT_BLOCK_THRESHOLD + self._threshold_delta:
            for p in sorted(self._posts.values(), key=lambda x: x["id"]):
                clue = p.get("clue_ref")
                if clue and clue not in self._unlocked_clues and p["id"] not in self._refuted:
                    blocked.append(clue)
        for clue in sorted(self._flooded_clues):
            if clue not in blocked and clue not in self._unlocked_clues:
                blocked.append(clue)
        return blocked

    def set_threshold_delta(self, delta: int) -> None:
        """动态难度热度阈值微调（assist +10 / hard -10，DifficultyDirector.apply 调用）。"""
        self._threshold_delta = int(delta)

    def refute_streak(self) -> int:
        """当前连续辟谣成功次数（成就：热搜质检员 ≥3 且全程零失败）。"""
        return self._refute_streak

    # --------------------------------------------- P1 弹幕押注（欢乐结算件）
    def open_bet(self, bet_id: str, subject: str, options: list[str],
                 round_no: int = 0) -> dict:
        """开押注池：弹幕（可含玩家）对某议题下注（如「这轮谁能搜到猛料」）。

        amount 单位=赞数（欢乐值）；settle 时按池比例赔付并小幅加热话题。
        """
        if not options or len(options) < 2:
            return {"ok": False, "reason": "need_2_options"}
        self._bets[bet_id] = {"subject": subject, "options": list(options),
                              "round": round_no, "wagers": [], "settled": False}
        return {"ok": True, "bet_id": bet_id, "subject": subject, "options": list(options)}

    def place_bet(self, bet_id: str, bettor: str, option: str, amount: int = 1) -> dict:
        """下注：bettor 如 danmaku:热评君 / player:1；同一 bettor 可追加（累计）。"""
        bet = self._bets.get(bet_id)
        if not bet or bet["settled"]:
            return {"ok": False, "reason": "bet_not_open"}
        if option not in bet["options"]:
            return {"ok": False, "reason": "unknown_option"}
        bet["wagers"].append({"bettor": bettor, "option": option, "amount": max(1, int(amount))})
        return {"ok": True, "bet_id": bet_id, "pool": sum(w["amount"] for w in bet["wagers"])}

    def settle_bet(self, bet_id: str, winning_option: str) -> dict:
        """押注结算：按注池比例赔付（单位=赞数）；话题小幅加热（押注人数越多越热）。"""
        bet = self._bets.get(bet_id)
        if not bet or bet["settled"]:
            return {"ok": False, "reason": "bet_not_open"}
        if winning_option not in bet["options"]:
            return {"ok": False, "reason": "unknown_option"}
        pool = sum(w["amount"] for w in bet["wagers"])
        win_pool = sum(w["amount"] for w in bet["wagers"] if w["option"] == winning_option)
        winners = []
        for w in bet["wagers"]:
            if w["option"] == winning_option and win_pool:
                winners.append({"bettor": w["bettor"],
                                "payout": int(w["amount"] * pool / win_pool)})
        bet["settled"] = True
        heat = self._add_heat(min(5, max(1, len(bet["wagers"]) // 2)))
        return {"ok": True, "bet_id": bet_id, "winning_option": winning_option,
                "pool": pool, "winners": winners, "heat": heat,
                "subject": bet["subject"]}

    # --------------------------------------------- P1 头条竞标（明牌博弈）
    def open_headline_bidding(self, round_no: int) -> dict:
        """每轮一个「头条位」阵营竞标开局（花行动点，扣点由上层校验）。"""
        self._headline = {"round": round_no, "bids": []}
        self._headline_winner = None
        return {"ok": True, "round": round_no, "note": "头条位竞标开始：出价=行动点，阵营身份明牌"}

    def bid_headline(self, actor: str, faction: str, amount: int,
                     post_id: str | None = None) -> dict:
        """出价：amount=愿付行动点；faction 明牌（truth|pollution）；可指定登头条的帖。"""
        if not self._headline:
            return {"ok": False, "reason": "bidding_not_open"}
        if faction not in ("truth", "pollution"):
            return {"ok": False, "reason": "bad_faction"}
        amount = max(0, int(amount))
        self._headline["bids"] = [b for b in self._headline["bids"] if b["actor"] != actor]
        if amount > 0:
            self._headline["bids"].append({"actor": actor, "faction": faction,
                                           "amount": amount, "post_id": post_id})
        return {"ok": True, "bids": len(self._headline["bids"])}

    def settle_headline(self) -> dict:
        """竞标结算：最高价阵营获头条位——其帖置顶且 heat_delta 翻倍（买热搜变明牌博弈）；
        平价先到先得；无人出价流拍（热度小涨：头条位空转的节目效果）。"""
        if not self._headline:
            return {"ok": False, "reason": "bidding_not_open"}
        bids = self._headline["bids"]
        if not bids:
            self._headline = None
            heat = self._add_heat(2)
            return {"ok": True, "winner": None, "heat": heat,
                    "note": "流拍：头条位空转，水军狂欢 2 点热度"}
        top = max(b["amount"] for b in bids)
        win = next(b for b in bids if b["amount"] == top)  # 平价先到先得
        self._headline_winner = win
        post_id = win.get("post_id")
        heat = self._heat
        if post_id and post_id in self._posts:
            self._pinned.add(post_id)
            delta = int(self._posts[post_id].get("heat_delta", 5))  # 翻倍加成
            heat = self._add_heat(delta)
        self._headline = None
        return {"ok": True, "winner": win["actor"], "faction": win["faction"],
                "amount": win["amount"], "post_id": post_id, "heat": heat,
                "note": "头条话题可信度权重上升；竞标阵营身份已公开"}

    # ---------------------------------------------------------------- extras
    def heat_ratio(self) -> float:
        """热度带偏程度（0.0-1.0，供 resolver 污染胜利判定）。"""
        return round(self._heat / HEAT_MAX, 2)

    def unlocked_clues(self) -> list[str]:
        """辟谣已解锁的真线索 id 列表。"""
        return sorted(self._unlocked_clues)
