"""Generated-pack evidence contract shared by mock, LLM and compiler paths."""

from __future__ import annotations

from typing import Any


# These links reuse existing clues from the same causal chain. They make every
# demo truth node composeable without changing clue count, tier or location.
_PREFERRED_LINKS = {
    "tn_01": ("clue_001", "clue_009", "clue_011"),
    "tn_02": ("clue_003", "clue_004", "clue_010"),
    "tn_03": ("clue_005", "clue_006", "clue_011"),
    "tn_04": ("clue_007", "clue_008", "clue_010"),
    "tn_05": ("clue_010", "clue_011", "clue_003"),
    "tn_06": ("clue_002", "clue_003", "clue_011"),
}


def ensure_evidence_playability(detail: dict[str, Any]) -> dict[str, Any]:
    """Align ``proof_clues`` and ``linked_truth_nodes`` for generated packs.

    The runtime composes cards from clue links, while authoring tools expose
    proof lists. Keeping both views synchronized prevents a package from
    passing validation while producing fewer than two distinct evidence cards.
    The function mutates and returns ``detail`` for existing pipeline callers.
    """
    if not isinstance(detail, dict):
        return detail
    clues = {
        str(row.get("id")): row
        for row in (detail.get("clues") or [])
        if isinstance(row, dict) and row.get("id")
    }
    nodes = [
        row for row in (detail.get("truth_nodes") or [])
        if isinstance(row, dict) and row.get("id")
    ]
    node_ids = {str(row["id"]) for row in nodes}
    real_clues = {
        cid: row for cid, row in clues.items()
        if row.get("tier") != "fake"
    }

    # Remove dangling node references first; validation should report malformed
    # source data rather than counting a phantom link as a playable one.
    for clue in real_clues.values():
        clue["linked_truth_nodes"] = [
            str(tn) for tn in (clue.get("linked_truth_nodes") or [])
            if str(tn) in node_ids
        ]

    for node in nodes:
        tid = str(node["id"])
        links = [
            cid for cid, clue in real_clues.items()
            if tid in (clue.get("linked_truth_nodes") or [])
        ]
        preferred = list(_PREFERRED_LINKS.get(tid, ()))
        for cid in preferred + sorted(real_clues):
            if len(links) >= 3:
                break
            if cid not in real_clues or cid in links:
                continue
            real_clues[cid].setdefault("linked_truth_nodes", []).append(tid)
            links.append(cid)
        # proof_clues is the author-facing projection of the same runtime set.
        node["proof_clues"] = sorted(dict.fromkeys(links))

    # Fake clues never participate in evidence composition.
    for clue in clues.values():
        if clue.get("tier") == "fake":
            clue["linked_truth_nodes"] = []
    return detail


def linked_clues_by_node(
    clues: dict[str, dict], truth_nodes: list[dict]
) -> dict[str, set[str]]:
    """Return valid non-fake clue ids grouped by truth node."""
    valid_nodes = {str(row.get("id")) for row in truth_nodes if row.get("id")}
    grouped: dict[str, set[str]] = {tid: set() for tid in valid_nodes}
    for cid, clue in clues.items():
        if clue.get("tier") == "fake":
            continue
        for tid in clue.get("linked_truth_nodes") or []:
            if str(tid) in valid_nodes:
                grouped[str(tid)].add(str(cid))
    return grouped
