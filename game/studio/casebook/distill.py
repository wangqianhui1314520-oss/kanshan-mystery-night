"""把权威剧本 kanshan 提炼成「黄金样本」（few-shot 写法范例）。

只读 content/scenarios/kanshan/，产物写 casebook/kanshan_golden.json。
统计数字全部由真实数据计算，不臆造字段：字段名以 kanshan 实际文件为准
（clue tier 实际为 public/limited/hidden/fake/boss_flaw 五档；
 said/heart 双层在 memory/char_XX_v*.json 的 blocks[].layer 中）。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = GAME_ROOT / "content" / "scenarios" / "kanshan"
GOLDEN_PATH = Path(__file__).resolve().parent / "kanshan_golden.json"

VOICE_CHARS = ("char_01", "char_03")

# kanshan 的 acts 不直接携带线索映射；clue_unlocks 按 unlock_condition 动词归类累计：
# act1=默认解锁，act2=evidence/memory/counsel，act3=debate/echo，act4=chat/review。
_ACT_UNLOCK_VERBS = {
    "act1": None,
    "act2": ("evidence", "memory", "counsel"),
    "act3": ("debate", "echo"),
    "act4": ("chat", "review"),
}
_ACT_CLUE_NOTE = (
    "kanshan 未直接标注幕→线索映射；clue_unlocks 按 unlock_condition 动词归类累计"
    "（act1=默认解锁，act2=evidence/memory/counsel，act3=debate/echo，act4=chat/review）"
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_clues(scenario: Path) -> dict[str, dict]:
    clues = {}
    clue_dir = scenario / "clues"
    if clue_dir.is_dir():
        for p in sorted(clue_dir.glob("clue_*.json")):
            data = _load_json(p)
            if data.get("id"):
                clues[data["id"]] = data
    return clues


def _tier_ratio(clues: dict[str, dict]) -> dict[str, int]:
    counter = Counter(c.get("tier") or "unknown" for c in clues.values())
    ordered = {t: counter[t] for t in ("public", "limited", "hidden", "fake", "boss_flaw")}
    for extra, n in sorted(counter.items()):
        if extra not in ordered:
            ordered[extra] = n
    return ordered


def _clue_density(truth: dict, clues: dict[str, dict]) -> dict[str, dict]:
    density = {}
    for node in truth.get("truth_nodes") or []:
        proofs = [p for p in (node.get("proof_clues") or []) if p in clues]
        tier_dist = Counter(clues[p].get("tier") for p in proofs)
        density[node.get("id") or ""] = {
            "name": node.get("name"),
            "proof_count": len(proofs),
            "tier_dist": dict(sorted(tier_dist.items(), key=lambda x: -x[1])),
        }
    return density


def _fake_samples(clues: dict[str, dict]) -> list[dict]:
    samples = []
    for cid in sorted(clues):
        c = clues[cid]
        if c.get("tier") != "fake":
            continue
        samples.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "description": c.get("fact"),
            "fake_of": c.get("fake_of"),
        })
    return samples


def _voice_dual_layer(scenario: Path, characters: dict[str, dict]) -> list[dict]:
    """said/heart 双层取自 memory/char_XX_v*.json 的 blocks[].layer（kanshan 实际字段）。"""
    out = []
    mem_dir = scenario / "memory"
    if not mem_dir.is_dir():
        return out
    for cid in VOICE_CHARS:
        versions = sorted(mem_dir.glob(f"{cid}_v*.json"))
        if not versions:
            continue
        latest = _load_json(versions[-1])
        said = next(
            (b for b in reversed(latest.get("blocks") or [])
             if b.get("layer") == "said" and b.get("integrity") == "edited"),
            None,
        ) or next((b for b in latest.get("blocks") or [] if b.get("layer") == "said"), None)
        heart = next((b for b in latest.get("blocks") or [] if b.get("layer") == "heart"), None)
        if not said and not heart:
            continue
        char = characters.get(cid) or {}
        out.append({
            "char": cid,
            "name": char.get("name") or latest.get("owner"),
            "said": (said or {}).get("text"),
            "said_integrity": (said or {}).get("integrity"),
            "heart": (heart or {}).get("text"),
        })
    return out


def _act_rhythm(scenario: Path, clues: dict[str, dict]) -> tuple[list[dict], str]:
    acts = (_load_json(scenario / "scenario.json").get("acts") or [])
    rows = []
    for act in acts:
        verbs = _ACT_UNLOCK_VERBS.get(act.get("id"))
        if verbs is None:
            n = sum(1 for c in clues.values() if c.get("unlock_condition") in (None, "默认"))
        else:
            n = sum(
                1 for c in clues.values()
                if str(c.get("unlock_condition") or "").split(":", 1)[0] in verbs
            )
        rows.append({
            "id": act.get("id"),
            "name": act.get("name"),
            "stage": act.get("stage"),
            "actions_allocated": act.get("actions_allocated"),
            "clue_unlocks": n,
        })
    return rows, _ACT_CLUE_NOTE


def _relations(truth: dict, booklets: dict[str, dict]) -> list[dict]:
    edges = []
    culprit = truth.get("culprit") or {}
    for acc in culprit.get("accomplices") or []:
        edges.append({
            "from": culprit.get("name"),
            "to": acc.get("name"),
            "note": acc.get("role"),
        })
    for bid, bk in sorted(booklets.items()):
        for cover in (bk.get("covers") or {}).values():
            for imp in cover.get("impressions") or []:
                edges.append({
                    "from": bk.get("name"),
                    "to": imp.get("who"),
                    "note": imp.get("note"),
                })
    return edges


def distill_kanshan(scenario_dir=None) -> dict:
    """读取 kanshan 真实数据，产出结构化黄金样本并写入 kanshan_golden.json。"""
    scenario = Path(scenario_dir) if scenario_dir else DEFAULT_SCENARIO
    if not scenario.is_dir():
        raise FileNotFoundError(f"剧本目录不存在: {scenario}")

    truth = _load_json(scenario / "truth.json")
    timeline = _load_json(scenario / "timeline.json")
    scenario_meta = _load_json(scenario / "scenario.json")

    characters = {}
    char_dir = scenario / "characters"
    if char_dir.is_dir():
        for p in sorted(char_dir.glob("char_*.json")):
            data = _load_json(p)
            characters[data.get("id") or p.stem] = data

    booklets = {}
    booklet_dir = scenario / "booklets"
    if booklet_dir.is_dir():
        for p in sorted(booklet_dir.glob("char_*.json")):
            data = _load_json(p)
            booklets[data.get("id") or p.stem] = data

    clues = _load_clues(scenario)
    tier_ratio = _tier_ratio(clues)
    density = _clue_density(truth, clues)
    acts, act_note = _act_rhythm(scenario, clues)

    golden = {
        "source": str(scenario),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": {
            "clues_total": len(clues),
            "truth_nodes_total": len(truth.get("truth_nodes") or []),
            "timeline_events": len(timeline.get("timeline") or []),
            "acts_total": len(scenario_meta.get("acts") or []),
        },
        "truth_layering": truth.get("truth_summary"),
        "tier_ratio": tier_ratio,
        "clue_density": density,
        "fake_evidence_samples": _fake_samples(clues),
        "voice_dual_layer": _voice_dual_layer(scenario, characters),
        "act_rhythm": acts,
        "act_clue_note": act_note,
        "relations": _relations(truth, booklets),
    }

    GOLDEN_PATH.write_text(
        json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return golden


if __name__ == "__main__":
    sample = distill_kanshan()
    print(f"golden -> {GOLDEN_PATH}")
    print(json.dumps(sample["stats"], ensure_ascii=False))
    print(f"tier_ratio: {sample['tier_ratio']}")
    print(f"fake_samples: {len(sample['fake_evidence_samples'])}")
    print(f"voice_dual_layer: {len(sample['voice_dual_layer'])}")
    print(f"relations: {len(sample['relations'])}")
