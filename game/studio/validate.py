"""跨文件闸门。不过闸不得 playable。"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import BLACKLIST
from .tiers import QUOTA

_BOOK_PUBLIC_LITERALS = ("guilt", "inner_truth", "pollution", "faction")
_BOOK_LITERAL_MSG = "BOOK: 公开信息不得出现 guilt/inner_truth/pollution/faction"
_BOOK_LEAK_MSG = "BOOK: 隐瞒不得写入公开信息"


def validate_dir(scenario_dir, tier: str = "demo") -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    root = Path(scenario_dir)
    sid = root.name
    if sid in BLACKLIST:
        errors.append("BLACKLIST: 拒绝写入 kanshan/template")
        return {"ok": False, "errors": errors, "warnings": warnings}

    q = QUOTA.get(tier)
    if not q:
        errors.append(f"未知档位 {tier}")
        return {"ok": False, "errors": errors, "warnings": warnings}

    def load(rel: str):
        p = root / rel
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"READ: {rel}: {e}")
            return None

    scenario = load("scenario.json")
    truth = load("truth.json")
    timeline = load("timeline.json")
    if not scenario or not truth or not timeline:
        return {"ok": False, "errors": errors, "warnings": warnings}

    chars = {}
    cdir = root / "characters"
    if cdir.is_dir():
        for f in sorted(cdir.glob("char_*.json")):
            chars[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    clues = {}
    for f in sorted((root / "clues").glob("clue_*.json")):
        clues[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    posts = {}
    hf = root / "hotfeed"
    if hf.is_dir():
        for f in sorted(hf.glob("post_*.json")):
            posts[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    cards = {}
    kcdir = root / "knowledge_cards"
    if kcdir.is_dir():
        for f in sorted(kcdir.glob("kc_*.json")):
            cards[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    mem_files = list((root / "memory").glob("char_*_v*.json")) if (root / "memory").is_dir() else []

    if len(chars) != q["chars"]:
        errors.append(f"QUOTA: 角色应为 {q['chars']}，实际 {len(chars)}")
    if len(clues) != q["clues"]:
        errors.append(f"QUOTA: 线索总数应为 {q['clues']}，实际 {len(clues)}")
    if len(scenario.get("scene_map") or {}) != q["locations"]:
        errors.append(f"QUOTA: 地点应为 {q['locations']}")
    if len(truth.get("truth_nodes") or []) != q["truth_nodes"]:
        errors.append(f"QUOTA: 真相节点应为 {q['truth_nodes']}")
    if len(scenario.get("acts") or []) != q["acts"]:
        errors.append(f"QUOTA: 幕数应为 {q['acts']}")
    if len(posts) != q["hotfeed"]:
        errors.append(f"QUOTA: 热搜应为 {q['hotfeed']}，实际 {len(posts)}")
    if len(cards) != q["kc"]:
        errors.append(f"QUOTA: 知识卡应为 {q['kc']}，实际 {len(cards)}")
    if len(mem_files) != q["memory_files"]:
        errors.append(f"QUOTA: 记忆文件应为 {q['memory_files']}，实际 {len(mem_files)}")

    tiers = {}
    for c in clues.values():
        tiers[c.get("tier")] = tiers.get(c.get("tier"), 0) + 1
    for key, expect in (("public", q["public"]), ("limited", q["limited"]),
                        ("hidden", q["hidden"]), ("fake", q["fake"])):
        if tiers.get(key, 0) != expect:
            errors.append(f"QUOTA: {key} 线索应为 {expect}，实际 {tiers.get(key, 0)}")

    factions = [c.get("faction") for c in chars.values()]
    if factions.count("pollution") != q["pollution"]:
        errors.append("FACTION: 需要 1 污染 + ≥1 可策反")
    elif factions.count("swayable") < q["swayable_min"]:
        errors.append("FACTION: 需要 1 污染 + ≥1 可策反")

    scene_names = {v.get("name") for v in (scenario.get("scene_map") or {}).values()}
    scene_ids = set((scenario.get("scene_map") or {}).keys())
    for sid_loc in scene_ids:
        if not str(sid_loc).startswith("loc_"):
            errors.append(f"REF: scene_map key 必须是 loc_*，收到 {sid_loc}")

    for cid, clue in clues.items():
        loc = clue.get("location")
        if loc not in scene_names:
            errors.append(f"REF: {cid} location={loc!r} 不在场景中文名")
        if clue.get("tier") == "fake":
            fo = clue.get("fake_of")
            if not fo or fo not in clues:
                errors.append("FAKE: fake 必须有 fake_of 且不得入 clue_pool")
            for node in (scenario.get("scene_map") or {}).values():
                if cid in (node.get("clue_pool") or []):
                    errors.append("FAKE: fake 必须有 fake_of 且不得入 clue_pool")
                    break
        for tn in clue.get("linked_truth_nodes") or []:
            if tn not in {n["id"] for n in truth.get("truth_nodes") or []}:
                errors.append(f"REF: {cid} 指向不存在节点 {tn}")

    for loc_id, node in (scenario.get("scene_map") or {}).items():
        for cid in node.get("clue_pool") or []:
            if cid not in clues:
                errors.append(f"REF: clue_pool 引用不存在")
                break

    tn_ids = set()
    for node in truth.get("truth_nodes") or []:
        tn_ids.add(node["id"])
        proofs = node.get("proof_clues") or []
        if len(proofs) < q["proof_min"]:
            errors.append("REF: truth_node 证明不足")
        for cid in proofs:
            if cid not in clues:
                errors.append(f"REF: clue_pool 引用不存在")

    char_ids = set(chars)
    for ch in chars.values():
        for rel in ch.get("memory_versions") or []:
            if not (root / rel).is_file():
                errors.append(f"REF: 记忆文件缺失 {rel}")

    for f in mem_files:
        mem = json.loads(f.read_text(encoding="utf-8"))
        if mem.get("owner") not in char_ids:
            errors.append(f"REF: 记忆归属非法 {f.name}")

    for ev in timeline.get("timeline") or []:
        who = ev.get("character")
        if who not in char_ids and who not in {"dm", "archiv3", "kanshan"}:
            warnings.append(f"时间线角色未登记：{who}")

    for card in cards.values():
        bind = card.get("binds")
        if bind not in char_ids and bind not in {"team_all", "team", "all", "org", "archive", "archive_bureau"}:
            errors.append("KC: binds 指向不存在角色")

    kc_tags = {c.get("topic_tag") for c in cards.values() if c.get("topic_tag")}
    matched = 0
    for p in posts.values():
        if p.get("is_fake") and p.get("topic_tag") in kc_tags:
            matched += 1
    if matched < q["fake_posts_min"]:
        errors.append("TAG: 辟谣帖 topic_tag 无法对齐知识卡")

    book_err = "BOOK: 每个角色必须有故事本"
    for cid in chars:
        book_path = root / "scripts" / f"player_book_{cid}.json"
        if not book_path.is_file():
            errors.append(book_err)
            continue
        try:
            book = json.loads(book_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            errors.append(book_err)
            continue
        if not isinstance(book, dict) or (book.get("char_id") or "") != cid:
            errors.append(book_err)
            continue
        you_are = book.get("you_are")
        if not (isinstance(you_are, str) and you_are.strip()):
            errors.append(book_err)
            continue
        goals = book.get("goals")
        if isinstance(goals, str):
            goals = [goals] if goals.strip() else []
        if not isinstance(goals, list) or not any(str(g).strip() for g in goals):
            errors.append(book_err)
            continue
        _book_semantic_gate(book, errors)

    # 去重
    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _book_strs(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    out = []
    for x in val:
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _book_semantic_gate(book: dict, errors: list[str]) -> None:
    """公开栏禁词 / 隐瞒原文泄漏。现有 mock 快本不踩线，记 errors 不降 warnings。"""
    you_are = book.get("you_are") or ""
    situation = book.get("situation") or ""
    facts = _book_strs(book.get("known_facts"))
    public_blob = "\n".join([str(you_are), str(situation), *facts])
    if any(tok in public_blob.lower() for tok in _BOOK_PUBLIC_LITERALS):
        errors.append(_BOOK_LITERAL_MSG)
    facts_blob = "\n".join(facts)
    for secret in _book_strs(book.get("secrets")):
        if secret and secret in facts_blob:
            errors.append(_BOOK_LEAK_MSG)
            break
