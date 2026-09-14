"""knowledge_cards — 知识卡引擎（心晴自习室/知识开导/辟谣弹药）

契约：docs/CONTRACTS.md §3.4；设计：docs/KNOWLEDGE_SYSTEM.md。
职责（确定性裁决，禁止 AI 参与）：
- 10 张知识卡池（对应知乎知识 10 篇正文，制作期已入库 content/worlds/yanyan_sources/）；
- 自习室抽卡：每次搜证随机抽 1 张未持有卡（全队共享池）；
- 心病匹配表：卡 binds ↔ NPC 心病；开导 = 2AP + 匹配 → 成功收益
  （memory_unlock / evidence / buff_ap / plot_fragment / boss_key），不匹配 → 群嘲演出；
- 辟谣弹药校验供 opinion_feed.refute() 调用；
- 心晴诊室结算：counsel_count 决定结局档位（4+ → 隐藏结局「全员心晴」）。

实现归 B 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

import json
import random
from pathlib import Path


class KnowledgeSystem:
    # 特殊开导对象别名（kanshan 内容用 team_all/archive_bureau，契约示例用 team/archive）
    TEAM_ALIASES = {"team", "team_all"}
    ARCHIVE_ALIASES = {"archive", "archive_bureau"}

    def __init__(self, seed: int | None = None) -> None:
        self._cards: dict[str, dict] = {}
        self._held: dict[str, str] = {}          # card_id -> 首抽 actor（全队共享池）
        self._rng = random.Random(seed)
        self._counsel_log: list[dict] = []       # 心晴档案
        self._counseled_chars: set[str] = set()  # 开导成功的角色（去重）
        self._counseled_cards: set[str] = set()  # 已成功使用的卡 id
        self._buff_ap_used = False
        self.current_round = 0                   # 当前轮次（上层 set_round 注入）
        self._er: dict[str, int] = {}            # 急诊室：char_id -> 红灯失效轮

    def set_round(self, round_no: int) -> None:
        """轮次推进注入（急诊室红灯有效期判定用）。"""
        self.current_round = round_no

    def er_active(self, char_id: str) -> bool:
        """心病急诊室红灯是否亮着（开导失败→恶化，下一轮内用对卡=双倍收益）。"""
        expiry = self._er.get(char_id)
        return expiry is not None and self.current_round <= expiry

    # ------------------------------------------------------------------ load
    def load(self, scenario_dir: str) -> None:
        """加载 content/scenarios/kanshan/knowledge_cards/ 10 卡定义。

        容错：目录不存在或为空时静默空载。
        """
        kc_dir = Path(scenario_dir) / "knowledge_cards"
        self._cards = {}
        if not kc_dir.is_dir():
            return
        for f in sorted(kc_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict) and data.get("id"):
                self._cards[data["id"]] = data

    # ------------------------------------------------------------------ draw
    def draw(self, actor: str) -> dict | None:
        """自习室抽卡：返回 {card} 或 None（已集齐）。全队共享池。"""
        remaining = [c for cid, c in sorted(self._cards.items()) if cid not in self._held]
        if not remaining:
            return None
        card = self._rng.choice(remaining)
        self._held[card["id"]] = actor
        return {"card": card}

    # --------------------------------------------------------------- counsel
    def counsel(self, actor: str, char_id: str, card_id: str) -> dict:
        """知识开导演算：{matched, effect, unlocked, transcript_hint}。

        matched=False 时 effect=mock（群嘲），收益为空。
        匹配规则（确定性）：卡的 binds 字段 == 被开导对象（NPC char_id / "team" / "archive"）。
        transcript_hint 仅做确定性拼装（金句+卡面），开导词由 Agent 层基于此生成。
        """
        card = self._cards.get(card_id)
        if not card:
            return {"matched": False, "effect": "mock", "unlocked": None,
                    "transcript_hint": "（未知的卡片，NPC 一脸茫然）"}
        # 持有校验在 EngineDriver（G10）；本层只做匹配/急诊室/诊室结算。

        binds = card.get("binds")
        matched = bool(binds) and (
            binds == char_id
            or (binds in self.TEAM_ALIASES and char_id in self.TEAM_ALIASES)
            or (binds in self.ARCHIVE_ALIASES and char_id in self.ARCHIVE_ALIASES)
        )
        if not matched:
            # 急诊室：开导失败 → 心病「恶化」亮红灯，下一轮内用对卡 = 双倍收益
            self._er[char_id] = self.current_round + 1
            self._counsel_log.append({"actor": actor, "char_id": char_id,
                                      "card_id": card_id, "matched": False})
            return {"matched": False, "effect": "mock", "unlocked": None,
                    "transcript_hint": (
                        f"尬聊现场：用《{card.get('title', card_id)}》开导 {char_id}，"
                        "对方愣住，弹幕群嘲「答非所问预警」。"
                        f"急诊室红灯亮起：{char_id} 的心病恶化了，下一轮内用对卡=双倍收益！")}

        effect = card.get("effect", "evidence")
        unlocked = self._resolve_effect(effect, card, char_id)
        rescue = self.er_active(char_id)
        if rescue:
            # 急诊室抢救成功：收益双倍（P1 节奏感）
            unlocked = dict(unlocked or {})
            unlocked["doubled"] = True
            if effect == "buff_ap":
                unlocked["ap"] = 2
            self._er.pop(char_id, None)
        first_time = card_id not in self._counseled_cards
        self._counseled_cards.add(card_id)
        if not self._is_group_target(char_id):
            self._counseled_chars.add(char_id)
        if char_id in self.TEAM_ALIASES:
            self._buff_ap_used = True
        self._counsel_log.append({"actor": actor, "char_id": char_id,
                                  "card_id": card_id, "matched": True, "effect": effect})
        golden = card.get("golden_lines", [])
        hint = (f"用《{card.get('title', card_id)}》（{card.get('author', '')}）开导 {char_id}："
                f"先专业后破防，结尾化用金句「{golden[0] if golden else ''}」。")
        if rescue:
            hint += "（急诊室抢救成功：收益×2，红灯熄灭）"
        # 知之者双卡彩蛋：目标角色被两张不同卡都开导成功 → 额外弹幕提示
        if len([c for c in self._counsel_log
                if c.get("matched") and c.get("char_id") == char_id]) >= 2:
            hint += "（彩蛋：同一人被两张卡先后开导，弹幕炸了）"
        return {"matched": True, "effect": effect, "unlocked": unlocked,
                "transcript_hint": hint, "first_time": first_time,
                "er_rescue": rescue}

    def _is_group_target(self, target: str) -> bool:
        """是否团队/档案局等非 NPC 开导对象（不计入心晴诊室 counsel_count）。"""
        return target in self.TEAM_ALIASES or target in self.ARCHIVE_ALIASES

    def _resolve_effect(self, effect: str, card: dict, char_id: str) -> dict | None:
        if effect == "memory_unlock":
            return {"type": "memory_unlock", "char_id": card.get("binds", char_id)}
        if effect == "evidence":
            # 水军线关键证据等：上层将 card_id 对接到 unlock_condition="counsel:<kc_id>"
            return {"type": "evidence", "char_id": card.get("binds", char_id),
                    "card_id": card.get("id")}
        if effect == "buff_ap":
            return {"type": "buff_ap", "ap": 1, "note": "团队 buff「合群又独立」+1AP（一次性）"}
        if effect == "plot_fragment":
            return {"type": "plot_fragment", "card_id": card.get("id"),
                    "count": len([c for c in self._counsel_log
                                  if c.get("matched") and c.get("effect") == "plot_fragment"])}
        if effect == "boss_key":
            return {"type": "boss_key", "char_id": card.get("binds", char_id),
                    "note": "隐藏真结局钥匙"}
        return {"type": effect, "char_id": char_id, "card_id": card.get("id")}

    # --------------------------------------------------------------- refute
    def refute_allowed(self, card_id: str, topic_tag: str) -> bool:
        """辟谣弹药校验（供 opinion_feed 调用）。卡存在且 topic_tag 匹配才生效。"""
        card = self._cards.get(card_id)
        return bool(card) and str(card.get("topic_tag", "")).strip() == str(topic_tag).strip()

    # --------------------------------------------------------------- clinic
    def clinic_settlement(self) -> dict:
        """心晴诊室结算：{counsel_count, ending_modifier, hidden_unlock}。

        counsel_count = 开导成功的 NPC 数（去重）；
        0-1 → normal（普通结局）；2-3 → archive_show（心晴档案放映）；
        4+ → all_hearts_clear（隐藏结局「全员心晴」，hidden_unlock=True）。
        """
        n = len(self._counseled_chars)
        if n >= 4:
            modifier, hidden = "all_hearts_clear", True
        elif n >= 2:
            modifier, hidden = "archive_show", False
        else:
            modifier, hidden = "normal", False
        boss_keys = [c for c in self._counsel_log if c.get("matched") and c.get("effect") == "boss_key"]
        return {"counsel_count": n, "ending_modifier": modifier, "hidden_unlock": hidden,
                "detail": {"boss_key_gained": len(boss_keys) > 0,
                           "buff_ap_gained": self._buff_ap_used,
                           "records": list(self._counsel_log)}}

    # ---------------------------------------------------------------- extras
    def held_cards(self) -> list[dict]:
        """全队当前持有的知识卡（图鉴展示）。"""
        return [self._cards[cid] for cid in sorted(self._held)]

    def card(self, card_id: str) -> dict | None:
        return self._cards.get(card_id)
