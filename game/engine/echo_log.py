"""echo_log — 回声证据引擎（S1 创新机制：玩家说过的话成为终局武器）

契约：docs/CONTRACTS.md §3.2（记忆系扩展）；设计：本文件头部注释即最新口径。
职责（确定性裁决，禁止 AI 参与）：
- 全程记录**玩家自己的原话**（不只是引擎生成的演出底稿）；
- 终局由 DM（看山）挑出玩家前后矛盾的两句话当庭投影，构陷玩家证词不可信；
- 玩家可「引自证」：指出自己究竟哪两句互相矛盾（或证明自己前后一致）；
- 自证成功 → 释放线索 clue_033 并返还 1 AP；失败 → 被 DM 记一笔（记入档案）。

为什么是 AI 原生：真人 DM 无法在全过程中零成本留存并即时复用玩家的每一句话，
只有 AI 主持的游戏才能做到「你喂给它的，最后变成它对付你的证据」——
这也是本作主题的最后一块拼图：信息操纵不只发生在剧情里，也发生在你与 AI 之间。
"""
from __future__ import annotations

import time

#: 立场极性词表（确定性判定，勿随意增删——会改变矛盾检测结果）
POSITIVE = ("相信", "信任", "清白", "没问题", "靠谱", "支持", "没错", "可信", "我信")
NEGATIVE = ("怀疑", "不信", "有鬼", "凶手", "撒谎", "假的", "不对", "可疑", "骗", "我疑")
#: 断言词（用于挑出「说得很满」的那句话）
ASSERTIVE = ("一定", "肯定", "绝对", "就是", "必然", "百分百", "我确定", "毫无疑问")


class EchoLog:
    def __init__(self) -> None:
        self._items: list[dict] = []
        self._seq = 0

    # ------------------------------------------------------------------- add
    def add(self, actor: str, text: str, target: str = "", round_no: int = 1) -> dict | None:
        """记录一句玩家原话。空白/过短不记；返回带 idx 的条目。"""
        t = (text or "").strip()
        if not t or len(t) < 2:
            return None
        self._seq += 1
        item = {"idx": self._seq, "actor": actor, "text": t[:500],
                "target": str(target or "").replace("npc:", "").strip(),
                "round": round_no, "ts": round(time.time(), 3)}
        self._items.append(item)
        return item

    # ------------------------------------------------------------------- log
    def log(self, actor: str | None = None) -> list[dict]:
        return [dict(i) for i in self._items
                if actor is None or i["actor"] == actor]

    # -------------------------------------------------------- contradictions
    def _polarity(self, text: str) -> str:
        if any(w in text for w in POSITIVE):
            return "pos"
        if any(w in text for w in NEGATIVE):
            return "neg"
        return ""

    def contradictions(self, actor: str | None = None) -> list[dict]:
        """检测同一对象上「先信后疑」或「先疑后信」的矛盾对（确定性）。

        返回 [{a: idx, b: idx, target, a_text, b_text, reason}]
        """
        items = self.log(actor)
        out: list[dict] = []
        for i, x in enumerate(items):
            px = self._polarity(x["text"])
            if not px:
                continue
            for y in items[i + 1:]:
                if x["target"] and y["target"] and x["target"] != y["target"]:
                    continue
                py = self._polarity(y["text"])
                if not py or py == px:
                    continue
                out.append({
                    "a": x["idx"], "b": y["idx"],
                    "target": x["target"] or y["target"],
                    "a_text": x["text"], "b_text": y["text"],
                    "reason": (f"你先说「{x['text'][:24]}」，后又说「{y['text'][:24]}」"
                               f"——同一件事，两种立场。"),
                })
        return out

    def assertive_lines(self, actor: str | None = None, n: int = 3) -> list[dict]:
        """挑出玩家说得最满的几句话（DM 构陷素材）。"""
        items = [i for i in self.log(actor) if any(w in i["text"] for w in ASSERTIVE)]
        items.sort(key=lambda i: -len(i["text"]))
        return items[:n]

    # ------------------------------------------------------------- challenge
    def challenge(self, actor: str) -> dict:
        """终局 DM 攻击：挑出一组矛盾（或断言句）投影到玩家面前。

        返回 {mode: "contradiction" | "assertion" | "empty",
              pair, candidates:[{idx,text}], text}
        """
        pairs = self.contradictions(actor)
        if pairs:
            p = pairs[0]
            cands = [i for i in self.log(actor)
                     if i["idx"] in (p["a"], p["b"])][:2]
            # 混入一条无关的干扰项（若有）
            noise = [i for i in self.log(actor)
                     if i["idx"] not in (p["a"], p["b"])][:1]
            return {"mode": "contradiction", "pair": p,
                    "candidates": [{"idx": i["idx"], "text": i["text"],
                                    "round": i["round"]} for i in cands + noise],
                    "text": (f"看山把你说过的话投影在墙上：「{p['a_text'][:30]}」"
                             f"……可你后来又说「{p['b_text'][:30]}」。"
                             "你连自己都前后不一，凭什么指认我？")}
        lines = self.assertive_lines(actor, 3)
        if lines:
            return {"mode": "assertion",
                    "candidates": [{"idx": i["idx"], "text": i["text"],
                                    "round": i["round"]} for i in lines],
                    "text": (f"看山念出你最笃定的那句：「{lines[0]['text'][:30]}」。"
                             "「现在，你还敢这么说吗？」")}
        return {"mode": "empty", "candidates": [], "pair": None,
                "text": "（你几乎没留下可以被引用的话——看山找不到攻击你的材料。）"}

    # ---------------------------------------------------------------- defend
    def defend(self, actor: str, picks: list[int]) -> dict:
        """玩家引自证：指出自己矛盾的两句（mode=contradiction 时）。

        返回 {ok, passed, mode, reason, transcript_hint}
        - 有矛盾对且选中正确一对 → passed=True（自证：承认并解释自己的动摇）
        - 无矛盾对（前后一致）→ passed=True（一致性加成）
        - 选错 → passed=False
        """
        pairs = self.contradictions(actor)
        if not pairs:
            return {"ok": True, "passed": True, "mode": "consistent",
                    "reason": "全场检索完毕：你的每一句话都前后一致，看山挑不出矛盾。",
                    "transcript_hint": ("自证成功：翻遍回声档案，你没有自相矛盾过——"
                                        "在一个人人改口的游戏里，保持一致本身就是证据。")}
        picked = {int(p) for p in (picks or []) if str(p).lstrip("-").isdigit()}
        hit = next((p for p in pairs if {p["a"], p["b"]} == picked), None)
        if hit:
            return {"ok": True, "passed": True, "mode": "contradiction",
                    "reason": hit["reason"],
                    "transcript_hint": (
                        f"自证成功：你承认了自己动摇过——「{hit['a_text'][:20]}」到"
                        f"「{hit['b_text'][:20]}」。承认被带过节奏，才是求真的起点。")}
        return {"ok": True, "passed": False, "mode": "contradiction",
                "reason": "你指的不是真正互相矛盾的那两句。",
                "transcript_hint": (
                    "自证失败：你指出的两句并不矛盾，看山笑着把这一段也记进了档案——"
                    "「连自己说过什么都找不准的人，怎么找真相？」")}

    # --------------------------------------------------------------- summary
    def summary(self, actor: str | None = None) -> dict:
        items = self.log(actor)
        return {"lines": len(items),
                "contradictions": len(self.contradictions(actor)),
                "assertive": len(self.assertive_lines(actor, 9)),
                "longest": max((len(i["text"]) for i in items), default=0)}
