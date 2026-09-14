"""作者 job 与试玩水合包。"""

from __future__ import annotations

import json
from pathlib import Path

from .player_book import list_covers
from .tiers import DM_AVATAR, LOCATION_META


def public_snapshot(scenario_dir: Path, *, playable: bool) -> dict:
    root = Path(scenario_dir)
    scenario = _j(root / "scenario.json")
    truth = _j(root / "truth.json")
    studio_world = _j(root / "_studio" / "world.json") or {}
    studio_detail = _j(root / "_studio" / "detail.json") or {}

    world_locs = {r.get("id"): r for r in (studio_world.get("locations") or []) if isinstance(r, dict)}
    locations = []
    for lid, node in (scenario.get("scene_map") or {}).items():
        meta = LOCATION_META.get(lid, {})
        img = "/" + str(node.get("image") or meta.get("image") or "").replace("\\", "/")
        if not img.startswith("/"):
            img = "/" + img
        wloc = world_locs.get(lid) or {}
        locations.append({
            "id": lid,
            "name": node.get("name", lid),
            "type": node.get("type", "base"),
            "img": img,
            "pos": meta.get("pos") or {"x": 50, "y": 50},
            "hint": node.get("hint") or wloc.get("hint") or (studio_world.get("hook") or "")[:40],
            "keywords": list(node.get("keywords") or wloc.get("keywords") or meta.get("keywords") or []),
        })

    name_to_id = {v["name"]: k for k, v in (scenario.get("scene_map") or {}).items()}
    replies_map = {c["id"]: c.get("replies") or [] for c in studio_detail.get("characters") or []}

    characters = []
    for f in sorted((root / "characters").glob("char_*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        pub = c.get("public") or {}
        avatar = pub.get("avatar") or ""
        if avatar and not avatar.startswith("/"):
            avatar = "/assets/" + avatar.split("assets/")[-1] if "assets/" in avatar else "/" + avatar
        characters.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "archetype": c.get("archetype", ""),
            "avatar": avatar,
            "bio": pub.get("bio", ""),
            "speech": pub.get("speech_style", ""),
            "goal": c.get("goal", ""),
            "heartache": c.get("heartache") or "",
            "replies": replies_map.get(c["id"]) or [pub.get("speech_style", "……")] * 3,
            "heartLine": "",
        })

    clues = []
    for f in sorted((root / "clues").glob("clue_*.json")):
        cl = json.loads(f.read_text(encoding="utf-8"))
        loc_name = cl.get("location") or ""
        clues.append({
            "id": cl["id"],
            "name": cl.get("name", ""),
            "tier": cl.get("tier", "public"),
            "location": name_to_id.get(loc_name, loc_name),
            "location_name": loc_name,
            "tags": cl.get("tags") or [],
            "fact": cl.get("fact", ""),
            "flavor": cl.get("flavor_hint", ""),
            "linked": cl.get("linked_truth_nodes") or [],
            "unlock": cl.get("unlock_condition") or "默认",
        })

    kcards = []
    for f in sorted((root / "knowledge_cards").glob("kc_*.json")):
        k = json.loads(f.read_text(encoding="utf-8"))
        kcards.append({
            "id": k["id"],
            "title": k.get("title", ""),
            "author": k.get("author", ""),
            "topic_tag": k.get("topic_tag", ""),
            "binds": k.get("binds", ""),
            "effect": k.get("effect", ""),
            "golden": k.get("golden_lines") or [],
            "summary": k.get("summary", ""),
        })

    posts = []
    for f in sorted((root / "hotfeed").glob("post_*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        posts.append({
            "id": p["id"],
            "round": p.get("round", 1),
            "title": p.get("title", ""),
            "body": p.get("body", ""),
            "author": p.get("author_mask", "网友"),
            "fake": bool(p.get("is_fake")),
            "tag": p.get("topic_tag", ""),
            "delta": p.get("heat_delta", 5),
            "humor": p.get("humor_tag", "玩梗"),
        })

    memories = {}
    mdir = root / "memory"
    if mdir.is_dir():
        for f in sorted(mdir.glob("*.json")):
            mem = json.loads(f.read_text(encoding="utf-8"))
            owner = mem.get("owner") or f.name.split("_v")[0]
            memories.setdefault(owner, []).append({
                "version": mem.get("version"),
                "blocks": _said_blocks(mem.get("blocks") or []),
                "diff": _public_diff(mem.get("diff_from_prev")),
            })

    return {
        "playable": bool(playable),
        "id": scenario.get("id"),
        "title": scenario.get("title", ""),
        "genre": scenario.get("genre", ""),
        "summary": scenario.get("summary", ""),
        "logline": studio_world.get("logline") or scenario.get("summary", ""),
        "hook": studio_world.get("hook", ""),
        "acts": [
            {"id": a.get("id"), "name": a.get("name"), "stage": a.get("stage"),
             "brief": a.get("brief", "")}
            for a in scenario.get("acts") or []
        ],
        "locations": locations,
        "characters": characters,
        "clues": clues,
        "kcards": kcards,
        "posts": posts,
        "truthNodes": [{"id": n["id"], "name": n.get("name", "")} for n in truth.get("truth_nodes") or []],
        "memories": memories,
        "books": list_covers(root),
        "dm": {"name": "叮——系统提示音", "avatar": "/" + DM_AVATAR},
    }


def _said_blocks(blocks) -> list:
    """公开包只给 said 层；heart 层不下发。"""
    out = []
    for b in blocks or []:
        if isinstance(b, dict) and b.get("layer") == "said":
            out.append(b)
    return out


def _public_diff(raw):
    """有篡改只回 True；无篡改回空列表。不写原文/真相反差。"""
    return True if raw else []


def _j(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
