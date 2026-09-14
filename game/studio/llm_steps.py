"""S1 接线处：有 LLM 时生成三份圣经。解析失败抛异常，pipeline 回退 mock。"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from . import mock_bible
from .tiers import KC_COPY, LOCATION_META, QUOTA, TIERS

LAST_PROVIDER = "main"

_GOLDEN_PATH = Path(__file__).resolve().parent / "casebook" / "kanshan_golden.json"
_GOLDEN_HEADER = "## 黄金样本对照（来自权威剧本 kanshan，供写法参考，禁止照抄内容）"
_GOLDEN_MAX_CHARS = 1500


def _golden_slice(step: str) -> str:
    """读取 kanshan 黄金样本切片。golden.json 缺失/损坏时返回空串，绝不阻塞生成。"""
    try:
        data = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
        if step == "world":
            body = (
                f"【真相分层写法】{data.get('truth_layering') or ''}\n"
                f"【线索 tier 配比（真实统计）】{json.dumps(data.get('tier_ratio') or {}, ensure_ascii=False)}"
            )
        elif step == "detail":
            fakes = (data.get("fake_evidence_samples") or [])[:2]
            body = (
                "【心声双层写法（said=口供 / heart=心声，edited=被篡改点）】"
                + json.dumps(data.get("voice_dual_layer") or [], ensure_ascii=False)
                + "\n【伪证话术范例】"
                + json.dumps(fakes, ensure_ascii=False)
            )
        elif step == "acts":
            pairs = {
                k: v.get("proof_count")
                for k, v in (data.get("clue_density") or {}).items()
            }
            body = (
                f"【幕节奏】{json.dumps(data.get('act_rhythm') or [], ensure_ascii=False)}"
                f"\n【真相-线索配对密度】{json.dumps(pairs, ensure_ascii=False)}"
            )
        else:
            return ""
        return f"{_GOLDEN_HEADER}\n{body}"[:_GOLDEN_MAX_CHARS]
    except Exception:
        return ""

_CHAR_IDS = ("char_01", "char_02", "char_03", "char_04")
_FACTIONS = {
    "char_01": "pollution",
    "char_02": "swayable",
    "char_03": "truth",
    "char_04": "truth",
}
_CLUE_IDS = [f"clue_{i:03d}" for i in range(1, 13)]
_TN_IDS = [f"tn_{i:02d}" for i in range(1, 7)]
_CLUE_TIERS = (
    ["public"] * 6 + ["limited"] * 3 + ["hidden"] * 2 + ["fake"]
)
_ACT_SPECS = (
    ("act1", "break_ice", 6, ["chat", "search"]),
    ("act2", "investigate", 9, ["search", "memory_fix", "counsel"]),
    ("act3", "accuse", 3, ["refute", "vote"]),
)
_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_MAX_RETRIES = 2


def generate_bibles(seed: str, *, tier: str = "demo", llm=None, inner_boss: bool = False,
                    brief=None) -> dict:
    """返回 {world, detail, acts}。解析失败必须抛异常，由 pipeline 回退 mock。"""
    global LAST_PROVIDER

    if tier not in TIERS:
        raise ValueError(f"P0 只支持 {TIERS}，收到 {tier!r}")

    seed = " ".join((seed or "").split())
    client = _resolve_llm(llm)
    skeleton = mock_bible.build(seed, inner_boss=inner_boss, brief=brief)

    world = _step_world(client, seed, skeleton, inner_boss=inner_boss)
    detail = _step_detail(client, seed, world, skeleton)
    acts = _step_acts(client, seed, world, detail, skeleton)

    LAST_PROVIDER = _provider_name(client)
    return {"world": world, "detail": detail, "acts": acts}


# ------------------------------------------------------------------ LLM 解析


def _resolve_llm(llm):
    if llm is not None:
        return llm
    try:
        from agents.llm_client import LLMClient  # noqa: WPS433
    except ImportError as exc:
        raise RuntimeError("无法导入 agents.llm_client.LLMClient") from exc
    client = LLMClient()
    main = client.providers.get("main")
    if main is None or not main.available():
        raise RuntimeError("LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 未配置，无法走 LLM 生成")
    return client


def _provider_name(llm) -> str:
    name = getattr(llm, "last_provider", "") or ""
    if name.endswith("(cache)"):
        name = name[: -len("(cache)")]
    if name in ("main", "zhida", "mock"):
        return name
    return "main"


def _load_prompt(name: str) -> str:
    from agents.llm_client import read_prompt  # noqa: WPS433

    return read_prompt(name)


def _render_prompt(name: str, **fields: str) -> tuple[str, str]:
    from agents.llm_client import render_template  # noqa: WPS433

    raw = _load_prompt(name)
    rendered = render_template(raw, **fields)
    if "## 创作种子" in rendered:
        head, tail = rendered.split("## 创作种子", 1)
        system = head.strip()
        user = ("## 创作种子" + tail).strip()
    else:
        system = rendered.strip()
        user = "请按 system 要求只输出 JSON。"
    if "只输出 JSON" not in system:
        system += "\n\n只输出 JSON，不要任何解释。"
    return system, user


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("根节点必须是 JSON 对象")
    return data


def _llm_json(client, system: str, user: str, *, step: str,
              shrink_hint: str = "") -> dict:
    global LAST_PROVIDER
    last_err: Exception | None = None
    prompt_user = user
    for attempt in range(_MAX_RETRIES + 1):
        try:
            text = client.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": prompt_user}],
                provider="main",
                temperature=0.35,
            )
            if isinstance(text, str):
                if getattr(client, "last_provider", "") == "fallback":
                    # 通道层请求失败（llm_client 已把异常兜底成通用文案），
                    # 当作传输失败重试，避免拿兜底文案空耗解析重试次数。
                    raise ValueError("LLM 请求失败（通道兜底文案）")
                try:
                    parsed = _parse_json(text)
                except (json.JSONDecodeError, ValueError):
                    if attempt < _MAX_RETRIES:
                        raise
                    # 末次尝试：疑似 max_tokens 截断 → 截断修复兜底（骨架补全其余字段）
                    parsed = _parse_json(_repair_truncated(text))
                LAST_PROVIDER = _provider_name(client)
                return parsed
            raise ValueError("chat 未返回字符串")
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            last_err = exc
            if attempt < _MAX_RETRIES:
                extra = shrink_hint if attempt == _MAX_RETRIES - 1 else ""
                prompt_user = (
                    f"{user}\n\n【重试 {attempt + 1}/{_MAX_RETRIES}】"
                    f"上次输出无法解析为合法 JSON（{exc}）。请只输出 JSON，不要解释。{extra}"
                )
    raise RuntimeError(f"{step} JSON 解析失败（已重试 {_MAX_RETRIES} 次）") from last_err


def _repair_truncated(text: str) -> str:
    """截断修复：丢弃残缺字符串/悬空键，按栈补全未闭合括号。修复失败由调用方抛错。"""
    stack: list[str] = []
    in_str = esc = False
    open_str_start = -1
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            open_str_start = i
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    if in_str:
        text = text[:open_str_start]
    text = text.rstrip().rstrip(",")
    # 去掉悬空的 "key": 残尾（截断点恰好在冒号后）
    while True:
        text = text.rstrip()
        if not text.endswith(":"):
            break
        text = text[:-1].rstrip()
        if text.endswith('"'):
            q = text.rfind('"', 0, -1)
            if q < 0:
                break
            text = text[:q].rstrip().rstrip(",")
    closer = {"{": "}", "[": "]"}
    return text + "".join(closer[c] for c in reversed(stack))


# ------------------------------------------------------------------ 三步


def _step_world(client, seed: str, skeleton: dict, *, inner_boss: bool = False) -> dict:
    system, user = _render_prompt("studio_world.md", seed=seed)
    if _golden_slice("world"):
        user = f"{user}\n\n{_golden_slice('world')}"
    raw = _llm_json(client, system, user, step="world")
    world = _patch_world(raw, skeleton["world"], inner_boss=inner_boss)
    _assert_world(world)
    return world


_DETAIL_SHRINK_HINT = (
    "【输出预算收紧】上次输出被截断。请压缩规模：顶层可省略 memories、hotfeed、"
    "timeline、kc_plan（系统自动补全）；characters 的 replies 每条≤20字、"
    "public/secret/goal 各≤40字；clues 的 fact/flavor_hint 各≤50字；"
    "truth_nodes 的 desc≤40字。只输出 JSON。"
)


def _step_detail(client, seed: str, world: dict, skeleton: dict) -> dict:
    world_json = json.dumps(world, ensure_ascii=False, indent=2)
    system, user = _render_prompt("studio_detail.md", seed=seed, world_json=world_json)
    if _golden_slice("detail"):
        user = f"{user}\n\n{_golden_slice('detail')}"
    raw = _llm_json(client, system, user, step="detail", shrink_hint=_DETAIL_SHRINK_HINT)
    detail = _patch_detail(raw, skeleton["detail"], world)
    _assert_detail(detail)
    return detail


def _step_acts(client, seed: str, world: dict, detail: dict, skeleton: dict) -> dict:
    world_json = json.dumps(
        {
            "title": world.get("title"),
            "hook": world.get("hook"),
            "logline": world.get("logline"),
            "surface_truth": world.get("surface_truth"),
            "cast_slots": world.get("cast_slots"),
        },
        ensure_ascii=False,
        indent=2,
    )
    detail_json = json.dumps(_detail_summary(detail), ensure_ascii=False, indent=2)
    system, user = _render_prompt(
        "studio_acts.md",
        seed=seed,
        world_json=world_json,
        detail_json=detail_json,
    )
    if _golden_slice("acts"):
        user = f"{user}\n\n{_golden_slice('acts')}"
    raw = _llm_json(client, system, user, step="acts")
    acts = _patch_acts(raw, skeleton["acts"])
    _assert_acts(acts)
    return acts


def _detail_summary(detail: dict) -> dict:
    culprit = detail.get("culprit") or {}
    return {
        "culprit": {
            k: culprit.get(k)
            for k in ("character", "name", "crime", "motive", "method", "evidence_chain")
        },
        "truth_nodes": [
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "desc": n.get("desc", ""),
                "proof_clues": n.get("proof_clues") or [],
            }
            for n in (detail.get("truth_nodes") or [])
        ],
        "characters": [
            {"id": c.get("id"), "name": c.get("name"), "faction": c.get("faction"),
             "archetype": c.get("archetype", "")}
            for c in (detail.get("characters") or [])
        ],
        "clues_brief": [
            {"id": c.get("id"), "name": c.get("name"), "tier": c.get("tier"),
             "location": c.get("location")}
            for c in (detail.get("clues") or [])
        ],
    }


# ------------------------------------------------------------------ 轻量修补


def _patch_world(raw: dict, skeleton: dict, *, inner_boss: bool) -> dict:
    world = _merge_missing(copy.deepcopy(raw), skeleton)
    world["cast_slots"] = _fix_cast_slots(raw.get("cast_slots") or skeleton["cast_slots"])
    world["locations"] = _fix_locations(
        raw.get("locations") or skeleton.get("locations")
    )
    if not inner_boss:
        world["inner_truth"] = None
    for key in ("title", "logline", "genre", "tone", "hook", "world_rules",
                "surface_truth", "theme", "comedy_sources", "safety"):
        if not world.get(key) and skeleton.get(key):
            world[key] = skeleton[key]
    return world


def _fix_cast_slots(slots: list) -> list:
    by_id = {s.get("id"): s for s in slots if isinstance(s, dict) and s.get("id")}
    fixed = []
    for cid in _CHAR_IDS:
        src = by_id.get(cid) or {}
        fixed.append({
            "id": cid,
            "name": src.get("name") or _default_char_name(cid),
            "archetype": src.get("archetype") or "",
            "faction": _FACTIONS[cid],
            "comedy_hook": src.get("comedy_hook") or "",
        })
    return fixed


def _default_char_name(cid: str) -> str:
    return {
        "char_01": "带节奏",
        "char_02": "执行者",
        "char_03": "目击者",
        "char_04": "记录员",
    }[cid]


def _patch_detail(raw: dict, skeleton: dict, world: dict) -> dict:
    detail = _merge_missing(copy.deepcopy(raw), skeleton)

    detail["characters"] = _fix_characters(
        detail.get("characters") or raw.get("characters") or skeleton["characters"])
    loc_names = [l.get("name") for l in (world.get("locations") or []) if l.get("name")]
    if len(loc_names) != 6:
        loc_names = [meta["name"] for meta in LOCATION_META.values()]
    detail["clues"] = _fix_clues(
        detail.get("clues") or raw.get("clues") or skeleton["clues"], loc_names
    )
    detail["truth_nodes"] = _fix_truth_nodes(
        detail.get("truth_nodes") or raw.get("truth_nodes") or skeleton["truth_nodes"])
    detail["culprit"] = _fix_culprit(
        detail.get("culprit") or raw.get("culprit") or skeleton["culprit"], world)
    detail["kc_plan"] = _fix_kc_plan(detail.get("kc_plan") or raw.get("kc_plan"))
    detail["memories"] = _fix_memories(detail.get("memories") or skeleton["memories"])
    detail["hotfeed"] = _fix_hotfeed(detail.get("hotfeed") or skeleton["hotfeed"])
    if not detail.get("timeline"):
        detail["timeline"] = skeleton["timeline"]
    return detail


def _fix_characters(chars: list) -> list:
    by_id = {c.get("id"): c for c in chars if isinstance(c, dict) and c.get("id")}
    out = []
    for cid in _CHAR_IDS:
        src = copy.deepcopy(by_id.get(cid) or {})
        src["id"] = cid
        src["faction"] = _FACTIONS[cid]
        src.setdefault("role_type", "npc")
        src.setdefault("name", _default_char_name(cid))
        src.setdefault("public", {})
        src.setdefault("secret", {"motive": "", "alibi": "", "guilt": ""})
        src.setdefault("goal", "")
        heartache_map = {"char_01": "kc_02", "char_02": "kc_03", "char_03": "kc_01", "char_04": "kc_04"}
        src.setdefault("heartache", heartache_map[cid])
        src.setdefault("replies", ["", "", ""])
        src.setdefault("heartLine", "")
        out.append(src)
    return out


def _fix_locations(raw_locs) -> list:
    by_id = {l.get("id"): l for l in (raw_locs or []) if isinstance(l, dict) and l.get("id")}
    out = []
    for lid, meta in LOCATION_META.items():
        src = by_id.get(lid) or {}
        out.append({
            "id": lid,
            "name": src.get("name") or meta["name"],
            "type": src.get("type") or meta["type"],
            "image": src.get("image") or meta["image"],
            "keywords": list(src.get("keywords") or meta.get("keywords") or []),
            "hint": src.get("hint") or "",
        })
    return out


def _fix_clues(clues: list, loc_names: list[str]) -> list:
    by_id = {c.get("id"): c for c in clues if isinstance(c, dict) and c.get("id")}
    if len(loc_names) != 6:
        loc_names = [meta["name"] for meta in LOCATION_META.values()]
    out = []
    for i, cid in enumerate(_CLUE_IDS):
        src = copy.deepcopy(by_id.get(cid) or {})
        skel = next((c for c in clues if c.get("id") == cid), {})
        merged = _merge_missing(src, skel)
        merged["id"] = cid
        merged.setdefault("name", f"线索 {i + 1}")
        tier = merged.get("tier") or _CLUE_TIERS[i]
        if tier not in ("public", "limited", "hidden", "fake"):
            tier = _CLUE_TIERS[i]
        merged["tier"] = tier
        loc = merged.get("location")
        if loc not in loc_names:
            merged["location"] = loc_names[i % len(loc_names)]
        merged.setdefault("tags", [])
        merged.setdefault("fact", "")
        merged.setdefault("flavor_hint", "")
        merged.setdefault("linked_truth_nodes", [])
        merged.setdefault("unlock_condition", "默认")
        merged["flaw_id"] = None
        if tier == "fake":
            if not merged.get("fake_of") or merged["fake_of"] not in _CLUE_IDS:
                merged["fake_of"] = "clue_011"
        else:
            merged["fake_of"] = None
        out.append(merged)
    return out


def _fix_truth_nodes(nodes: list) -> list:
    by_id = {n.get("id"): n for n in nodes if isinstance(n, dict) and n.get("id")}
    out = []
    for tid in _TN_IDS:
        src = copy.deepcopy(by_id.get(tid) or {})
        src["id"] = tid
        src.setdefault("name", f"真相节点 {tid[-2:]}")
        src.setdefault("desc", "")
        proofs = [p for p in (src.get("proof_clues") or []) if p in _CLUE_IDS]
        if len(proofs) < 2:
            defaults = {
                "tn_01": ["clue_001", "clue_009"],
                "tn_02": ["clue_003", "clue_004"],
                "tn_03": ["clue_005", "clue_006"],
                "tn_04": ["clue_007", "clue_008"],
                "tn_05": ["clue_011", "clue_010"],
                "tn_06": ["clue_002", "clue_003"],
            }
            proofs = defaults.get(tid, ["clue_001", "clue_002"])
        src["proof_clues"] = proofs[: max(2, len(proofs))]
        out.append(src)
    return out


def _fix_culprit(culprit: dict, world: dict) -> dict:
    c = copy.deepcopy(culprit or {})
    c["character"] = "char_01"
    slot = next((s for s in (world.get("cast_slots") or []) if s.get("id") == "char_01"), {})
    c.setdefault("name", slot.get("name") or "带节奏")
    for key in ("crime", "motive", "method"):
        c.setdefault(key, "")
    chain = [x for x in (c.get("evidence_chain") or []) if x in _CLUE_IDS]
    if len(chain) < 2:
        chain = ["clue_003", "clue_011", "clue_002"]
    c["evidence_chain"] = chain
    acc = c.get("accomplices")
    if not isinstance(acc, list) or not acc:
        c["accomplices"] = [
            {"character": "char_02", "name": "执行者", "role": "被裹挟者", "swayable": True}
        ]
    return c


def _fix_kc_plan(plan: list | None) -> list:
    expected = [{"id": kc, "binds": bind} for kc, bind in KC_COPY]
    if not plan:
        return expected
    by_id = {p.get("id"): p for p in plan if isinstance(p, dict) and p.get("id")}
    return [{"id": kc, "binds": by_id.get(kc, {}).get("binds") or bind} for kc, bind in KC_COPY]


def _fix_memories(memories: dict) -> dict:
    if not isinstance(memories, dict):
        memories = {}
    out = {}
    for cid in _CHAR_IDS:
        versions = memories.get(cid)
        if not versions or len(versions) < 3:
            skel = mock_bible.build("补全")["detail"]["memories"].get(cid, [])
            out[cid] = versions if versions and len(versions) >= 3 else skel
        else:
            out[cid] = versions[:3]
    return out


def _fix_hotfeed(posts: list) -> list:
    if not isinstance(posts, list):
        posts = []
    by_id = {p.get("id"): p for p in posts if isinstance(p, dict) and p.get("id")}
    out = []
    for i in range(1, 9):
        pid = f"post_{i:03d}"
        src = copy.deepcopy(by_id.get(pid) or {})
        src["id"] = pid
        src.setdefault("round", min(3, (i - 1) // 3 + 1))
        src.setdefault("title", "")
        src.setdefault("body", "")
        src.setdefault("author_mask", "网友")
        src.setdefault("is_fake", i % 2 == 0)
        src.setdefault("clue_ref", None)
        if src.get("is_fake") and not src.get("topic_tag"):
            src["topic_tag"] = ("kc_02", "kc_03", "kc_04", "kc_01")[(i - 1) % 4]
        src.setdefault("topic_tag", "")
        src.setdefault("heat_delta", 5)
        src.setdefault("humor_tag", "玩梗")
        out.append(src)
    return out


def _patch_acts(raw: dict, skeleton: dict) -> dict:
    acts_data = raw.get("acts") if isinstance(raw.get("acts"), list) else None
    if not acts_data:
        acts_data = skeleton.get("acts") or []
    skel_acts = {a.get("id"): a for a in (skeleton.get("acts") or []) if a.get("id")}
    fixed = []
    for act_id, stage, ap, verbs in _ACT_SPECS:
        src = next((a for a in acts_data if a.get("id") == act_id), {})
        skel = skel_acts.get(act_id, {})
        row = _merge_missing(copy.deepcopy(src), skel)
        row["id"] = act_id
        row["stage"] = stage
        row["actions_allocated"] = ap
        row["player_verbs"] = verbs
        row.setdefault("name", skel.get("name", act_id))
        row.setdefault("brief", "")
        row.setdefault("info_budget", skel.get("info_budget", 3))
        row.setdefault("must_reveal", [])
        row.setdefault("must_not_reveal", [])
        row.setdefault("twist_beat", "")
        row.setdefault("comedy_beat", "")
        row.setdefault("oh_moment", "")
        row.setdefault("dm_notes", "")
        fixed.append(row)
    return {"acts": fixed}


def _merge_missing(target: Any, skeleton: Any) -> Any:
    if skeleton is None:
        return target
    if target is None:
        return copy.deepcopy(skeleton)
    if isinstance(target, dict) and isinstance(skeleton, dict):
        out = copy.deepcopy(target)
        for key, sk_val in skeleton.items():
            if key not in out or out[key] is None:
                out[key] = copy.deepcopy(sk_val)
            elif isinstance(out[key], dict) and isinstance(sk_val, dict):
                out[key] = _merge_missing(out[key], sk_val)
            elif isinstance(out[key], list) and isinstance(sk_val, list):
                if out[key] and isinstance(out[key][0], dict) and out[key][0].get("id"):
                    out[key] = _merge_list_by_id(out[key], sk_val)
        return out
    return target


def _merge_list_by_id(target_list: list, skel_list: list) -> list:
    skel_by_id = {x.get("id"): x for x in skel_list if isinstance(x, dict) and x.get("id")}
    out = []
    for item in target_list:
        if not isinstance(item, dict):
            out.append(item)
            continue
        iid = item.get("id")
        merged = _merge_missing(item, skel_by_id.get(iid, {}))
        out.append(merged)
    return out


# ------------------------------------------------------------------ 结构校验


def _assert_world(world: dict) -> None:
    if not world.get("title"):
        raise ValueError("world 缺少 title")
    slots = world.get("cast_slots") or []
    if len(slots) != 4 or [s.get("id") for s in slots] != list(_CHAR_IDS):
        raise ValueError("world cast_slots 结构无效")
    locs = world.get("locations") or []
    if len(locs) != 6 or [l.get("id") for l in locs] != list(LOCATION_META.keys()):
        raise ValueError("world locations 结构无效")


def _assert_detail(detail: dict) -> None:
    q = QUOTA["demo"]
    if len(detail.get("characters") or []) != q["chars"]:
        raise ValueError("detail characters 数量无效")
    if len(detail.get("clues") or []) != q["clues"]:
        raise ValueError("detail clues 数量无效")
    if len(detail.get("truth_nodes") or []) != q["truth_nodes"]:
        raise ValueError("detail truth_nodes 数量无效")
    if (detail.get("culprit") or {}).get("character") != "char_01":
        raise ValueError("culprit 必须锁定 char_01")
    tiers: dict[str, int] = {}
    for c in detail.get("clues") or []:
        tiers[c.get("tier")] = tiers.get(c.get("tier"), 0) + 1
        if c.get("flaw_id"):
            raise ValueError("快本禁止 boss_flaw")
    for key, expect in (("public", 6), ("limited", 3), ("hidden", 2), ("fake", 1)):
        if tiers.get(key, 0) != expect:
            raise ValueError(f"线索 tier {key} 配额错误")
    fake = next((c for c in detail.get("clues") or [] if c.get("tier") == "fake"), None)
    if not fake or not fake.get("fake_of"):
        raise ValueError("fake 线索缺少 fake_of")
    if len(detail.get("hotfeed") or []) != q["hotfeed"]:
        raise ValueError("detail hotfeed 数量无效")


def _assert_acts(acts: dict) -> None:
    rows = acts.get("acts") or []
    if len(rows) != 3:
        raise ValueError("acts 必须为 3 幕")
    for row, (_, stage, ap, verbs) in zip(rows, _ACT_SPECS):
        if row.get("stage") != stage or int(row.get("actions_allocated", 0)) != ap:
            raise ValueError(f"幕 {row.get('id')} stage/AP 无效")
        if row.get("player_verbs") != verbs:
            raise ValueError(f"幕 {row.get('id')} player_verbs 无效")
