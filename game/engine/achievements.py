"""achievements — 成就判定引擎 + 鱼干收集品（P3 彩蛋层）

数据源（D 组交付，B/F 组直接取用）：
- content/scenarios/kanshan/scripts/achievements.md §三（23 条成就判定 JSON，
  condition DSL：type/op/value/target/cards）；
- content/scenarios/kanshan/scripts/collectibles_p3.md §四（collectibles JSON：
  fish_01..03 位置/拾取时机 + 集齐解锁规则）。

职责（确定性裁决，禁止 AI 参与）：
- AchievementEngine：condition DSL 求值器。引擎自判项（boss_flaw_count /
  chat_keyword / env_clue / heart_unlock_count / clue_collected / same_location_dry_streak /
  refute_success_streak / memory_puzzle_win / counsel_multi / collectible / ending）
  从注入的引擎对象只读取数；外部行为项（listen_full / fake_exposed / confrontation_win /
  danmaku_echo / antifraud / quiz / closing_vote）由上层经 record() 喂事件；
  解锁幂等（跨局计数归 session_store，本地）。
- CollectiblesBoard：拾取门槛（available_from: act1/act2/act3，0AP）与集齐触发
  （ach_yuganxianren + 看山Bot 隐藏语音 4+1 段清单）。彩蛋层硬规则：不进证据链、
  不影响结局判定（与 evidence_chain 零耦合）。

实现归 B 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# D 组 JSON 的 ending value → 引擎 matrix_ending 键映射（resolver.ENDINGS）
ENDING_MAP = {
    "ending_kanshan": {"kanshan_still_mountain"},
    "ending_pollution": {"pollution_win"},
    "ending_sunny": {"all_hearts_clear"},
    "ending_chapter7": {"deleted_chapter7"},
    "ending_perfect": {"perfect_restoration"},
    "ending_truth": {"truth_revealed"},
    "ending_vindicated": {"vindicated"},
}


def _extract_json_block(text: str) -> dict | list:
    """从 markdown 提取 ```json 围栏块（D 组两份对接 JSON 均为 md 内嵌）。"""
    m = re.search(r"```json\s*\n(.*?)```", text, re.S)
    if not m:
        raise ValueError("no ```json block found")
    return json.loads(m.group(1))


def _load_source(source) -> dict | list:
    """接受：dict/list（已解析 JSON）| .md/.json 路径 | 原始 JSON/md 文本。"""
    if isinstance(source, (dict, list)):
        return source
    text = str(source)
    p = Path(text)
    if p.is_file():
        text = p.read_text(encoding="utf-8")
    if text.lstrip().startswith(("{", "[")):
        return json.loads(text)
    return _extract_json_block(text)


def _cmp(actual, op: str, value) -> bool | None:
    """op 求值；actual=None（数据未产生）→ None（视为未达成但非错误）。"""
    if actual is None:
        return None
    try:
        if op == ">=":
            return actual >= value
        if op == "<=":
            return actual <= value
        if op == ">":
            return actual > value
        if op == "<":
            return actual < value
        if op == "==":
            return actual == value
        if op == "!=":
            return actual != value
    except TypeError:
        return False
    return bool(actual) if op is None else None


class AchievementEngine:
    def __init__(self, refs: dict | None = None) -> None:
        """refs（可选注入，引擎自判项数据源）：
        {evidence_chain, memory_system, opinion_feed, knowledge_cards, collectibles, party}"""
        self._refs = dict(refs or {})
        self._defs: list[dict] = []
        self._meta: dict[str, dict] = {}         # id -> {banner, share_line}（md 表格提取）
        self._unlocked: set[str] = set()
        self._stats: dict[str, float] = {}       # record() 计数

    # ------------------------------------------------------------------ load
    def load(self, source) -> None:
        """加载成就定义：achievements.md 路径 / JSON 文本 / 已解析 list。

        同时提取 md 表格中的横幅与分享卡文案（列：id|成就|稀有度|...|解锁横幅文案|分享卡一句话）。
        """
        data = _load_source(source)
        if isinstance(data, dict):
            data = data.get("achievements", [])
        self._defs = [a for a in data if isinstance(a, dict) and a.get("id")]
        src = Path(str(source)) if Path(str(source)).is_file() else None
        if src and src.suffix == ".md":
            self._load_meta(src.read_text(encoding="utf-8"))

    def _load_meta(self, md_text: str) -> None:
        for m in re.finditer(
                r"^\|\s*(ach_\w+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*[^|]+\|\s*([^|]+)\|\s*([^|]+)\|",
                md_text, re.M):
            self._meta[m.group(1)] = {"name": m.group(2).strip().strip("*"),
                                      "rarity_label": m.group(3).strip(),
                                      "banner": m.group(4).strip(),
                                      "share_line": m.group(5).strip()}

    # ---------------------------------------------------------------- record
    def record(self, event: str, target: str | None = None, value: float = 1,
               mode: str = "add") -> None:
        """外部行为事件（引擎无法自判项）：
        listen_full(target) / fake_exposed / confrontation_win(target) / danmaku_echo /
        antifraud(correct) / quiz(score) / closing_survived / hammered_votes(target)。
        mode: add(累加) | set(覆盖) | max(取大)。"""
        key = f"{event}:{target}" if target else event
        cur = self._stats.get(key)
        if mode == "add" or cur is None:
            self._stats[key] = (cur or 0) + value
        elif mode == "set":
            self._stats[key] = value
        elif mode == "max":
            self._stats[key] = max(cur or 0, value)

    # -------------------------------------------------------------- evaluate
    def evaluate(self, ending_key: str | None = None) -> dict:
        """全量判定：返回 {"unlocked": [ach...], "new_count", "total", "unlocked_ids"}。

        ach dict = D 组 JSON 原字段 + meta（banner/share_line，若有）。
        ending_key：matrix_ending() 的 ending 值（本轮终局，无则 None）。
        """
        new: list[dict] = []
        for a in self._defs:
            aid = a["id"]
            if aid in self._unlocked:
                continue
            met = self._cond_met(a.get("condition", {}), ending_key)
            if met:
                self._unlocked.add(aid)
                out = dict(a)
                if aid in self._meta:
                    out.update(self._meta[aid])
                new.append(out)
        return {"unlocked": new, "new_count": len(new),
                "total": len(self._defs), "unlocked_ids": sorted(self._unlocked)}

    def unlocked_ids(self) -> list[str]:
        return sorted(self._unlocked)

    # ------------------------------------------------------------ DSL 求值器
    def _cond_met(self, cond: dict, ending_key: str | None) -> bool:
        t = str(cond.get("type", ""))
        op = cond.get("op")
        val = cond.get("value")
        ec = self._refs.get("evidence_chain")
        ms = self._refs.get("memory_system")
        of = self._refs.get("opinion_feed")
        ks = self._refs.get("knowledge_cards")
        cb = self._refs.get("collectibles")

        if t == "ending":
            return ending_key in ENDING_MAP.get(str(val), set())
        if t == "counsel_count":
            n = len({c["char_id"] for c in getattr(ks, "_counsel_log", [])
                     if c.get("matched") and c.get("char_id") not in
                     ("team", "team_all", "archive", "archive_bureau")}) if ks else None
            return bool(_cmp(n, op or ">=", val))
        if t == "clue_collected":
            return bool(_cmp(len(getattr(ec, "released", {}) or {}), op or ">=", val))
        if t == "listen_full":
            return bool(_cmp(self._stats.get(f"listen_full:{cond.get('target')}", 0),
                             op or ">=", val))
        if t == "fake_exposed":
            return bool(_cmp(self._stats.get("fake_exposed", 0), op or ">=", val))
        if t == "confrontation_win":
            return self._stats.get(f"confrontation_win:{cond.get('target')}", 0) >= 1
        if t == "danmaku_echo":
            return bool(_cmp(self._stats.get("danmaku_echo", 0), op or ">=", val))
        if t == "memory_puzzle_win":
            return bool(ms and ms.puzzle_wins() >= 1)
        if t == "counsel_multi":
            target, cards = cond.get("target"), set(cond.get("cards", []))
            if not ks:
                return False
            hit = {c["card_id"] for c in ks._counsel_log
                   if c.get("matched") and c.get("char_id") == target}
            return cards <= hit
        if t == "same_location_dry_streak":
            streaks = ec.dry_streaks() if ec else {}
            return bool(_cmp(max(streaks.values(), default=0), op or ">=", val))
        if t == "boss_flaw_count":
            return bool(ec and _cmp(ec.flaw_count(), op or ">=", val))
        if t == "chat_keyword":
            return bool(ec and str(val) in ec.chat_keywords_hit())
        if t == "refute_success_streak":
            return bool(of and _cmp(of.refute_streak(), op or ">=", val))
        if t == "antifraud_all_correct":
            return bool(self._stats.get("antifraud_all_correct", 0) >= 1)
        if t == "quiz_score":
            return bool(_cmp(self._stats.get("quiz_score"), op or "==", val))
        if t == "closing_vote_top1_survived":
            return bool(self._stats.get("closing_vote_top1_survived", 0) >= 1)
        if t == "collectible":
            return bool(cb and _cmp(cb.collected_count(), op or ">=", val))
        if t == "env_clue":
            return bool(ec and any(str(val) in f for f in ec.env_facts_seen()))
        if t == "heart_unlock_count":
            return bool(ms and _cmp(ms.heart_unlock_count(), op or ">=", val))
        if t == "stealth_photo_clean":
            # CONTRACTS §3.5b：干净暗拍=photos_of(pid) 中 clue_id 指向池内非 fake
            # 线索的照片计数（flagged 拆穿项排除，前向兼容）；逐玩家计，
            # 任一玩家达标即解锁（party 下取最大者）。
            counts = ec.clean_photo_counts() if ec else {}
            return bool(_cmp(max(counts.values(), default=0), op or ">=", val))
        if t == "hammered_votes":
            # record 外部登记型（gameplay：终局陈词"最想锤的人"票数）：
            # record("hammered_votes", target=...)；任一目标被锤票数达标即解锁。
            hammered = [v for k, v in self._stats.items() if k.startswith("hammered_votes")]
            return bool(_cmp(max(hammered, default=0), op or ">=", val))
        return False  # 未知 type 不解锁（新 DSL 需回 A 广播）


class CollectiblesBoard:
    """鱼干收集品（P3 彩蛋层）：不进证据链、不占 AP、不影响结局判定。"""

    ACT_ORDER = {"act1": 1, "act2": 2, "act3": 3, "act4": 4}

    def __init__(self) -> None:
        self._items: list[dict] = []
        self._unlock: dict = {}
        self._collected: dict[str, str] = {}     # item_id -> player_id（首拾者）
        self._order = {"act1": 0, "act2": 0}     # 稳定遍历用

    # ------------------------------------------------------------------ load
    def load(self, source) -> None:
        """加载 collectibles JSON：collectibles_p3.md 路径 / JSON 文本 / 已解析 dict。"""
        data = _load_source(source)
        if isinstance(data, list):
            data = {"collectibles": data}
        self._items = list(data.get("collectibles", []))
        self._unlock = dict(data.get("unlock", {}))

    # --------------------------------------------------------------- collect
    def collect(self, player_id: str, item_id: str, act_no: int = 1) -> dict:
        """拾取：点击微光点即得，0AP；校验拾取时机（available_from: act1|act2|act3）。"""
        item = next((i for i in self._items if i["id"] == item_id), None)
        if not item:
            return {"ok": False, "reason": "unknown_item"}
        if item_id in self._collected:
            return {"ok": False, "reason": "already_collected", "item": item}
        need = self.ACT_ORDER.get(str(item.get("available_from", "act1")), 1)
        if act_no < need:
            return {"ok": False, "reason": "locked_until_act",
                    "available_from": item.get("available_from"), "item": item}
        self._collected[item_id] = player_id
        prog = self.progress()
        out = {"ok": True, "item": item, "player_id": player_id,
               "cost_ap": item.get("cost_ap", 0), **prog}
        if prog["collected"] >= prog["total"] and prog["total"] > 0:
            out["all_collected"] = True
            out["unlock"] = self.unlock_payload()
        return out

    # -------------------------------------------------------------- progress
    def progress(self) -> dict:
        return {"collected": len(self._collected),
                "total": len(self._items),
                "items": sorted(self._collected),
                "pending": sorted(i["id"] for i in self._items if i["id"] not in self._collected)}

    def collected_count(self) -> int:
        """成就 ach_yuganxianren 判定数据源（collectible == 3）。"""
        return len(self._collected)

    def all_collected(self) -> bool:
        return bool(self._items) and len(self._collected) == len(self._items)

    def unlock_payload(self) -> dict | None:
        """集齐触发：ach_yuganxianren + 看山Bot 隐藏语音清单（4 段 + 终极层加播 1 段）。"""
        if not self.all_collected():
            return None
        return {"achievement": self._unlock.get("achievement", "ach_yuganxianren"),
                "voice_lines": list(self._unlock.get("voice_lines", [])),
                "boss_reveal_extra": self._unlock.get("boss_reveal_extra"),
                "note": "语音按句切片逐句播放，不合并（IndexTTS 2.5）"}
