"""证据链系统：线索发放、持有、关联与矛盾检测。

线索卡 schema 见 content/scenarios/template/clues/clue_001.json（旧）与
docs/CONTRACTS.md §3.3（新：tier/location/tags/fact/linked_truth_nodes/unlock_condition）。
核心职责：确保 AI 永远不能凭空发放线索；线索只能来自线索池。

V3 升级（docs/GAME_DESIGN_V3.md §3）：
- 线索分级 tier: public | limited | hidden | fake | boss_flaw（兼容旧 level 字段）；
- 地点热度：每被搜一次 -1，归零只剩环境线索（§3.4 抢搜压制）；
- 搜证冲突：同轮同地点被两人搜 → 后来者获「现场被翻动过」痕迹线索；
- 独家猛料：limited 全局仅一份，先到先得；
- 证据合成：集齐 3 条 linked_truth_nodes 有交集的线索 → 自动合成证据卡（§3.6）；
- 伪造：污染阵营「投放伪证」plant_fake() 混入公开池，fake_of 指向被篡改真线索；
- boss_flaw：看山破绽（flaw_id: flavor_1..5），集齐 5 个解锁「指认：DM」；
- unlock_condition 解析："默认 | evidence:clue_003 | memory:char_04:3 |
  counsel:kc_06 | boss:flaw_count>=3"（上下文由 sync_context 注入）。

旧骨架签名与语义保留：__init__ / release / get_player_clues / check_contradiction。
"""
import json
import re
from pathlib import Path

# 环境线索池（无案情信息，AI 永远无法捏造证据——没搜到就是没搜到，环境描写负责搞笑）
_ENV_POOL = [
    {"id": "env_fish", "name": "半块鱼干和一张纸条",
     "fact": "半块鱼干 + 纸条：「别找了，摸鱼中。」", "tags": ["茶水间"]},
    {"id": "env_pill", "name": "年代不明的大力丸",
     "fact": "空调机房里搜出一颗二十年前的大力丸，包装上的代言狐早已过气。", "tags": ["机房"]},
    {"id": "env_badge", "name": "过期的访客贴纸",
     "fact": "一张贴歪的访客贴纸，姓名栏写着「我自己」。", "tags": ["前台"]},
    {"id": "env_dust", "name": "吃灰的服务器",
     "fact": "服务器的灰尘厚得能种多肉，风扇声像在叹气。", "tags": ["机房"]},
    {"id": "env_noodle", "name": "泡面叉子的经济链",
     "fact": "茶水间的泡面叉子按长短排好，像一套严谨的刑具。", "tags": ["茶水间"]},
    {"id": "env_dry", "name": "天台的风",
     "fact": "天台除了风什么都没有，风里还夹着隔壁奶茶店的珍珠味。", "tags": ["天台"]},
]

# 搜证冲突痕迹线索（后来者额外获得，可指证先手）
_TRACE_CLUE_ID = "env_trace_disturbed"


def _loc_token_aliases(token: str) -> set[str]:
    """scene_map key 与 loc_ 前缀互认：loc_teahouse ↔ teahouse。"""
    t = (token or "").strip()
    if not t:
        return set()
    if t.startswith("loc_"):
        return {t, t[4:]}
    return {t, f"loc_{t}"}


class EvidenceChain:
    def __init__(self, scenario_dir: Path):
        self.clue_dir = Path(scenario_dir) / "clues"
        self.scenario = self._read_scenario(scenario_dir)
        self.pool = {}          # clue_id -> clue dict
        self.released = {}      # clue_id -> set(player_id)
        self._load_pool()
        # ---- V3 新增状态 ----
        self._context = {"memory_versions": {}, "counsel_cards": set(),
                         "chat_keywords": set(), "review_flags": set(),
                         "echo_flags": set(), "debate_flags": set()}
        self._location_heat: dict[str, int] = {}
        self._search_log: dict[tuple, list[str]] = {}   # (round_no, location) -> [players]
        self._env_seq = 0                                # 环境线索轮转指针
        self._evidence_cards: list[dict] = []            # 已合成证据卡
        self._ev_seq = 0
        self._flaws: dict[str, set] = {}                 # player_id -> {flaw_id}
        self._gradient = "normal"                        # 动态难度梯度（DifficultyDirector 落地）
        self._flipped: set = set()                       # 双面线索已翻面 clue_id
        self._photos: dict[str, list] = {}               # 暗拍照片 player_id -> [photo]
        self._photo_seq = 0
        self._dry_streaks: dict[str, int] = {}           # 同地点连续未命中连击（成就：摸鱼大师）
        self._env_facts_seen: set = set()                # 已见环境彩蛋 fact（成就：空调已修好）

    def _load_pool(self):
        for f in self.clue_dir.glob("*.json"):
            try:
                clue = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(clue, dict) and clue.get("id"):
                self.pool[clue["id"]] = clue

    @staticmethod
    def _read_scenario(scenario_dir) -> dict:
        path = Path(scenario_dir) / "scenario.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def resolve_location(self, raw: str) -> str | None:
        """地点三口径：scene_map key / 中文 name / loc_ 前缀 → 线索卡 location（中文名）。"""
        token = str(raw or "").strip()
        if not token:
            return None
        scene_map = (self.scenario or {}).get("scene_map") or {}
        if not isinstance(scene_map, dict):
            return None
        incoming = _loc_token_aliases(token)
        for key, node in scene_map.items():
            if isinstance(node, dict):
                name = str(node.get("name") or "").strip()
            elif node is not None:
                name = str(node).strip()
            else:
                name = ""
            if token == name or incoming & _loc_token_aliases(str(key)):
                return name or None
        return None

    # ---------------------------------------------------------- tier/兼容工具
    @staticmethod
    def tier_of(clue: dict) -> str:
        """新 schema 用 tier，旧模板用 level；统一读取。"""
        return str(clue.get("tier") or clue.get("level") or "public")

    def _loc_clues(self, location: str) -> list[dict]:
        return [c for c in self.pool.values() if c.get("location") == location]

    def _location_heat_init(self, location: str) -> int:
        if location not in self._location_heat:
            self._location_heat[location] = max(2, min(5, len(self._loc_clues(location))))
        return self._location_heat[location]

    # --------------------------------------------------------- 上下文（联动）
    def sync_context(self, memory_versions: dict | None = None,
                     counsel_cards: list | set | None = None,
                     chat_keywords: list | set | None = None,
                     review_flags: list | set | None = None,
                     echo_flags: list | set | None = None,
                     debate_flags: list | set | None = None) -> None:
        """注入跨模块上下文：{char: 已解锁版本}、已成功开导的卡 id 集合、
        对话框已说出的关键词集合（chat:keyword_ 条件）、已进入的复盘触发点集合
        （review:credits 等条件）、回声自证（echo:contradiction）、
        法官采信（debate:convinced）。由上层在状态变化后调用。
        """
        if memory_versions is not None:
            self._context["memory_versions"].update(memory_versions)
        if counsel_cards is not None:
            self._context["counsel_cards"].update(counsel_cards)
        if chat_keywords is not None:
            self._context["chat_keywords"].update(chat_keywords)
        if review_flags is not None:
            self._context["review_flags"].update(review_flags)
        if echo_flags is not None:
            self._context["echo_flags"].update(echo_flags)
        if debate_flags is not None:
            self._context["debate_flags"].update(debate_flags)

    def _unlock_met(self, clue: dict) -> bool:
        """解析 unlock_condition（§3.3 条件表达式 + kanshan 扩展语法，确定性求值）。

        支持："默认 | evidence:<clue_id> | memory:<char>:<ver> | counsel:<kc_id> |
        boss:flaw_count>=<n> | chat:keyword_<关键词> | review:<触发点> |
        echo:<flag> | debate:<flag>"
        """
        cond = str(clue.get("unlock_condition", "默认")).strip()
        if cond in ("", "默认"):
            return True
        if cond.startswith("evidence:"):
            # evidence:clue_003 → 评估视角的玩家需已持有该线索（release 时按 player_id 判定）
            return self._eval_holder(cond.split(":", 1)[1].strip())
        if cond.startswith("memory:"):
            # memory:char_04:3 → 该角色记忆已解锁至版本 >= 3
            m = re.fullmatch(r"memory:(\S+?):(\d+)", cond)
            if not m:
                return False
            got = int(self._context["memory_versions"].get(m.group(1), 0))
            return got >= int(m.group(2))
        if cond.startswith("counsel:"):
            # counsel:kc_06 → 该知识卡已开导成功
            return cond.split(":", 1)[1].strip() in self._context["counsel_cards"]
        if cond.startswith("boss:"):
            # boss:flaw_count>=3 → 全场收集的看山破绽数（assist 梯度宽限 -1，hard 收紧 +1）
            m = re.fullmatch(r"boss:flaw_count\s*>=\s*(\d+)", cond)
            if not m:
                return False
            grace = {"assist": -1, "hard": 1}.get(self._gradient, 0)
            return self.flaw_count() >= max(0, int(m.group(1)) + grace)
        if cond.startswith("chat:keyword_"):
            # chat:keyword_看山，关门 → 玩家在对话框说出该关键词（kanshan 扩展语法，
            # 见 scenario.json condition_grammar；关键词为前缀后的原文，含逗号空格）
            kw = cond[len("chat:keyword_"):].strip()
            return kw in self._context["chat_keywords"] or kw in {k.strip() for k in self._context["chat_keywords"]}
        if cond.startswith("review:"):
            # review:credits → 进入复盘页触发点（kanshan 扩展语法）
            return cond.split(":", 1)[1].strip() in self._context["review_flags"]
        if cond.startswith("echo:"):
            # echo:contradiction → 回声自证成功（由 driver 注入，禁止搜证旁路）
            return cond.split(":", 1)[1].strip() in self._context["echo_flags"]
        if cond.startswith("debate:"):
            # debate:convinced → 法官采信（由 driver 注入，禁止搜证旁路）
            return cond.split(":", 1)[1].strip() in self._context["debate_flags"]
        return False

    def _eval_holder(self, clue_id: str) -> bool:
        holder = getattr(self, "_eval_player", None)
        if holder is None:
            return False
        return clue_id in self.get_player_clues(holder)

    # -------------------------------------------------------------- 旧骨架 API
    def release(self, clue_id: str, player_id: str) -> dict | None:
        """按条件发放线索：校验触发类型与前置条件。

        升级语义（保持签名/返回）：tier=hidden / boss_flaw 需 unlock_condition 满足；
        limited 全局仅一份（已被他人持有则拒绝）；fake 线索只能经 plant_fake 入场。
        """
        clue = self.pool.get(clue_id)
        if not clue:
            return None
        tier = self.tier_of(clue)
        if tier == "fake":
            return None  # 伪证不按正常渠道发放，由污染阵营 plant_fake 投放
        if self._needs_unlock_gate(clue) and not self._eval_holder_view(clue, player_id):
            return None
        if tier == "limited":
            holders = self.released.get(clue_id)
            if holders and player_id not in holders:
                return None  # 独家猛料：先到先得
        self.released.setdefault(clue_id, set()).add(player_id)
        if tier == "boss_flaw" and clue.get("flaw_id"):
            self._flaws.setdefault(player_id, set()).add(clue["flaw_id"])
        return clue

    def _needs_unlock_gate(self, clue: dict) -> bool:
        """hidden/boss_flaw 一律求值；limited 仅在条件不是「默认」时求值。"""
        tier = self.tier_of(clue)
        if tier in ("hidden", "boss_flaw"):
            return True
        if tier == "limited":
            cond = str(clue.get("unlock_condition", "默认")).strip()
            return cond not in ("", "默认")
        return False

    def _eval_holder_view(self, clue: dict, player_id: str) -> bool:
        """以指定玩家为视角求值 unlock_condition（evidence 类条件按其持有物判定）。"""
        saved = getattr(self, "_eval_player", None)
        self._eval_player = player_id
        try:
            return self._unlock_met(clue)
        finally:
            self._eval_player = saved

    def get_player_clues(self, player_id: str) -> list:
        return [cid for cid, players in self.released.items() if player_id in players]

    def check_contradiction(self, statement: str, truth: dict) -> list[str]:
        """一致性守卫调用：检测 NPC 证词与真相表的矛盾点。"""
        conflicts = []
        for node in truth.get("truth_nodes", []):
            # 简化示例：实际用语义比对/关键词+向量双重校验
            name = node.get("name", "")
            if name and name in statement and node.get("desc") not in statement:
                conflicts.append(node["id"])
        return conflicts

    # ------------------------------------------------------------------ 搜证
    def search(self, location: str, keyword: str, player_id: str,
               round_no: int = 0) -> dict:
        """V3 §3.2 搜证主循环（引擎侧确定性裁决）。

        location ∩ keyword(tags) ≥1 → 从候选池按优先级发线索；未命中 → 环境线索。
        地点热度 -1；同轮同地点第二人搜 → 额外获得「现场被翻动过」痕迹。
        返回 {hit, clues, env_clue, disturb, heat, location_status}。
        """
        resolved = self.resolve_location(location)
        if resolved:
            location = resolved
        self._location_heat_init(location)
        candidates = []
        for clue in self._loc_clues(location):
            tier = self.tier_of(clue)
            if tier == "fake":
                continue  # 伪证只能经 plant_fake 混入
            if clue["id"] in self.released and player_id in self.released[clue["id"]]:
                continue  # 自己已持有
            if tier == "limited" and self.released.get(clue["id"]):
                continue  # 独家猛料已被他人拿走
            if self._needs_unlock_gate(clue) and not self._eval_holder_view(clue, player_id):
                continue  # 条件未满足不可见
            if self._keyword_match(clue, keyword):
                candidates.append(clue)
        # 优先级：boss_flaw > hidden > limited > public（高价值优先暴露给先手）
        order = {"boss_flaw": 0, "hidden": 1, "limited": 2, "public": 3}
        candidates.sort(key=lambda c: order.get(self.tier_of(c), 4))

        hit = bool(candidates)
        granted: list[dict] = []
        for clue in candidates[:1]:  # 单次搜证至多 1 张案情线索
            got = self.release(clue["id"], player_id)
            if got:
                granted.append(got)

        # 地点热度 -1（命中与否都算搜过一次）
        self._location_heat[location] = max(0, self._location_heat[location] - 1)
        # 连击统计：命中清零 / 未命中 +1（成就判定数据源）
        if hit:
            self._dry_streaks[location] = 0
        else:
            self._dry_streaks[location] = self._dry_streaks.get(location, 0) + 1

        # 搜证冲突：同轮同地点先手另有其人 → 后来者获痕迹线索
        key = (round_no, location)
        first = self._search_log.get(key, [])
        disturb = bool(first) and player_id not in first
        env_clue = None
        # 未命中时给出确定性、非剧透的方向提示：只暴露当前地点公开线索的
        # 标签，不直接透露线索事实。这样首局不会因一次关键词失误而卡死，
        # 同时仍保留玩家自己推理的空间。
        next_hint = None
        if disturb:
            env_clue = self._grant_trace(location, player_id)
        elif not hit:
            env_clue = self._grant_env(location, player_id)
            public_tags = []
            for clue in self._loc_clues(location):
                if (self.tier_of(clue) == "public"
                        and clue.get("linked_truth_nodes")
                        and clue["id"] not in self.get_player_clues(player_id)
                        and self._eval_holder_view(clue, player_id)):
                    for tag in clue.get("tags", []):
                        tag = str(tag)
                        if tag and tag not in public_tags:
                            public_tags.append(tag)
            if public_tags:
                next_hint = {
                    "kind": "keyword_hint",
                    "text": "没有找到案情线索。可以换个关键词再查一次。",
                    "keywords": public_tags[:3],
                }
        self._search_log.setdefault(key, []).append(player_id)
        return {"hit": hit, "clues": granted, "env_clue": env_clue, "disturb": disturb,
                "hint": next_hint,
                "heat": self._location_heat[location],
                "location_status": self.location_status(location)}

    def _keyword_match(self, clue: dict, keyword: str) -> bool:
        kw = (keyword or "").strip().lower()
        if not kw:
            return False
        tags = [str(t).lower() for t in clue.get("tags", [])]
        return any(kw in t or t in kw for t in tags)

    def _grant_env(self, location: str, player_id: str) -> dict:
        env = dict(_ENV_POOL[self._env_seq % len(_ENV_POOL)])
        self._env_seq += 1
        self._env_facts_seen.add(env["fact"])
        env.update({"tier": "public", "location": location, "linked_truth_nodes": [],
                    "unlock_condition": "默认", "fake_of": None, "flaw_id": None,
                    "flavor_hint": "AI 可自由扩写环境吐槽，但 fact 不许动。"})
        env["id"] = f"{env['id']}_{self._env_seq}"
        self.pool[env["id"]] = env
        self.released.setdefault(env["id"], set()).add(player_id)
        return env

    def _grant_trace(self, location: str, player_id: str) -> dict:
        trace = {"id": f"{_TRACE_CLUE_ID}_{location}_{len(self._search_log)}",
                 "name": "现场被翻动过", "tier": "public", "location": location,
                 "tags": ["痕迹", "冲突"], "linked_truth_nodes": [],
                 "fact": "你到达时现场刚被人翻动过——有人比你先一步搜过这里。",
                 "flavor_hint": "描写抽屉没关严、纸屑错位等「先手痕迹」细节。",
                 "unlock_condition": "默认", "fake_of": None, "flaw_id": None}
        self.pool[trace["id"]] = trace
        self.released.setdefault(trace["id"], set()).add(player_id)
        return trace

    def location_status(self, location: str) -> str:
        """地点热度三档模糊提示（V3 §3.1：有发现 / 可能有 / 一无所获，不剧透）。"""
        self._location_heat_init(location)
        h = self._location_heat[location]
        if h > 2:
            return "有发现"
        if h >= 1:
            return "可能有"
        return "一无所获"

    def suggest_keywords(self, location: str, limit: int | None = None) -> list[str]:
        """系统建议关键词：该地点候选线索 tags 并集（去重保序）。

        limit 缺省时按动态难度梯度取值（assist 5 / normal 3 / hard 2）。
        """
        if limit is None:
            limit = {"assist": 5, "hard": 2}.get(self._gradient, 3)
        seen, out = set(), []
        for clue in self._loc_clues(location):
            for t in clue.get("tags", []):
                if t not in seen:
                    seen.add(t)
                    out.append(t)
        return out[:limit]

    def set_gradient(self, gradient: str) -> None:
        """动态难度梯度落地（assist|normal|hard，由 DifficultyDirector.apply 调用）：
        影响建议关键词数量与 boss 条件宽限。"""
        if gradient in ("assist", "normal", "hard"):
            self._gradient = gradient

    # ------------------------------------------------------- D 对接点（V31 B.3）
    def on_chat(self, player_id: str, text: str) -> list[dict]:
        """对话框触发点：玩家发言命中 chat:keyword_<关键词> 条件 → 自动解锁线索。

        返回本次解锁的线索 dict 列表（供 F 广播 clue_gained 事件）；幂等。
        """
        got: list[dict] = []
        for clue_id, clue in sorted(self.pool.items()):
            cond = str(clue.get("unlock_condition", ""))
            if not cond.startswith("chat:keyword_"):
                continue
            kw = cond[len("chat:keyword_"):].strip()
            if kw and kw in str(text):
                if clue_id in self.get_player_clues(player_id):
                    continue
                self.sync_context(chat_keywords={kw})
                released = self.release(clue_id, player_id)
                if released:
                    got.append(released)
        return got

    def on_review_entered(self, player_id: str) -> list[dict]:
        """复盘页触发点：进入复盘 → 解锁全部 review:* 条件线索（如 review:credits）。"""
        got: list[dict] = []
        flags = {c["unlock_condition"].split(":", 1)[1].strip()
                 for c in self.pool.values()
                 if str(c.get("unlock_condition", "")).startswith("review:")}
        if flags:
            self.sync_context(review_flags=flags)
        for clue_id, clue in sorted(self.pool.items()):
            if str(clue.get("unlock_condition", "")).startswith("review:"):
                if clue_id in self.get_player_clues(player_id):
                    continue
                released = self.release(clue_id, player_id)
                if released:
                    got.append(released)
        return got

    # ------------------------------------------------------- P1/P2 裁决件
    def flip_side(self, clue_id: str, player_id: str) -> dict | None:
        """双面线索锁（P2）：线索可带 sides={front, back, back_condition} 字段，
        公开展示恒为 front；back_condition 满足（评估规则同 unlock_condition）才可翻面。
        返回 {"clue_id", "back"} 或 None（无双面/条件未满足/已翻面）。"""
        clue = self.pool.get(clue_id)
        if not clue or not isinstance(clue.get("sides"), dict) or clue_id in self._flipped:
            return None
        sides = clue["sides"]
        if not sides.get("back"):
            return None
        probe = dict(clue)
        probe["unlock_condition"] = sides.get("back_condition", "默认")
        if not self._eval_holder_view(probe, player_id):
            return None
        self._flipped.add(clue_id)
        return {"clue_id": clue_id, "back": sides["back"],
                "front": sides.get("front", clue.get("fact", ""))}

    def stealth_photo(self, location: str, keyword: str, player_id: str,
                      round_no: int = 0) -> dict:
        """暗拍（P2）：2AP（由上层 PartyBoard/resolver 扣）——线索**留原地**，你只持有
        「照片」（可分享、可说谎，信息博弈加深，GAMEPLAY_V31 §一）。

        与 search 的区别：不写 released（他人仍可搜到原件），地点热度照常 -1。
        返回 {"ok", "photo"|"env_note"}。
        """
        self._location_heat_init(location)
        order = {"boss_flaw": 0, "hidden": 1, "limited": 2, "public": 3}
        candidates = []
        for clue in self._loc_clues(location):
            tier = self.tier_of(clue)
            if tier == "fake":
                continue
            if clue["id"] in self.released and player_id in self.released[clue["id"]]:
                continue
            if tier == "limited" and self.released.get(clue["id"]):
                continue
            if tier in ("hidden", "boss_flaw") and not self._eval_holder_view(clue, player_id):
                continue
            if self._keyword_match(clue, keyword):
                candidates.append(clue)
        candidates.sort(key=lambda c: order.get(self.tier_of(c), 4))
        for clue in candidates[:1]:
            self._photo_seq += 1
            photo = {"photo_id": f"photo_{self._photo_seq}", "clue_id": clue["id"],
                     "name": clue.get("name", ""), "fact": clue.get("fact", ""),
                     "location": location, "round": round_no, "owner": player_id,
                     "shared": False}
            self._photos.setdefault(player_id, []).append(photo)
            self._location_heat[location] = max(0, self._location_heat[location] - 1)
            return {"ok": True, "photo": photo}
        self._location_heat[location] = max(0, self._location_heat[location] - 1)
        return {"ok": False, "env_note": "快门按了十几张，全是空调外机和一只警惕的海鸥。"}

    def share_photo(self, player_id: str, photo_id: str,
                    claim: str | None = None) -> dict | None:
        """照片分享（可说谎——引擎登记原文与声称内容，真伪由圆桌对质裁决）。"""
        for p in self._photos.get(player_id, []):
            if p["photo_id"] == photo_id:
                p["shared"] = True
                return {"speaker": player_id, "photo": p,
                        "claim": claim if claim is not None else p["fact"]}
        return None

    def photos_of(self, player_id: str) -> list[dict]:
        return list(self._photos.get(player_id, []))

    def clean_photo_counts(self) -> dict:
        """各玩家「干净暗拍」数（CONTRACTS §3.5b：photos_of(pid) 中 clue_id 指向
        池内非 fake 线索的照片；photo 带 flagged=True（被当场拆穿）则排除——前向兼容）。
        成就「暗房大师」判定数据源。"""
        out: dict[str, int] = {}
        for pid, photos in self._photos.items():
            n = 0
            for p in photos:
                if p.get("flagged"):
                    continue
                clue = self.pool.get(p.get("clue_id"))
                if clue is not None and self.tier_of(clue) != "fake":
                    n += 1
            out[pid] = n
        return out

    # ------------------------------------------------------------------ 伪造
    def plant_fake(self, clue_id: str, actor: str) -> dict | None:
        """污染阵营「投放伪证」：tier=fake 线索混入公开池（fake_of 指向真线索）。

        返回投放的伪证线索；不存在或非 fake 返回 None。
        """
        clue = self.pool.get(clue_id)
        if not clue or self.tier_of(clue) != "fake":
            return None
        self.released.setdefault(clue_id, set()).add(actor)
        return clue

    def forgery_target(self, fake_clue_id: str) -> dict | None:
        """证伪对质用：返回伪证 fake_of 指向的真线索（None = 非伪证）。"""
        fake = self.pool.get(fake_clue_id)
        if not fake or self.tier_of(fake) != "fake":
            return None
        return self.pool.get(fake.get("fake_of")) if fake.get("fake_of") else None

    # -------------------------------------------------------------- 证据合成
    def try_compose(self, player_id: str) -> dict | None:
        """V3 §3.6 证据合成：3 条 linked_truth_nodes 有交集的线索 → 证据卡。

        返回 {"evidence_id", "clue_ids", "truth_nodes", "owner"} 或 None。
        """
        held = [self.pool[c] for c in self.get_player_clues(player_id) if c in self.pool]
        node_map: dict[str, list[dict]] = {}
        for clue in held:
            for tn in clue.get("linked_truth_nodes") or []:
                node_map.setdefault(tn, []).append(clue)
        for tn in sorted(node_map):
            if len(node_map[tn]) >= 3:
                clues = sorted({c["id"] for c in node_map[tn]})
                if any(ev["clue_ids"] == clues and ev["truth_nodes"][0] == tn
                       for ev in self._evidence_cards):
                    continue
                self._ev_seq += 1
                card = {"evidence_id": f"ev_{player_id}_{self._ev_seq}",
                        "clue_ids": clues, "truth_nodes": [tn], "owner": player_id}
                self._evidence_cards.append(card)
                return card
        return None

    def evidence_cards(self, player_id: str | None = None) -> list[dict]:
        """已合成证据卡（可按 owner 过滤）。"""
        return [ev for ev in self._evidence_cards
                if player_id is None or ev["owner"] == player_id]

    # -------------------------------------------------------------- boss 破绽
    def flaw_count(self, player_id: str | None = None) -> int:
        """看山破绽收集数（flaw_id 去重；player_id=None 时全场合计）。"""
        if player_id is not None:
            return len(self._flaws.get(player_id, set()))
        all_flaws: set = set()
        for s in self._flaws.values():
            all_flaws |= s
        return len(all_flaws)

    def boss_ready(self) -> bool:
        """集齐 5 个破绽 → 解锁「指认：DM」选项。"""
        return self.flaw_count() >= 5

    # -------------------------------------------------------------- 篡改点接入
    def ingest_clue(self, clue: dict, owner: str | None = None) -> dict:
        """外部线索入池（memory_system 篡改点转线索卡自动入证据链）。

        幂等：同 id 重复入池只更新内容。owner 非 None 时自动发放给该玩家。
        """
        self.pool[clue["id"]] = clue
        if owner:
            self.released.setdefault(clue["id"], set()).add(owner)
        return clue

    def clue(self, clue_id: str) -> dict | None:
        return self.pool.get(clue_id)

    # ------------------------------------------------- 成就判定数据源（只读）
    def dry_streaks(self) -> dict:
        """{location: 连续未命中次数}（成就：摸鱼大师=任一地点 ≥3）。"""
        return dict(self._dry_streaks)

    def env_facts_seen(self) -> set:
        """已见环境彩蛋 fact 集合（成就：空调已修好）。"""
        return set(self._env_facts_seen)

    def chat_keywords_hit(self) -> set:
        """已说出的对话框关键词（成就：唤醒词侦探）。"""
        return set(self._context["chat_keywords"])
