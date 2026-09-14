"""truth_profile — 求真相画像（S3：通关生成可分享的媒介素养诊断卡）

契约：docs/CONTRACTS.md §3.7（结算系扩展）；设计：本文件头部注释即最新口径。
职责（确定性计算，禁止 AI 参与评分）：
- 结算时基于整局真实行为生成五维画像（严谨/怀疑/共情/勇气/独立）；
- 输出人格原型 + 一句判词 + 三条高光行为 + 可分享文案；
- 前端据此渲染竖版卡片并支持下载（分享即传播，也服务社区人气）。

设计意图：把「玩过一局剧本杀」变成「拿到一份关于自己的诊断」——
这才是本作对社区用户的实际价值：媒介素养不是口号，是你这一局打出来的分数。
"""
from __future__ import annotations

ARCHETYPES = {
    "流量操盘手": "你很懂流量怎么运作——正因如此，你比谁都清楚水军是怎么赢的。",
    "追光者": "你指认了主持人。在所有人都看向嫌疑人的时候，你抬头看向了那个递给你线索的人。",
    "求真派": "你不轻信任何一句通顺的话，包括对你有利的那句。这是求真的基本功。",
    "心晴派": "你把行动点花在了别人的心上。真相之外，你也救了几个人的这一夜。",
    "稳健调查员": "你不抢风头，但卷宗里每一条实证都有你的签名。",
    "见习档案员": "第一夜而已。档案局的大门永远为还想再查一次的人开着。",
}


def _pct(v: float) -> int:
    return int(max(0, min(100, round(v))))


def build(ctx: dict | None = None) -> dict:
    """ctx 字段（全部可选，缺失按 0 处理）：
    {clue_count, coverage(0-1), pollution:{passed,total,ammo}, refutes, buy_heats,
     counsel_count, echo:{lines,contradictions,defended}, debate:{score,convinced},
     accused_dm, ending, heat}
    """
    c = ctx or {}
    pol = c.get("pollution") or {}
    echo = c.get("echo") or {}
    debate = c.get("debate") or {}

    clue_count = int(c.get("clue_count") or 0)
    coverage = float(c.get("coverage") or 0.0)
    pol_total = int(pol.get("total") or 0)
    pol_passed = int(pol.get("passed") or 0)
    refutes = int(c.get("refutes") or 0)
    buy_heats = int(c.get("buy_heats") or 0)
    counsel = int(c.get("counsel_count") or 0)
    accused_dm = bool(c.get("accused_dm"))
    heat = int(c.get("heat") or 0)

    rigor = _pct(coverage * 70 + min(clue_count, 12) / 12 * 30)
    skepticism = _pct(
        (pol_passed / pol_total * 60 if pol_total else 0)
        + min(refutes, 3) / 3 * 25
        + (15 if int(pol.get("ammo_earned") or pol.get("ammo") or 0) > 0 else 0)
    )
    empathy = _pct(min(counsel, 5) / 5 * 100)
    courage = _pct((40 if accused_dm else 0)
                   + (30 if debate.get("convinced") else 0)
                   + (30 if echo.get("defended") else 0))
    independence = _pct(100 - buy_heats * 25 - max(0, heat - 50) * 0.6)

    if buy_heats >= 2:
        arch = "流量操盘手"
    elif accused_dm and debate.get("convinced"):
        arch = "追光者"
    elif skepticism >= 70:
        arch = "求真派"
    elif empathy >= 60:
        arch = "心晴派"
    elif rigor >= 60:
        arch = "稳健调查员"
    else:
        arch = "见习档案员"

    highlights = _highlights(clue_count, pol_passed, pol_total, refutes, buy_heats,
                             counsel, echo, debate, accused_dm, heat)
    scores = {"rigor": rigor, "skepticism": skepticism, "empathy": empathy,
              "courage": courage, "independence": independence}
    overall = _pct(sum(scores.values()) / len(scores))
    return {
        "archetype": arch,
        "archetype_desc": ARCHETYPES[arch],
        "scores": scores,
        "overall": overall,
        "verdict": _verdict(arch, scores, heat),
        "highlights": highlights,
        "share": {
            "title": f"我在《求真档案局》的求真画像：{arch}",
            "lines": [
                f"综合求真力 {overall} 分",
                f"严谨 {rigor} · 怀疑 {skepticism} · 共情 {empathy} · 勇气 {courage} · 独立 {independence}",
                ARCHETYPES[arch],
            ],
        },
        "ending": c.get("ending", ""),
    }


def _verdict(arch: str, s: dict, heat: int) -> str:
    tail = "（本局舆论热度 %d，你的判断没有被声量牵着走。）" % heat if heat < 40 else \
           "（本局舆论热度 %d——注意：热度越高，越难保持独立。）" % heat
    return f"{ARCHETYPES[arch]} {tail}"


def _highlights(clue_count: int, pol_passed: int, pol_total: int, refutes: int,
                buy_heats: int, counsel: int, echo: dict, debate: dict,
                accused_dm: bool, heat: int) -> list[str]:
    out: list[str] = []
    if pol_total and pol_passed:
        out.append(f"识破 {pol_passed}/{pol_total} 条被改写的知乎回答——你能在「看起来很像原文」的话里认出操纵")
    if refutes:
        out.append(f"完成 {refutes} 次有效辟谣：用专业回答对冲了水军话术")
    if echo.get("defended"):
        out.append("你承认了自己前后矛盾过——在被 AI 用你自己的话反将一军时，你没抵赖")
    elif echo.get("contradictions"):
        out.append(f"回声档案记录了 {echo['contradictions']} 处你前后不一的发言（下次可以更稳）")
    if debate.get("convinced"):
        out.append(f"说服了那个被舆论带偏的 AI 法官（陈词 {debate.get('score', 0)} 分）")
    if accused_dm:
        out.append("你指认了主持人刘看山——本作最难的一个选择")
    if counsel >= 3:
        out.append(f"开导了 {counsel} 位角色：查案之外，你没把人当工具")
    if buy_heats:
        out.append(f"你买过 {buy_heats} 次热搜——操纵流量的手段你也会用，只是你选择拿它换真相")
    if not out:
        out.append("这一局你走完了全流程：在一个人人改口的夜里，你至少没有中途离场")
    return out[:3]
