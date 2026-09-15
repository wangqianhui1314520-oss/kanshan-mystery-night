"""圣经 → schemas 合法目录。零 LLM。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .paths import KANSHAN, assert_writable
from .tiers import CHAR_AVATARS, LOCATION_META


def _loc_table(world: dict) -> dict:
    rows = {r.get("id"): r for r in (world.get("locations") or []) if isinstance(r, dict) and r.get("id")}
    out = {}
    for lid, meta in LOCATION_META.items():
        src = rows.get(lid) or {}
        out[lid] = {
            "name": src.get("name") or meta["name"],
            "type": src.get("type") or meta["type"],
            "image": src.get("image") or meta["image"],
            "keywords": list(src.get("keywords") or meta.get("keywords") or []),
            "hint": src.get("hint") or "",
        }
    return out


def compile_bibles(world: dict, detail: dict, acts: dict, *, scenario_id: str) -> Path:
    out = assert_writable(scenario_id)

    loc_table = _loc_table(world)
    scene_map = {}
    pool_by_name: dict[str, list[str]] = {row["name"]: [] for row in loc_table.values()}
    for clue in detail["clues"]:
        if clue.get("tier") == "fake":
            continue
        loc = clue.get("location")
        if loc in pool_by_name:
            pool_by_name[loc].append(clue["id"])
        else:
            pool_by_name.setdefault(loc, []).append(clue["id"])
    for lid, row in loc_table.items():
        scene_map[lid] = {
            "name": row["name"],
            "type": row["type"],
            "clue_pool": pool_by_name.get(row["name"]) or [],
            "image": row["image"],
            "keywords": list(row.get("keywords") or []),
            "hint": row.get("hint") or "",
        }

    act_list = []
    for a in acts["acts"]:
        act_list.append({
            "id": a["id"],
            "name": a["name"],
            "stage": a["stage"],
            "actions_allocated": int(a["actions_allocated"]),
            "brief": a.get("brief", ""),
        })

    scenario = {
        "id": scenario_id,
        "title": world["title"],
        "genre": world.get("genre", "欢乐阵营机制推理 · 快本"),
        "ip_source": "工作台快本 · 知识卡署名见 cards · 骨架为虚构拟人",
        "player_count_min": 1,
        "player_count_max": 4,
        "ai_npc_count": 4,
        "duration_minutes": 20,
        "difficulty": "快本（演示档）",
        "summary": world.get("logline") or world.get("hook", ""),
        "modes": {
            "main": "快本三幕",
            "daily": "同快本",
            "quick": "快本（工作台默认）",
        },
        "acts": act_list,
        "scene_map": scene_map,
        "system_npcs": [
            {"id": "dm", "name": "系统提示音", "desc": "叮——控场；只演不裁"}
        ],
        "condition_grammar": "默认 | evidence:<id> | memory:<char>:<ver> | counsel:<kc>",
        "content_safety": world.get("safety", ""),
    }
    _dump(out / "scenario.json", scenario)

    truth = {
        "truth_summary": world.get("surface_truth", ""),
        "culprit": detail["culprit"],
        "boss_layer": None,
        "truth_nodes": detail["truth_nodes"],
        "attribution": "知识卡作者署名保留在 knowledge_cards；剧情角色均为虚构。",
    }
    _dump(out / "truth.json", truth)
    _dump(out / "timeline.json", detail["timeline"])

    cdir = out / "characters"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir()
    for ch in detail["characters"]:
        cid = ch["id"]
        card = {
            "id": cid,
            "name": ch["name"],
            "role_type": ch.get("role_type", "npc"),
            "archetype": ch.get("archetype", ""),
            "faction": ch["faction"],
            "public": ch.get("public") or {
                "avatar": CHAR_AVATARS.get(cid, CHAR_AVATARS["char_01"]),
                "bio": "",
                "speech_style": "",
            },
            "secret": ch.get("secret") or {"motive": "", "alibi": "", "guilt": ""},
            "goal": ch.get("goal", ""),
            "heartache": ch.get("heartache", ""),
            "memory_versions": [
                f"memory/{cid}_v1.json",
                f"memory/{cid}_v2.json",
                f"memory/{cid}_v3.json",
            ],
            "deleted_segments": ch.get("deleted_segments") or [],
        }
        _dump(cdir / f"{cid}.json", card)

    from .player_book import build_books, write_books, write_runtime_booklets
    books = build_books(world, detail, acts)
    write_books(out, books)
    write_runtime_booklets(out, world, detail, acts, books)

    mdir = out / "memory"
    if mdir.exists():
        shutil.rmtree(mdir)
    mdir.mkdir()
    for cid, versions in detail["memories"].items():
        for mem in versions:
            ver = int(mem["version"])
            _dump(mdir / f"{cid}_v{ver}.json", {
                "owner": mem.get("owner", cid),
                "version": ver,
                "blocks": mem.get("blocks") or [],
                "diff_from_prev": mem.get("diff_from_prev") or [],
            })

    cldir = out / "clues"
    if cldir.exists():
        shutil.rmtree(cldir)
    cldir.mkdir()
    for clue in detail["clues"]:
        row = {
            "id": clue["id"],
            "name": clue["name"],
            "tier": clue["tier"],
            "location": clue["location"],
            "tags": clue.get("tags") or [],
            "fact": clue.get("fact", ""),
            "flavor_hint": clue.get("flavor_hint", ""),
            "linked_truth_nodes": clue.get("linked_truth_nodes") or [],
            "unlock_condition": clue.get("unlock_condition") or "默认",
            "fake_of": clue.get("fake_of"),
            "flaw_id": clue.get("flaw_id"),
        }
        _dump(cldir / f"{clue['id']}.json", row)

    _copy_knowledge_cards(out, detail.get("kc_plan") or [])
    kc_tags = _kc_topic_tags(out)

    hf = out / "hotfeed"
    if hf.exists():
        shutil.rmtree(hf)
    hf.mkdir()
    for post in detail["hotfeed"]:
        tag = post.get("topic_tag") or ""
        if tag.startswith("kc_") and tag in kc_tags:
            tag = kc_tags[tag]
        row = {
            "id": post["id"],
            "round": int(post.get("round") or 1),
            "title": post["title"],
            "body": post.get("body", ""),
            "author_mask": post.get("author_mask", "网友"),
            "is_fake": bool(post.get("is_fake")),
            "clue_ref": post.get("clue_ref"),
            "topic_tag": tag,
            "heat_delta": int(post.get("heat_delta") or 5),
            "humor_tag": post.get("humor_tag") or "玩梗",
        }
        _dump(hf / f"{post['id']}.json", row)

    studio = out / "_studio"
    studio.mkdir(exist_ok=True)
    _dump(studio / "world.json", world)
    _dump(studio / "detail.json", _detail_without_secrets_for_debug(detail))
    _dump(studio / "acts.json", acts)
    (studio / "bible.md").write_text(_bible_md(world, acts), encoding="utf-8")
    return out


def _copy_knowledge_cards(out: Path, plan: list[dict]) -> None:
    src = KANSHAN / "knowledge_cards"
    dest = out / "knowledge_cards"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    binds = {p["id"]: p["binds"] for p in plan}
    for kid, bind in binds.items():
        fp = src / f"{kid}.json"
        data = json.loads(fp.read_text(encoding="utf-8"))
        data["binds"] = bind
        _dump(dest / f"{kid}.json", data)


def _kc_topic_tags(out: Path) -> dict[str, str]:
    tags = {}
    for f in (out / "knowledge_cards").glob("kc_*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        tags[data["id"]] = data.get("topic_tag") or ""
    return tags


def _detail_without_secrets_for_debug(detail: dict) -> dict:
    """落盘给作者看的细节稿：保留 secret（作者视图）。"""
    return detail


def _bible_md(world: dict, acts: dict) -> str:
    lines = [f"# {world.get('title', '')}", "", world.get("logline", ""), "", "## 幕"]
    for a in acts.get("acts", []):
        lines.append(f"- {a.get('name')}: {a.get('brief')}")
    return "\n".join(lines) + "\n"


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
