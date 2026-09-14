"""从钩子/构思生成一本完整快本圣经。

配额锁死（4 人 / 6 地 / 12 证 / 6 节点 / 3 幕），案情、人名、地名、
线索 fact、记忆和热搜帖随种子与本型变，不再套同一套「热榜机房七分钟」。
"""

from __future__ import annotations

from ..brief import TYPE_META, normalize_brief
from ..tiers import KC_COPY
from . import extract, narrative
from .lexicon import PACK_DEFAULTS


def build(seed: str, *, inner_boss: bool = False, brief: dict | None = None) -> dict:
    brief_n = normalize_brief(brief, seed)
    hook = brief_n.get("hook") or (seed or "").split("\n", 1)[0].strip()
    hook = " ".join(hook.split()) or "有人把今晚的记录挖走了一截"
    pack = brief_n.get("pack_type") or "fun_mech"
    if pack not in PACK_DEFAULTS:
        pack = "fun_mech"
    mood = (brief_n.get("vibe") or {}).get("mood") or "comedy"
    return _assemble(hook, brief_n, pack, mood, bool(inner_boss))


def _assemble(hook: str, brief: dict, pack: str, mood: str, inner_boss: bool) -> dict:
    defaults = PACK_DEFAULTS[pack]
    lock = brief.get("lock") or {}
    truth = brief.get("truth") or {}
    vibe = brief.get("vibe") or {}
    camp = brief.get("camp") or {}

    space = extract.place(hook, lock.get("space") or "", defaults["room"])
    obj = extract.object_name(hook, truth, defaults["object"])
    window = extract.window(hook, lock.get("timebox") or "")
    device = extract.device(hook, pack, defaults["device"])
    verb = extract.verb(hook, obj, truth.get("crime") or "", defaults["verb"])
    leftover = extract.leftover(hook, pack, defaults["leftover"])
    signal = extract.signal(hook, pack, defaults["signal"])
    times = extract.times(lock.get("timebox") or "")
    names, arches, bios, hooks = extract.cast(brief.get("cast") or [], obj, pack, mood)
    locs = extract.places(space, pack)
    quote = hook[:22]
    lock_rule = (lock.get("lock_rule") or "").strip() or "不出真相，不出此门"
    theme = (lock.get("theme") or "").strip() or extract.theme(pack, obj)
    player_crime = (truth.get("crime") or "").strip()
    player_motive = (truth.get("motive") or "").strip()
    player_method = (truth.get("method") or "").strip()
    player_surface = (truth.get("surface") or "").strip()
    notes = (brief.get("board_notes") or "").strip()
    crime = player_crime or f"指使{names['char_02']}{verb}{obj}，并嫁祸{names['char_03']}"
    motive = player_motive or f"怕{obj}被翻出来，自己先被点名"
    method = player_method or (
        f"让{names['char_02']}在 {times['crime']} 用内部工具{verb}{obj}，"
        f"暗号是「{signal}」，再投放一条栽给{names['char_03']}的伪证"
    )
    surface = player_surface or (
        f"{names['char_01']}指使被裹挟的{names['char_02']}{verb}{obj}，"
        f"并试图把锅扣给{names['char_03']}"
    )
    title_bit = (lock.get("space") or space or obj)[:10]
    title = f"求真档案局 · {title_bit}"
    logline = extract.logline(hook, mood, space, obj, window)
    meta = TYPE_META.get(pack) or TYPE_META["fun_mech"]

    clue_rows = narrative.clues(
        locs, names, obj, window, device, verb, leftover, signal, quote,
        lock_rule, times, notes, player_crime,
    )
    loc_rows = narrative.loc_rows(locs, clue_rows, hook)
    memories = narrative.memories(names, locs, obj, verb, leftover, signal, device, times, window)
    posts = narrative.posts(hook, names, obj, device, window, leftover, mood)
    timeline = narrative.timeline(names, locs, obj, verb, leftover, device, times)
    acts = narrative.acts(brief.get("acts") or [], pack, hook, obj, device, names, brief)
    chars = narrative.characters(
        names, arches, bios, hooks, obj, verb, leftover, signal, device, times, locs, mood, quote,
    )
    kc_plan = [{"id": a, "binds": b} for a, b in KC_COPY]

    world = {
        "title": title,
        "logline": logline,
        "genre": meta["genre"],
        "tone": (lock.get("tone") or "").strip() or meta["tone"],
        "hook": hook,
        "world_rules": [
            "AI 不得捏造未写入 fact 的证据",
            "口供与心声不一致处才是篡改点",
            f"{device}落下之后，出口只认证据不认口号",
        ],
        "surface_truth": surface,
        "inner_truth": (
            f"{device}的签发源不在四人之中，而在局内预埋的压力测试脚本（快本不展开人物）"
            if inner_boss else None
        ),
        "theme": theme,
        "cast_slots": [
            {"id": cid, "name": names[cid], "archetype": arches[cid],
             "faction": fac, "comedy_hook": hooks[cid]}
            for cid, fac in (
                ("char_01", "pollution"),
                ("char_02", "swayable"),
                ("char_03", "truth"),
                ("char_04", "truth"),
            )
        ],
        "locations": loc_rows,
        "comedy_sources": extract.comedy(mood, vibe),
        "safety": "角色均为虚构拟人，不映射真实用户。",
    }
    if camp:
        world["world_rules"].append(
            f"阵营称呼：{camp.get('pollution') or '污染'} / "
            f"{camp.get('swayable') or '可策反'} / {camp.get('truth') or '求真'}"
        )

    detail = {
        "characters": chars,
        "timeline": timeline,
        "truth_nodes": [
            {"id": "tn_01", "name": f"{device}落下", "desc": f"{device}与侧门令牌同一秒生效",
             "proof_clues": ["clue_001", "clue_009"]},
            {"id": "tn_02", "name": f"{obj}被动过", "desc": f"{window}的空洞来自内部{verb}",
             "proof_clues": ["clue_003", "clue_004"]},
            {"id": "tn_03", "name": f"{names['char_03']}的矛盾", "desc": "打卡与口供对不上",
             "proof_clues": ["clue_005", "clue_006"]},
            {"id": "tn_04", "name": "备份被动过", "desc": f"{obj}备份被借走且时间戳被改",
             "proof_clues": ["clue_007", "clue_008"]},
            {"id": "tn_05", "name": "同一只手", "desc": f"{verb}账号与舆论设备同源",
             "proof_clues": ["clue_011", "clue_010"]},
            {"id": "tn_06", "name": "主谋身份", "desc": f"离席窗口对上{names['char_01']}",
             "proof_clues": ["clue_002", "clue_003"]},
        ],
        "culprit": {
            "character": "char_01",
            "name": names["char_01"],
            "crime": crime,
            "motive": motive,
            "method": method,
            "accomplices": [
                {"character": "char_02", "name": names["char_02"],
                 "role": "被裹挟者", "swayable": True}
            ],
            "evidence_chain": ["clue_003", "clue_011", "clue_002"],
        },
        "clues": clue_rows,
        "memories": memories,
        "hotfeed": posts,
        "kc_plan": kc_plan,
    }
    return {"world": world, "detail": detail, "acts": acts}
