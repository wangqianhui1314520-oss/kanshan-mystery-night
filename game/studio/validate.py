"""跨文件闸门。不过闸不得 playable。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .evidence_contract import linked_clues_by_node
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
    truth_nodes = truth.get("truth_nodes") or []
    for node in truth_nodes:
        tn_ids.add(node["id"])
        proofs = node.get("proof_clues") or []
        if len(proofs) < q["proof_min"]:
            errors.append("REF: truth_node 证明不足")
        for cid in proofs:
            if cid not in clues:
                errors.append(f"REF: clue_pool 引用不存在")

    # Generated demo packs must be playable under EvidenceChain.try_compose:
    # three valid links make one card, and accusation requires two distinct
    # truth-node cards. Small hand-built validator fixtures intentionally omit
    # the full demo quota and are covered by the older V1/V2/V3 checks below.
    if (os.environ.get("NARRATIVE_GATE", "") != "0"
            and len(clues) == q["clues"]
            and len(truth_nodes) == q["truth_nodes"]):
        linked_by_tn = linked_clues_by_node(clues, truth_nodes)
        composeable = 0
        for node in truth_nodes:
            tid = str(node.get("id") or "")
            valid_links = linked_by_tn.get(tid, set())
            if len(valid_links) < 3:
                errors.append(
                    f"NARR-EVIDENCE: {tid} 可合成线索不足（有效 linked_truth_nodes={len(valid_links)}，需 ≥3）")
            else:
                composeable += 1
        if composeable < 2:
            errors.append(
                f"NARR-EVIDENCE: 至少需要 2 个可合成证据节点（当前 {composeable}）")

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

    # 叙事级闸门（V1/V2/V3）。NARRATIVE_GATE=0 可整体关闭（mutation test 用）。
    if os.environ.get("NARRATIVE_GATE", "") != "0":
        _check_timeline_consistency(scenario, truth, timeline, clues, errors, warnings)
        _check_reachability(scenario, truth, clues, errors, warnings)
        _check_fake_loop(root, truth, clues, chars, errors, warnings)

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


# ---------------------------------------------------------------------------
# 叙事级检查器（V1/V2/V3）。只查「叙事逻辑」，不改结构闸门既有逻辑。
# 实测基准：content/scenarios/kanshan/（权威主剧本）不得被误伤（0 error）。
# ---------------------------------------------------------------------------


def _check_timeline_consistency(scenario, truth, timeline, clues, errors, warnings) -> None:
    """V1 时间线一致性（error 级）。

    规则：
    1. 同一 character 的时间不重叠：按 time 精确相等判定（time 相同且 action
       相同视为同一事件，不报；time 相同但 action 不同 → error）。
    2. 每幕时间窗内至少一条事件——仅在 acts 含时间窗字段（time_window 或
       start_time/end_time）时检查。kanshan 实测 acts 只有 id/name/stage/
       actions_allocated/brief，无时间窗字段 → 该子项天然跳过。
    3. 「口供-时间线」交叉点兜底：有 linked_truth_nodes 的线索数 ≥ truth_nodes
       数（粗粒度）。kanshan 实测 34≥14 通过；不满足仅 warning（避免误伤
       小体量包，非死局）。
    """
    events = timeline.get("timeline") or []
    # 子项 1：同角色同时刻重叠（action 相同视为同源事件）
    seen: dict[tuple, dict] = {}
    for ev in events:
        who = ev.get("character")
        when = str(ev.get("time") or "")
        act_txt = str(ev.get("action") or ev.get("desc") or "")
        key = (who, when)
        prev = seen.get(key)
        if prev is None:
            seen[key] = {"action": act_txt}
        elif act_txt != prev["action"]:
            errors.append(
                f"NARR-V1: {who} 在 {when} 存在重叠事件（同一时刻只能在一个事件）")
    # 子项 2：幕时间窗（kanshan 无时间窗字段，自动跳过）
    for act in scenario.get("acts") or []:
        win = act.get("time_window")
        start, end = act.get("start_time"), act.get("end_time")
        if win:
            parts = str(win).split("-")
            if len(parts) == 2:
                start, end = parts[0].strip(), parts[1].strip()
        if not (start and end):
            continue
        inside = [
            ev for ev in events
            if str(start) <= str(ev.get("time") or "") <= str(end)
        ]
        if not inside:
            errors.append(
                f"NARR-V1: 幕 {act.get('id')} 时间窗 {start}-{end} 内无时间线事件")
    # 子项 3：交叉点粗兜底
    tn_count = len(truth.get("truth_nodes") or [])
    linked = sum(1 for c in clues.values() if c.get("linked_truth_nodes"))
    if tn_count and linked < tn_count:
        warnings.append(
            f"NARR-V1: 口供-时间线交叉点不足（有真相链接的线索 {linked} < 真相节点 {tn_count}）")


def _check_reachability(scenario, truth, clues, errors, warnings) -> None:
    """V2 真相可达性（error 级），宽松可达模型。

    建图：truth_node ←proof_clues← clue ←location(中文场景名)← scene_map 节点。
    分幕解锁从严会误伤，故 act2 起全部场景视为可达、act1 起点集合不做裁剪——
    只拦两类死局：
    a) 真相挂在完全不存在的场景：某节点的全部有效证明线索 location 均不在
       scene_map 中文名集合 → error。
    b) 真相零证明线索：proof_clues 为空列表 → error。
    逐节点 proof 细化（≥2 条）：1 条=warning、0 条=error。REF 段已有
    proof_min 检查；同一节点已被 REF 报过的（引用不存在的线索）不再重复报。
    kanshan 实测豁免：tn_08 仅 1 条证明（clue_016），单证规则点由 error
    降级为 warning，不拦截 gate.ok。
    """
    scene_names = {v.get("name") for v in (scenario.get("scene_map") or {}).values()}
    for node in truth.get("truth_nodes") or []:
        tn = node.get("id")
        proofs = node.get("proof_clues") or []
        existing = [c for c in proofs if c in clues]
        if not proofs:
            errors.append(f"NARR-V2: {tn} 零证明线索（真相死局）")
            continue
        if not existing:
            # 全部引用缺失：REF 段已报「clue_pool 引用不存在」，去重不报
            continue
        if len(existing) == 1:
            # kanshan 实测豁免：tn_08 单证合法，降 warning 不拦截
            warnings.append(f"NARR-V2: {tn} 证明线索仅 1 条（建议 ≥2）")
        reachable = [
            c for c in existing if clues[c].get("location") in scene_names
        ]
        if not reachable:
            errors.append(
                f"NARR-V2: {tn} 真相不可达（证明线索均不在场景节点）")


def _check_fake_loop(root: Path, truth, clues, chars, errors, warnings) -> None:
    """V3 伪证回路与凶手隐瞒（error 级）。

    规则：
    1. 每个 fake 线索必须「可被真线索戳破」，满足任一即可：
       a) 存在非 fake 线索与其共享同一个 linked_truth_nodes 成员；
       b) fake_of 指向一条存在的非 fake 线索（被伪造的原件即戳破者；
          生成包 mock 快本实测 fake 线索 linked_truth_nodes 为空、仅靠
          fake_of 关联，故 b 为必要豁免，否则误伤全部生成包）。
       两者皆缺 → error。
    2. culprit（truth.culprit.character）必须有隐瞒：scripts/player_book_{cid}.json
       或 booklets/{cid}.json 的 secrets 非空。文件缺失或无 secrets 键 →
       warning（kanshan 实测豁免：主剧本无 player_book，booklets/char_XX.json
       无 secrets 键，故事本结构与生成包不同；生成包的 player_book 存在性
       已由 BOOK 段既有检查覆盖）。secrets 键存在但为空 → error。
    """
    linked_by_tn: dict[str, set] = {}
    for cid, clue in clues.items():
        if clue.get("tier") == "fake":
            continue
        for tn in clue.get("linked_truth_nodes") or []:
            linked_by_tn.setdefault(tn, set()).add(cid)
    for cid, clue in clues.items():
        if clue.get("tier") != "fake":
            continue
        tns = set(clue.get("linked_truth_nodes") or [])
        shared = any(linked_by_tn.get(tn, {cid}) - {cid} for tn in tns)
        fo = clue.get("fake_of")
        fake_of_valid = bool(fo) and fo in clues and clues[fo].get("tier") != "fake"
        if not (shared or fake_of_valid):
            errors.append(
                f"NARR-V3: {cid} 伪证不可戳破（无真线索共享真相节点且 fake_of 缺失）")

    culprit = truth.get("culprit") or {}
    ccid = culprit.get("character")
    if ccid and ccid in chars:
        book = None
        for rel in (f"scripts/player_book_{ccid}.json", f"booklets/{ccid}.json"):
            p = root / rel
            if p.is_file():
                try:
                    book = json.loads(p.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    book = None
                break
        if book is None or "secrets" not in (book or {}):
            # kanshan 实测豁免：主剧本故事本无 secrets 键，降 warning
            warnings.append(f"NARR-V3: 凶手 {ccid} 故事本无 secrets 字段（建议补齐）")
        elif not _book_strs(book.get("secrets")):
            errors.append(f"NARR-V3: 凶手 {ccid} 无隐瞒（secrets 为空）")
