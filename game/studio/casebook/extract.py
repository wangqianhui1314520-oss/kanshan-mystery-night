"""从钩子 / 锁局 / 入座抽出空间、物件、时间轴、人名。"""

from __future__ import annotations

import re

from .lexicon import OBJECTS, PACK_LOCS, PLACE_END

_TIME_HM = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")
_WINDOW = re.compile(r"(\d+)\s*分钟")


def place(hook: str, space: str, fallback: str) -> str:
    if space:
        return space[:10]
    for end in PLACE_END:
        i = hook.find(end)
        if i < 0:
            continue
        raw = hook[max(0, i - 6): i + len(end)]
        raw = re.sub(r"^[\d\s:：点小时钟]+", "", raw)
        raw = re.sub(r"^[在从到往被把将的了与和]", "", raw)
        raw = raw.strip()
        if raw:
            return raw[-8:]
    return fallback


def object_name(hook: str, truth: dict, fallback: str) -> str:
    crime = (truth.get("crime") or "").strip()
    for key in OBJECTS:
        if key in crime:
            return key
    for key in OBJECTS:
        if key in hook:
            return key
    if crime:
        clip = re.sub(r"[，。！？、\s]", "", crime)
        if 2 <= len(clip) <= 8:
            return clip
        return clip[:8] or fallback
    return fallback


def window(hook: str, timebox: str) -> str:
    text = f"{hook} {timebox}"
    m = _WINDOW.search(text)
    if m:
        return f"{m.group(1)}分钟"
    if "小时" in text and "24" in text:
        return "锁门后的空档"
    return "锁门后的空档"


def device(hook: str, pack: str, fallback: str) -> str:
    if "灯" in hook or pack == "horror":
        if "横幅" in hook and pack != "horror":
            return "全息横幅"
        return "灭灯令" if pack == "horror" or "灯" in hook else fallback
    if "横幅" in hook:
        return "全息横幅"
    if "盐" in hook:
        return "盐值闸"
    return fallback


def verb(hook: str, obj: str, crime: str, fallback: str) -> str:
    blob = hook + crime + obj
    if any(w in blob for w in ("删", "挖走", "缺了")):
        return "删除"
    if any(w in blob for w in ("换", "调换", "原片")):
        return "调换"
    if any(w in blob for w in ("改写", "横幅指令", "写着")):
        return "改写"
    if any(w in blob for w in ("剪", "播出")):
        return "剪掉"
    return fallback


def leftover(hook: str, pack: str, fallback: str) -> str:
    if "盐" in hook:
        return "一撮盐粒"
    if "灯" in hook or pack == "horror":
        return "烧过的火柴"
    if "奶茶" in hook or "糖" in hook:
        return "半杯暗号饮"
    return fallback


def signal(hook: str, pack: str, fallback: str) -> str:
    if "老规矩" in hook:
        return "按老规矩"
    if "糖" in hook:
        return "三分糖"
    if pack == "horror":
        return "三次敲管"
    return fallback


def theme(pack: str, obj: str) -> str:
    return {
        "horror": "看见了就不能装没看见",
        "emotion": "没说出口的比证物更重",
        "hard_logic": "只认时间地点和哈希",
        "faction": "赢面和真相不是同一张牌",
        "variety": "镜头在，成片可以不在",
        "immerse": "出不去，是因为还没对上",
    }.get(pack, f"{obj}不是热闹")


def times(timebox: str) -> dict[str, str]:
    m = _TIME_HM.search(timebox or "")
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
    else:
        h, mi = 21, 0

    def fmt(hh: int, mm: int) -> str:
        hh = (hh + mm // 60) % 24
        mm = mm % 60
        return f"{hh:02d}:{mm:02d}"

    lock = fmt(h, mi)
    return {
        "lock": lock,
        "leave": fmt(h, mi + 5),
        "gap_a": fmt(h, mi + 7),
        "crime": fmt(h, mi + 8),
        "gap_b": fmt(h, mi + 14),
        "back": fmt(h, mi + 14),
        "late": fmt(h, mi + 28),
        "borrow": fmt(h - 1 if mi < 15 else h, (mi - 15) % 60 if mi >= 15 else mi + 45),
        "speech": fmt(h - 1 if mi < 10 else h, (mi - 10) % 60 if mi >= 10 else mi + 50),
        "fake": fmt(h + 1, mi),
        "open": fmt(h - 1, 0) if h else "20:00",
    }


def cast(rows: list, obj: str, pack: str, mood: str) -> tuple[dict, dict, dict, dict]:
    token = (obj[:2] if obj else "局内") or "局内"
    defaults = {
        "char_01": f"{token}主理",
        "char_02": "被点名的人",
        "char_03": "余光",
        "char_04": "值班记录",
    }
    arch_def = {
        "char_01": "把信息当武器的人",
        "char_02": "被拿捏的实习",
        "char_03": "看见了又不敢确认",
        "char_04": "记录在抽屉、勇气在门外",
    }
    by_id = {r.get("id"): r for r in rows if isinstance(r, dict)}
    names, arches, bios, hooks = {}, {}, {}, {}
    for cid in ("char_01", "char_02", "char_03", "char_04"):
        row = by_id.get(cid) or {}
        names[cid] = (row.get("name") or "").strip() or defaults[cid]
        arches[cid] = (row.get("archetype") or "").strip() or arch_def[cid]
        bios[cid] = (row.get("public_bio") or "").strip()
        hooks[cid] = (row.get("comedy_hook") or "").strip() or default_hook(cid, mood)
    return names, arches, bios, hooks


def default_hook(cid: str, mood: str) -> str:
    table = {
        "comedy": {"char_01": "每句话自带话题", "char_02": "开口先道歉",
                   "char_03": "我好像看见过", "char_04": "您好这边建议"},
        "horror": {"char_01": "先把灯关了再说", "char_02": "手还在抖",
                   "char_03": "余光里有人", "char_04": "记成了电路跳"},
        "variety": {"char_01": "先对镜头笑", "char_02": "这期不是我剪的",
                    "char_03": "我只是围观", "char_04": "流程单在我这"},
        "grim": {"char_01": "时间对得上再说", "char_02": "少说话",
                 "char_03": "我只报我看见的", "char_04": "记录在，人不敢"},
    }
    return (table.get(mood) or table["comedy"])[cid]


def places(space: str, pack: str) -> list[str]:
    suffixes = PACK_LOCS.get(pack) or PACK_LOCS["fun_mech"]
    prefix = (space or "")[:4]
    names = []
    if prefix:
        for suf in suffixes:
            name = f"{prefix}{suf}"
            if len(name) > 8:
                name = f"{prefix[:2]}{suf}"
            names.append(name)
    else:
        names = list(suffixes)
    return uniq(names)


def uniq(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for n in names:
        base, i = n, 2
        while n in seen:
            n = f"{base}{i}"
            i += 1
        seen.add(n)
        out.append(n)
    return out


def logline(hook: str, mood: str, space: str, obj: str, window_s: str) -> str:
    q = hook[:36]
    if mood == "horror":
        return f"「{q}」——{space}的灯灭之后，必须有人先承认碰过{obj}。"
    if mood == "grim":
        return f"「{q}」——{window_s}里只留下{obj}被动过的痕迹。"
    if mood == "variety":
        return f"「{q}」——镜头还在，{obj}已经不在。"
    return f"「{q}」——被锁在{space}的人，必须在热闹把{obj}淹死之前抓住那只手。"


def comedy(mood: str, vibe: dict) -> list[str]:
    extra = [x.strip() for x in re.split(r"[,，、/;；]+", vibe.get("comedy") or "") if x.strip()]
    if extra:
        return extra[:4]
    return {
        "horror": ["错位耳语", "灯灭空档", "搜到不该搜的"],
        "grim": ["冷场", "对不上的时间", "官腔把自己绕进去"],
        "variety": ["提示卡拿反", "一眼假热搜", "围观位突然出镜"],
        "comedy": ["腔调错位", "搜错彩蛋", "一眼假热搜"],
    }.get(mood, ["腔调错位", "搜错彩蛋"])
