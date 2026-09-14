"""judge_debate — AI 法官辩论引擎（S4 创新机制：终局不是投票，是说服一个会被带偏的 AI 法官）

契约：docs/CONTRACTS.md §3.5（裁决系扩展）；设计：本文件头部注释即最新口径。
职责（确定性裁决，禁止 AI 参与打分）：
- 终局环节由 AI 法官（JudgeAgent）主持，**打分与立场迁移完全由本模块确定性计算**；
  AI 只负责把裁决结果翻译成法官台词（骨架由 transcript_hint 提供，AI 不改判）；
- 法官会被「带偏」：热度越高，法官初始立场越怀疑玩家（舆论真的能影响裁判）；
- 玩家多轮陈词：引用证据/引用知乎知识卡/承认自己动摇过 → 加分；
  灌水、情绪化辱骂、车轱辘话 → 扣分；
- 累计达标 → 法官采信（stance=convinced），释放线索 clue_034。

为什么是 AI 原生：真人法官不可能被玩家逐轮说服并实时改写立场，
而「一个会被舆论带偏的 AI 裁判」本身就是本作主题的镜像——
我们正在把判断权交给算法，这正是本案要审判的事。
"""
from __future__ import annotations

#: 情绪化辱骂词表（扣分：法官不采信情绪，只采信证据）
ABUSE = ("傻", "蠢", "废物", "去死", "滚", "脑残", "智障", "闭嘴", "垃圾")
#: 自证词（承认自己动摇过，契合 S1 回声机制）
SELF_REFLECT = ("我承认", "我曾经", "我改口", "我说过", "我动摇", "我错了", "我之前")
#: 灌水判定长度
MIN_MEANINGFUL = 8

STANCE_ORDER = {"hostile": 0, "skeptical": 1, "open": 2, "convinced": 3}


class JudgeDebate:
    #: 采信阈值（累计分）
    CONVINCE_SCORE = 4
    #: 单次陈词得分上下限
    MAX_GAIN, MAX_LOSS = 3, -2

    def __init__(self) -> None:
        self._total = 0
        self._rounds: list[dict] = []
        self._stance = "open"
        self._convinced = False

    # ------------------------------------------------------------------ open
    def open_case(self, heat: int) -> dict:
        """法官开场：热度决定初始立场（舆论真的能影响裁判）。"""
        if heat >= 60:
            self._stance = "skeptical"
            text = ("法官敲了敲桌面：热搜上全是你的负面消息——"
                    "在本庭，声量也是一种证词。请陈词。")
        elif heat >= 30:
            self._stance = "open"
            text = "法官抬眼：舆论场杂音不小，但本庭仍愿听你陈述。请陈词。"
        else:
            self._stance = "open"
            text = "法官点头：案卷干净，本庭愿意听你说话。请陈词。"
        return {"stance": self._stance, "score": self._total,
                "need": self.CONVINCE_SCORE, "text": text,
                "rounds_used": len(self._rounds)}

    # ---------------------------------------------------------------- submit
    def submit(self, actor: str, claim: str, ctx: dict | None = None) -> dict:
        """提交一轮陈词（确定性打分）。

        ctx: {evidence_terms:[...], card_titles:[...], echo_ok:bool, heat:int}
        返回 {gain, total, stance, convinced, reasons[], transcript_hint}
        """
        ctx = ctx or {}
        text = (claim or "").strip()
        reasons: list[str] = []
        gain = 0

        if len(text) < MIN_MEANINGFUL:
            return {"gain": -1, "total": self._total, "stance": self._stance,
                    "convinced": self._convinced, "reasons": ["陈词过短，法官视为敷衍"],
                    "transcript_hint": "法官皱眉：「这不是陈词，这是打卡。」（本轮不计）"}

        ev_terms = [t for t in (ctx.get("evidence_terms") or []) if t]
        if any(t in text for t in ev_terms):
            gain += 2
            reasons.append("引用了卷宗里的实证")
        cards = [t for t in (ctx.get("card_titles") or []) if t]
        if any(t in text for t in cards):
            gain += 1
            reasons.append("引用了知乎答主的专业意见")
        if ctx.get("echo_ok") and any(w in text for w in SELF_REFLECT):
            gain += 1
            reasons.append("承认自己曾被带过节奏——诚实也是证据")
        if any(w in text for w in ABUSE):
            gain -= 1
            reasons.append("情绪化表述，法官不予采信")
        if self._is_repeat(text):
            gain -= 1
            reasons.append("与上一轮陈词高度重复，法官失去耐心")

        gain = max(self.MAX_LOSS, min(self.MAX_GAIN, gain))
        self._total = max(0, self._total + gain)
        self._rounds.append({"actor": actor, "text": text[:300], "gain": gain})
        self._update_stance()
        return {"gain": gain, "total": self._total, "stance": self._stance,
                "convinced": self._convinced, "reasons": reasons,
                "transcript_hint": self._hint(gain, reasons)}

    def _is_repeat(self, text: str) -> bool:
        if not self._rounds:
            return False
        prev = self._rounds[-1].get("text", "")
        if not prev:
            return False

        def grams(s: str, n: int = 2) -> set:
            return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}

        a, b = grams(text), grams(prev)
        if not a or not b:
            return False
        return len(a & b) / len(a | b) > 0.6

    def _update_stance(self) -> None:
        if self._total >= self.CONVINCE_SCORE:
            self._stance, self._convinced = "convinced", True
        elif self._total > 0:
            self._stance = "open"
        else:
            self._stance = "skeptical"

    def _hint(self, gain: int, reasons: list[str]) -> str:
        head = ("本轮 +%d 分" % gain) if gain >= 0 else ("本轮 %d 分" % gain)
        why = "；".join(reasons) if reasons else "法官未置可否"
        if self._convinced:
            return (f"{head}（{why}）。法官放下笔：「证据链成立，本庭采信你的陈述。」"
                    "——线索「法官采信」已入卷宗。")
        if self._stance == "skeptical":
            return f"{head}（{why}）。法官摇头：「情绪与重复不是证据，请继续。」"
        return f"{head}（{why}）。法官记录中，距离采信还需 {max(0, self.CONVINCE_SCORE - self._total)} 分。"

    # --------------------------------------------------------------- summary
    def summary(self) -> dict:
        return {"score": self._total, "stance": self._stance,
                "convinced": self._convinced, "rounds": len(self._rounds),
                "need": self.CONVINCE_SCORE}
