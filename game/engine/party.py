"""party — 房间级多人同场引擎（阵营分配器 + AP/投票聚合）

契约：docs/CONTRACTS.md v2.1（mode=party）；设计：docs/MEGA_MODE.md §二、docs/GAMEPLAY_V31.md B.1。
职责（确定性裁决，禁止 AI 参与）：
- 阵营分配器：1-5 真人动态配比（污染配额 ≤3 人局=2 / 4-5 人局=3），暗置发牌，
  至少 1 名「被裹挟者」（swayable 角色优先）可策反；
- 席位管理：真人入座（每人扮一个角色）、掉线 AI 无缝接管标记（口风由一致性守卫保证）；
- 多人 AP：行动点各算各的（每轮 3 点/人），AI 席位同池；
- 投票聚合：真人 + AI（ai:char_xx）+ 弹幕（danmaku）统一加权计票，平票显式返回；
- 终局陈词轮：陈词登记 + 弹幕实时「最想锤的人」投票（不影响指认，影响群嘲结局与成就）。

实现归 B 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

import random

# 每轮每人行动点（V3 §3.2；多人各算各的，MEGA_MODE §二）
AP_PER_ROUND = 3


class PartyBoard:
    def __init__(self, char_factions: dict[str, str] | None = None,
                 seed: int | None = None) -> None:
        """char_factions: {char_id: 角色卡预设 faction(truth|pollution|swayable)}，
        仅用于「被裹挟者」优先选择；阵营本身由 assign_factions 动态暗置发牌。"""
        self._char_factions = dict(char_factions or {})
        self._rng = random.Random(seed)
        self._seats: dict[str, dict] = {}        # player_id -> {char_id, connected}
        self._char_owner: dict[str, str] = {}    # char_id -> player_id（""=AI 补位）
        self._factions: dict[str, str] = {}      # char_id -> truth|pollution
        self._coerced: str | None = None         # 被裹挟者（可策反）
        self._ap: dict[str, int] = {}            # actor(player_id 或 ai:char_id) -> AP
        self._votes: list[dict] = []             # {voter, target, weight}
        self._statements: list[dict] = []        # 终局陈词
        self._hammer_votes: list[dict] = []      # 「最想锤的人」
        # V1 vertical slice: per-character three-layer goals and joy economy.
        self._goals: dict[str, dict] = {}
        self._joy: dict[str, int] = {}
        self._skills_used: list[dict] = []

    # ------------------------------------------------------------- 阵营分配
    def assign_factions(self, reshuffle: bool = False) -> dict:
        """1-5 人动态配比暗置发牌：污染配额 ≤3 人局=2 / 4-5 人局=3；
        swayable 角色分入污染时优先成为「被裹挟者」，否则指定污染首位。
        幂等：已分配且未要求 reshuffle 时直接返回现状。"""
        if self._factions and not reshuffle:
            return self.result()
        chars = sorted(self._char_factions) or [f"char_{i:02d}" for i in range(1, 9)]
        n_players = len([s for s in self._seats if s.startswith("player:")])
        quota = 2 if n_players <= 3 else 3
        quota = min(quota, len(chars) - 1)  # 至少留 1 名求真
        shuffled = chars[:]
        self._rng.shuffle(shuffled)
        pollution = shuffled[:quota]
        truth = shuffled[quota:]
        # 被裹挟者：swayable 优先
        coerced = next((c for c in pollution if self._char_factions.get(c) == "swayable"),
                       pollution[0] if pollution else None)
        self._factions = {c: ("pollution" if c in pollution else "truth") for c in chars}
        self._coerced = coerced
        return self.result()

    def result(self) -> dict:
        return {"factions": dict(self._factions), "coerced": self._coerced,
                "pollution": sorted(c for c, f in self._factions.items() if f == "pollution"),
                "truth": sorted(c for c, f in self._factions.items() if f == "truth"),
                "players": len([s for s in self._seats if s.startswith("player:")]),
                "joy": dict(self._joy), "goals": {k: dict(v) for k, v in self._goals.items()}}

    def configure_goals(self, goals: dict[str, dict] | None = None) -> dict:
        """配置角色三层目标（faction/personal/fun），缺省自动生成可玩目标。"""
        for cid in self._char_factions:
            g = dict((goals or {}).get(cid, {}))
            faction = self._factions.get(cid, self._char_factions.get(cid, "swayable"))
            g.setdefault("faction", "推动污染值达到阈值" if faction == "pollution" else "收集证据并还原真相")
            g.setdefault("personal", f"完成{cid}的秘密委托")
            g.setdefault("fun", "制造一次全桌爆笑事件")
            self._goals[cid] = g
            self._joy.setdefault(cid, 0)
        return {k: dict(v) for k, v in self._goals.items()}

    def add_joy(self, actor: str, amount: int = 1, reason: str = "") -> dict:
        """欢乐值（独立于 AP/热度），用于技能与复盘称号。"""
        cid = self.char_of(actor) or actor
        self._joy[cid] = max(0, min(10, self._joy.get(cid, 0) + int(amount)))
        return {"actor": actor, "char_id": cid, "joy": self._joy[cid], "delta": int(amount), "reason": reason}

    def joy_state(self) -> dict:
        return dict(self._joy)

    def use_skill(self, actor: str, skill: str, target: str | None = None) -> dict:
        """确定性阵营技能：污染伪证/热搜，求真质询/交叉验证。"""
        faction = self.faction_of(actor)
        allowed = {
            "pollution": {"plant_fake", "buy_hotsearch", "delay_clue"},
            "truth": {"cross_check", "public_question", "repair_memory"},
        }.get(faction, {"public_question"})
        if skill not in allowed:
            return {"ok": False, "reason": "skill_not_allowed", "faction": faction, "skill": skill}
        if not self.spend(actor, 1):
            return {"ok": False, "reason": "no_ap"}
        joy = self.add_joy(actor, 1, skill)
        rec = {"actor": actor, "skill": skill, "target": target, "faction": faction}
        self._skills_used.append(rec)
        return {"ok": True, **rec, "joy": joy["joy"], "ap": self.ensure_ap(actor)}

    def faction_of(self, actor: str) -> str | None:
        """actor: player_id 或 ai:char_id → 其扮演角色阵营（仅引擎/裁决可查，前端不透出）。"""
        char = self.char_of(actor)
        return self._factions.get(char) if char else None

    def char_of(self, actor: str) -> str | None:
        seat = self._seats.get(actor)
        if seat:
            return seat["char_id"]
        if actor.startswith("ai:"):
            return actor[3:]
        return None

    # ------------------------------------------------------------- 席位管理
    def join(self, player_id: str, char_id: str | None = None) -> dict:
        """真人入座：可指定角色（须为空位/AI 席），否则自动分配空位。"""
        existing = self._seats.get(player_id)
        if existing and existing.get("char_id"):
            if not char_id or char_id == existing["char_id"]:
                existing["connected"] = True
                existing["ai_takeover"] = False
                return {"ok": True, "player_id": player_id,
                        "char_id": existing["char_id"],
                        "seats": self.seats(), "rejoin": True}
            old_cid = existing["char_id"]
            if self._char_owner.get(old_cid) == player_id:
                del self._char_owner[old_cid]
        taken = set(self._char_owner)
        if char_id:
            owner = self._char_owner.get(char_id, "")
            if owner and owner != player_id and self._seats.get(owner, {}).get("connected"):
                return {"ok": False, "reason": "seat_taken", "char_id": char_id}
        else:
            char_id = next((c for c in sorted(self._char_factions) if c not in taken), None)
            if not char_id:
                return {"ok": False, "reason": "room_full"}
        # 顶替 AI 席或重连
        old = self._char_owner.get(char_id)
        if old and old != player_id:
            self._seats.pop(old, None)
        self._seats[player_id] = {"char_id": char_id, "connected": True}
        self._char_owner[char_id] = player_id
        self._ap.setdefault(player_id, AP_PER_ROUND)
        return {"ok": True, "player_id": player_id, "char_id": char_id,
                "seats": self.seats()}

    def leave(self, player_id: str) -> dict:
        """掉线：席位保留、AI 无缝接管标记（口风由一致性守卫保证，MEGA_MODE §二）。"""
        seat = self._seats.get(player_id)
        if not seat:
            return {"ok": False, "reason": "no_seat"}
        seat["connected"] = False
        seat["ai_takeover"] = True
        return {"ok": True, "player_id": player_id, "char_id": seat["char_id"],
                "ai_takeover": True}

    def seats(self) -> list[dict]:
        out = []
        for char_id in sorted(self._char_factions) or sorted(self._char_owner):
            owner = self._char_owner.get(char_id, "")
            seat = self._seats.get(owner, {})
            out.append({"char_id": char_id, "player_id": owner or None,
                        "connected": seat.get("connected", False),
                        "ai_takeover": seat.get("ai_takeover", False),
                        "is_ai": not owner or not seat.get("connected", False)})
        return out

    # ------------------------------------------------------------- 多人 AP
    def reset_round_ap(self, ap: int = AP_PER_ROUND) -> dict:
        """新轮：所有人（含 AI 席）行动点重置。"""
        for actor in {self._char_owner.get(c) or f"ai:{c}" for c in self._char_factions}:
            self._ap[actor] = ap
        return {k: self._ap.get(k, 0) for k in sorted(self._ap)}

    def ensure_ap(self, actor: str, ap: int | None = None) -> int:
        """后补席 / 未知 actor：不在 _ap 时写入 AP_PER_ROUND（或传入值），返回当前点数。"""
        if actor not in self._ap:
            self._ap[actor] = AP_PER_ROUND if ap is None else ap
        return self._ap[actor]

    def spend(self, actor: str, n: int = 1) -> bool:
        """扣行动力（各算各的）；未知 actor 先 ensure_ap 再扣；不足返回 False。"""
        cur = self.ensure_ap(actor)
        if cur < n:
            return False
        self._ap[actor] = cur - n
        return True

    def refund(self, actor: str, n: int = 1) -> None:
        self._ap[actor] = self._ap.get(actor, 0) + n

    def ap_state(self) -> dict:
        return {k: v for k, v in sorted(self._ap.items())}

    # ------------------------------------------------------------- 投票聚合
    def cast_vote(self, voter: str, target: str, weight: int = 1) -> dict:
        """登记一票。voter: player:* / ai:char_xx / danmaku:xxx（弹幕低权重由调用方传）。
        一人一票：重复投票覆盖原票。"""
        self._votes = [v for v in self._votes if v["voter"] != voter]
        self._votes.append({"voter": voter, "target": target, "weight": weight})
        return {"ok": True, "voter": voter, "target": target,
                "votes_in": len(self._votes)}

    def tally(self) -> dict:
        """真人+AI+弹幕聚合。返回 {counts: {target: weight}, total, leader, tie}。
        平票时 leader=None、tie=[并列目标]。"""
        counts: dict[str, int] = {}
        for v in self._votes:
            counts[v["target"]] = counts.get(v["target"], 0) + v["weight"]
        if not counts:
            return {"counts": {}, "total": 0, "leader": None, "tie": []}
        top = max(counts.values())
        leaders = sorted(t for t, w in counts.items() if w == top)
        return {"counts": counts, "total": sum(counts.values()),
                "leader": leaders[0] if len(leaders) == 1 else None,
                "tie": leaders if len(leaders) > 1 else []}

    # ------------------------------------------------------------- 终局陈词轮
    def final_statement(self, speaker: str, text: str) -> dict:
        """投票前最后陈词登记（每人一条，重复提交覆盖；不影响指认——只进复盘/成就）。"""
        self._statements = [s for s in self._statements if s["speaker"] != speaker]
        self._statements.append({"speaker": speaker, "text": text})
        return {"ok": True, "speaker": speaker, "statements": len(self._statements)}

    def hammer_vote(self, voter: str, target: str, weight: int = 1) -> dict:
        """弹幕实时投票「最想锤的人」（与指认投票分池，不影响结局档位）。"""
        self._hammer_votes = [v for v in self._hammer_votes if v["voter"] != voter]
        self._hammer_votes.append({"voter": voter, "target": target, "weight": weight})
        return {"ok": True, "hammer_votes_in": len(self._hammer_votes)}

    def hammer_result(self) -> dict:
        """「最想锤的人」结果 + 陈词回放（群嘲结局与成就素材，C 组消费）。"""
        counts: dict[str, int] = {}
        for v in self._hammer_votes:
            counts[v["target"]] = counts.get(v["target"], 0) + v["weight"]
        top = max(counts.values()) if counts else 0
        most = sorted(t for t, w in counts.items() if w == top) if counts else []
        return {"most_hammered": most[0] if len(most) == 1 else None,
                "tie": most if len(most) > 1 else [],
                "counts": counts,
                "statements": list(self._statements)}

    def three_endings(self, *, truth_score: float = 0.0, pollution_score: float = 0.0,
                      accused_correct: bool = False) -> dict:
        """首局三主结局裁决：真相公开/污染成功/档案局失控。旧结局键保持独立。"""
        joy = sum(self._joy.values())
        if pollution_score >= 0.7 and pollution_score > truth_score:
            key, title = "pollution_win", "热搜污染成功"
        elif accused_correct and truth_score >= 0.6:
            key, title = "truth_revealed", "真相公开"
        else:
            key, title = "archive_meltdown", "档案局失控"
        return {"ending": key, "title": title, "joy": joy,
                "faction_score": {"truth": truth_score, "pollution": pollution_score}}

    # ------------------------------------------ F 联调增量（on-call 2026-09-12）
    @classmethod
    def from_roster(cls, roster: list[dict], seed: int | None = None) -> "PartyBoard":
        """从角色卡列表一行构造（F 的 EngineDriver._load_roster() 输出即 roster）。

        roster: [{"id": "char_01", "name": ..., "faction": "truth|pollution|swayable"}, ...]
        """
        return cls({str(r.get("id")): str(r.get("faction", "swayable"))
                    for r in roster or []}, seed=seed)

    def snapshot(self) -> dict:
        """可序列化快照（F 的 session_store 持久化 / 服务重启确定性回放必需）。

        含发牌结果、座位（含掉线接管标记）、各自 AP、全部票池与陈词。
        """
        return {"assigned": bool(self._factions),
                "factions": dict(self._factions), "coerced": self._coerced,
                "seats": {pid: dict(seat) for pid, seat in self._seats.items()},
                "char_owner": dict(self._char_owner),
                "ap": dict(self._ap),
                "votes": [dict(v) for v in self._votes],
                "hammer_votes": [dict(v) for v in self._hammer_votes],
                "statements": [dict(s) for s in self._statements],
                "goals": {k: dict(v) for k, v in self._goals.items()}, "joy": dict(self._joy),
                "skills_used": [dict(s) for s in self._skills_used]}

    def restore(self, snap: dict) -> None:
        """从 snapshot() 恢复（与 seed 重放配合：先 restore 再按 actions 回放）。"""
        if not snap:
            return
        self._factions = dict(snap.get("factions", {}))
        self._coerced = snap.get("coerced")
        self._seats = {pid: dict(seat) for pid, seat in snap.get("seats", {}).items()}
        self._char_owner = dict(snap.get("char_owner", {}))
        self._ap = dict(snap.get("ap", {}))
        self._votes = [dict(v) for v in snap.get("votes", [])]
        self._hammer_votes = [dict(v) for v in snap.get("hammer_votes", [])]
        self._statements = [dict(s) for s in snap.get("statements", [])]
        self._goals = {k: dict(v) for k, v in snap.get("goals", {}).items()}
        self._joy = {k: int(v) for k, v in snap.get("joy", {}).items()}
        self._skills_used = [dict(s) for s in snap.get("skills_used", [])]
