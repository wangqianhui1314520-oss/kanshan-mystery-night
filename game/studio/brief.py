"""玩家构思稿：叠进圣经，不改引擎 id / 配额 / 动词。

目录常量在 catalog.py。本文件只做 normalize / compose / apply。
"""

from __future__ import annotations

import re

from .catalog import (
    ACT_IDS,
    CAST_IDS,
    DEFAULT_CAMP,
    DEFAULT_MODULES,
    MINI_IDS,
    PACK_TYPES,
    TYPE_META,
    VIBE_MOODS,
)

_SPLIT = re.compile(r"[,，、/;；]+")

__all__ = [
    "ACT_IDS",
    "CAST_IDS",
    "DEFAULT_CAMP",
    "DEFAULT_MODULES",
    "MINI_IDS",
    "PACK_TYPES",
    "TYPE_META",
    "VIBE_MOODS",
    "apply_brief",
    "compose_seed",
    "default_modules",
    "normalize_brief",
]


def _txt(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def _split_list(v) -> list[str]:
    if isinstance(v, (list, tuple)):
        return [_txt(x) for x in v if _txt(x)]
    return [p.strip() for p in _SPLIT.split(_txt(v)) if p.strip()]


def default_modules() -> dict:
    return dict(DEFAULT_MODULES)


def normalize_brief(brief, seed: str = "") -> dict:
    src = brief if isinstance(brief, dict) else {}
    hook = _txt(src.get("hook")) or _txt(seed)
    lock_src = src.get("lock") if isinstance(src.get("lock"), dict) else {}
    truth_src = src.get("truth") if isinstance(src.get("truth"), dict) else {}
    voice_src = src.get("voice") if isinstance(src.get("voice"), dict) else {}
    vibe_src = src.get("vibe") if isinstance(src.get("vibe"), dict) else {}
    camp_src = src.get("camp") if isinstance(src.get("camp"), dict) else {}
    mods_src = src.get("modules") if isinstance(src.get("modules"), dict) else {}

    pack_type = _txt(src.get("pack_type")) or "fun_mech"
    if pack_type not in PACK_TYPES:
        pack_type = "fun_mech"

    mood = _txt(vibe_src.get("mood")) or _txt(src.get("mood"))
    if mood not in VIBE_MOODS:
        mood = "horror" if pack_type == "horror" else (
            "variety" if pack_type in ("variety", "faction") else (
                "grim" if pack_type in ("hard_logic", "emotion", "immerse") else "comedy"
            )
        )

    cast_by_id = {}
    for row in src.get("cast") or []:
        if isinstance(row, dict) and row.get("id") in CAST_IDS:
            cast_by_id[row["id"]] = row
    cast = []
    for cid in CAST_IDS:
        row = cast_by_id.get(cid) or {}
        cast.append({
            "id": cid,
            "name": _txt(row.get("name")),
            "archetype": _txt(row.get("archetype")),
            "comedy_hook": _txt(row.get("comedy_hook")),
            "public_bio": _txt(row.get("public_bio")),
        })

    act_by_id = {}
    for row in src.get("acts") or []:
        if isinstance(row, dict) and row.get("id") in ACT_IDS:
            act_by_id[row["id"]] = row
    acts = []
    for aid in ACT_IDS:
        row = act_by_id.get(aid) or {}
        acts.append({
            "id": aid,
            "name": _txt(row.get("name")),
            "brief": _txt(row.get("brief")),
            "must_reveal": _split_list(row.get("must_reveal")),
            "must_not_reveal": _split_list(row.get("must_not_reveal")),
            "twist": _txt(row.get("twist") or row.get("twist_beat")),
            "comedy": _txt(row.get("comedy") or row.get("comedy_beat")),
        })

    modules = default_modules()
    for key in modules:
        if key in mods_src:
            modules[key] = bool(mods_src[key])

    minis = []
    raw_minis = src.get("minis")
    if isinstance(raw_minis, (list, tuple)):
        for mid in raw_minis:
            mid = _txt(mid)
            if mid in MINI_IDS and mid not in minis:
                minis.append(mid)

    camp = dict(DEFAULT_CAMP)
    for key in camp:
        if key == "public":
            if "public" in camp_src:
                camp["public"] = bool(camp_src["public"])
        elif camp_src.get(key):
            camp[key] = _txt(camp_src[key])

    dm = _txt(vibe_src.get("dm")) or _txt(voice_src.get("dm"))
    comedy = _txt(vibe_src.get("comedy")) or _txt(voice_src.get("comedy"))

    return {
        "hook": hook,
        "pack_type": pack_type,
        "lock": {
            "timebox": _txt(lock_src.get("timebox")),
            "space": _txt(lock_src.get("space")),
            "lock_rule": _txt(lock_src.get("lock_rule")),
            "win": _txt(lock_src.get("win")),
            "tone": _txt(lock_src.get("tone")),
            "theme": _txt(lock_src.get("theme")),
        },
        "camp": camp,
        "cast": cast,
        "truth": {
            "surface": _txt(truth_src.get("surface")),
            "crime": _txt(truth_src.get("crime")),
            "motive": _txt(truth_src.get("motive")),
            "method": _txt(truth_src.get("method")),
        },
        "board_notes": _txt(src.get("board_notes")),
        "acts": acts,
        "modules": modules,
        "minis": minis,
        "vibe": {
            "mood": mood,
            "horror_beats": _txt(vibe_src.get("horror_beats")),
            "dm": dm,
            "comedy": comedy,
        },
        "voice": {"dm": dm, "comedy": comedy},
    }


def compose_seed(brief: dict) -> str:
    """钩子必须在第一行，案情工厂用这一句抽取物件、空间和锁局。"""
    b = normalize_brief(brief, "")
    parts = [b["hook"] or ""]
    parts.append(f"本型：{b['pack_type']} 氛围：{b['vibe']['mood']}")
    lock = b["lock"]
    lock_bits = []
    for key, label in (
        ("timebox", "时间"),
        ("space", "空间"),
        ("lock_rule", "锁局"),
        ("win", "胜利"),
        ("tone", "语气"),
        ("theme", "主题"),
    ):
        if lock.get(key):
            lock_bits.append(f"{label}={lock[key]}")
    if lock_bits:
        parts.append("锁局：" + "；".join(lock_bits))

    camp = b["camp"]
    parts.append(
        "阵营："
        + f"{camp['pollution']}/{camp['swayable']}/{camp['truth']}"
        + (" 公开" if camp["public"] else " 隐藏")
    )
    if camp.get("win_pollution") or camp.get("win_truth"):
        parts.append(
            "阵营胜："
            + "；".join(x for x in (camp.get("win_pollution"), camp.get("win_truth")) if x)
        )

    named = [f"{c['id']} {c['name']}/{c['archetype']}" for c in b["cast"] if c["name"] or c["archetype"]]
    if named:
        parts.append("入座：" + "，".join(named))

    truth = b["truth"]
    truth_bits = [truth[k] for k in ("surface", "crime", "motive", "method") if truth.get(k)]
    if truth_bits:
        parts.append("真相：" + "；".join(truth_bits))

    if b["board_notes"]:
        parts.append("场与证：" + b["board_notes"])

    act_bits = []
    for a in b["acts"]:
        if a["name"] or a["brief"]:
            act_bits.append(f"{a['id']} {a['name']} {a['brief']}".strip())
    if act_bits:
        parts.append("幕表：" + " / ".join(act_bits))

    on = [k for k, v in b["modules"].items() if v]
    if on:
        parts.append("机制：" + " ".join(on))
    if b["minis"]:
        parts.append("小游戏：" + " ".join(b["minis"]))

    vibe = b["vibe"]
    if vibe["horror_beats"] or vibe["dm"] or vibe["comedy"]:
        parts.append(
            "氛围："
            + " ".join(x for x in (vibe["horror_beats"], vibe["dm"], vibe["comedy"]) if x)
        )

    return "\n".join(p for p in parts if p).strip()


def apply_brief(world: dict, detail: dict, acts, brief: dict) -> None:
    """只覆盖玩家写过的文字。不改 faction / stage / AP / 动词 / 地点中文名。"""
    if not world or not detail:
        return
    b = normalize_brief(brief, "")
    lock = b["lock"]
    hook = b["hook"]
    meta = TYPE_META.get(b["pack_type"]) or TYPE_META["fun_mech"]

    world["genre"] = meta["genre"]
    if lock.get("tone"):
        world["tone"] = lock["tone"]
    else:
        world["tone"] = meta["tone"]
    if b["vibe"]["mood"] == "horror" and not lock.get("tone"):
        world["tone"] = "封闭空间恐怖"

    if hook and len(hook) >= 6:
        world.setdefault("hook", hook)
        if lock.get("space"):
            world["title"] = f"求真档案局 · {lock['space'][:10]}"
        elif not world.get("title"):
            world["title"] = f"求真档案局 · {hook[:10]}"
        if not world.get("logline"):
            if b["vibe"]["mood"] == "horror":
                world["logline"] = f"「{hook[:36]}」——灯灭之后，必须有人先承认看见了不该看见的。"
            else:
                world["logline"] = (
                    f"「{hook[:36]}」——被锁在局里的人，必须在热闹把真相淹死之前抓住那只手。"
                )

    if lock.get("theme"):
        world["theme"] = lock["theme"]

    extras = []
    if lock.get("timebox"):
        extras.append(f"时间盒：{lock['timebox']}")
    if lock.get("space"):
        extras.append(f"空间：{lock['space']}")
    if lock.get("lock_rule"):
        extras.append(f"锁局规则：{lock['lock_rule']}")
    if lock.get("win"):
        extras.append(f"胜利条件：{lock['win']}")
    camp = b["camp"]
    extras.append(
        f"阵营称呼：{camp['pollution']} / {camp['swayable']} / {camp['truth']}"
        + ("（对外公开）" if camp["public"] else "（对玩家隐藏）")
    )
    if camp.get("win_pollution"):
        extras.append(f"{camp['pollution']}胜利：{camp['win_pollution']}")
    if camp.get("win_truth"):
        extras.append(f"{camp['truth']}胜利：{camp['win_truth']}")
    if b["vibe"]["horror_beats"]:
        extras.append(f"恐怖拍点：{b['vibe']['horror_beats']}")
    if b["minis"]:
        extras.append("小游戏：" + "、".join(b["minis"]))

    rules = list(world.get("world_rules") or [])
    keep = [r for r in rules if not str(r).startswith((
        "时间盒：", "空间：", "锁局规则：", "胜利条件：", "阵营称呼：",
        "恐怖拍点：", "小游戏：",
    )) and "胜利：" not in str(r)[:8]]
    world["world_rules"] = (keep[:1] + extras + keep[1:])[:10]

    truth = b["truth"]
    if truth.get("surface"):
        world["surface_truth"] = truth["surface"]

    labels = {
        "char_01": camp["pollution"],
        "char_02": camp["swayable"],
        "char_03": camp["truth"],
        "char_04": camp["truth"],
    }
    slots = {c["id"]: c for c in (world.get("cast_slots") or [])}
    chars = {c["id"]: c for c in (detail.get("characters") or [])}
    for slot in b["cast"]:
        cid = slot["id"]
        if slot["name"]:
            if cid in slots:
                slots[cid]["name"] = slot["name"]
            if cid in chars:
                chars[cid]["name"] = slot["name"]
        if slot["archetype"]:
            arch = slot["archetype"]
            if camp["public"] and labels.get(cid) and not arch.startswith("【"):
                arch = f"【{labels[cid]}】{arch}"
            if cid in slots:
                slots[cid]["archetype"] = arch
            if cid in chars:
                chars[cid]["archetype"] = arch
        elif camp["public"] and cid in chars:
            arch = chars[cid].get("archetype") or ""
            if arch and not arch.startswith("【"):
                chars[cid]["archetype"] = f"【{labels[cid]}】{arch}"
                if cid in slots:
                    slots[cid]["archetype"] = chars[cid]["archetype"]
        if slot["comedy_hook"] and cid in slots:
            slots[cid]["comedy_hook"] = slot["comedy_hook"]
        if slot["public_bio"] and cid in chars:
            pub = dict(chars[cid].get("public") or {})
            pub["bio"] = slot["public_bio"]
            chars[cid]["public"] = pub

    culprit = detail.get("culprit") or {}
    c01 = next((c for c in b["cast"] if c["id"] == "char_01" and c["name"]), None)
    if c01:
        culprit["name"] = c01["name"]
    c02 = next((c for c in b["cast"] if c["id"] == "char_02" and c["name"]), None)
    accomplices = culprit.get("accomplices") or []
    if c02 and accomplices:
        accomplices[0]["name"] = c02["name"]
    if truth.get("crime"):
        culprit["crime"] = truth["crime"]
    if truth.get("motive"):
        culprit["motive"] = truth["motive"]
    if truth.get("method"):
        culprit["method"] = truth["method"]
    detail["culprit"] = culprit

    act_list = acts.get("acts") if isinstance(acts, dict) else acts
    if not isinstance(act_list, list):
        return
    want = {a["id"]: a for a in b["acts"]}
    for a in act_list:
        w = want.get(a.get("id"))
        if not w:
            continue
        if w["name"]:
            a["name"] = w["name"]
        if w["brief"]:
            a["brief"] = w["brief"]
        if w["must_reveal"]:
            a["must_reveal"] = w["must_reveal"]
        if w["must_not_reveal"]:
            a["must_not_reveal"] = w["must_not_reveal"]
        if w["twist"]:
            a["twist_beat"] = w["twist"]
        if w["comedy"]:
            a["comedy_beat"] = w["comedy"]

    vibe = b["vibe"]
    if vibe.get("dm"):
        for a in act_list:
            a["dm_notes"] = vibe["dm"]
    if vibe.get("comedy"):
        world["comedy_sources"] = _split_list(vibe["comedy"])
    elif vibe["mood"] == "horror":
        world["comedy_sources"] = ["错位耳语", "灯灭空档", "搜到不该搜的"]
