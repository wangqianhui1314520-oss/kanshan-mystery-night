"""闭卷查询与 AI 按本行动的服务侧组装（不改裁决）。"""
from __future__ import annotations

import copy
from pathlib import Path

from engine.booklet import load_library, stage_to_chapter
from engine.stage_machine import Stage

from .scenario_resolve import resolve_session_scenario_dir

try:
    from engine.stage_machine import legal_actions as engine_legal
except ImportError:
    engine_legal = None

_STAGE_LEGAL = {
    "break_ice": ["chat", "advance"],
    "investigate": ["chat", "search", "private_chat", "skill", "counsel", "advance"],
    "round_table": ["chat", "private_chat", "skill", "counsel", "vote", "advance"],
    "accuse": ["vote", "advance"],
    "review": ["advance"],
}

_PUBLIC_DROP = ("faction", "faction_label", "never_say")


def scenario_dir_of(session: dict) -> Path:
    return resolve_session_scenario_dir(session.get("scenario_id"))


def library_of(session: dict):
    return load_library(scenario_dir_of(session))


def role_of(session: dict, player_id: str) -> str:
    pid = str(player_id or "").strip()
    roles = session.get("booklet_roles") or {}
    if pid in roles:
        return str(roles[pid])
    if session.get("mode") == "party":
        for seat in session.get("seats") or session.get("seats_public") or []:
            if isinstance(seat, dict) and seat.get("player_id") == pid and seat.get("char_id"):
                return str(seat["char_id"])
    return "investigator"


def claim_role(session: dict, player_id: str, role_id: str) -> str:
    lib = library_of(session)
    rid = lib.resolve_role(role_id, solo=session.get("mode") != "party")
    session.setdefault("booklet_roles", {})[player_id] = rid
    return rid


def chapter_of(session: dict) -> int:
    return stage_to_chapter(session.get("stage") or "break_ice")


def legal_actions(session: dict) -> list[str]:
    stage = session.get("stage") or Stage.BREAK_ICE.value
    if engine_legal is not None:
        return list(engine_legal(stage))
    return list(_STAGE_LEGAL.get(stage, ["chat"]))


def public_booklet_view(pack: dict) -> dict:
    """广播/列表出口：剥阵营与禁语，禁止把别人的闭卷秘密发出去。

    本人 GET 用 visible_booklet（可留 faction）；WS/列表/他人可见必须走本函数。
    """
    if not isinstance(pack, dict):
        return {}
    out = copy.deepcopy(pack)
    for key in _PUBLIC_DROP:
        out.pop(key, None)
    covers = out.get("covers")
    if isinstance(covers, dict):
        for cover in covers.values():
            if isinstance(cover, dict):
                cover.pop("never_say", None)
    return out


def visible_booklet(session: dict, player_id: str) -> dict:
    lib = library_of(session)
    role = role_of(session, player_id)
    pack = lib.visible_pack(role, chapter_of(session), include_faction=True)
    pack["player_id"] = player_id
    return pack


def other_chars(session: dict, role_id: str) -> list[str]:
    out = []
    for n in session.get("npcs") or []:
        cid = n.get("id") if isinstance(n, dict) else None
        if cid and cid != role_id:
            out.append(cid)
    return out


def _iter_seat_rows(session: dict):
    """seats / seats_public 可能是列表或 player_id→席位表。"""
    for key in ("seats", "seats_public"):
        raw = session.get(key) or []
        if isinstance(raw, dict):
            for pid, seat in raw.items():
                if not isinstance(seat, dict):
                    continue
                row = dict(seat)
                row.setdefault("player_id", pid or seat.get("player_id"))
                yield row
        elif isinstance(raw, list):
            for seat in raw:
                if isinstance(seat, dict):
                    yield seat


def vacant_ai_roles(session: dict) -> list[str]:
    """空席角色 id：无人真人认领、非调查员，供 AI 按本行动。"""
    roles: list[str] = []
    for n in session.get("npcs") or []:
        cid = n.get("id") if isinstance(n, dict) else None
        if cid and cid not in roles:
            roles.append(str(cid))
    if not roles:
        roles = [f"char_{i:02d}" for i in range(1, 9)]

    claimed = {str(rid) for rid in (session.get("booklet_roles") or {}).values()
               if rid}

    occupied: set[str] = set()
    for seat in _iter_seat_rows(session):
        pid = seat.get("player_id")
        cid = seat.get("char_id")
        if cid and pid and seat.get("is_ai") is not True and seat.get("connected"):
            occupied.add(str(cid))

    return [rid for rid in roles
            if rid != "investigator" and rid not in claimed and rid not in occupied]


def take_wave_roles(session: dict, n: int | None = None) -> list[str]:
    """本波出手的空席。n 为空或 <=0 时整桌空席各走一步（像真人围坐一轮）。"""
    vacant = vacant_ai_roles(session)
    cursor = int(session.get("ai_wave_cursor") or 0)
    if n is None or int(n) <= 0:
        take_n = len(vacant)
    else:
        take_n = int(n)
    try:
        from agents.seat_runner import rotate_roles
        picked, nxt = rotate_roles(vacant, cursor, take_n)
    except Exception:
        if not vacant:
            picked, nxt = [], 0
        else:
            take_n = max(0, min(take_n, len(vacant)))
            picked = [vacant[(cursor + i) % len(vacant)] for i in range(take_n)]
            nxt = (cursor + take_n) % len(vacant) if vacant else 0
    session["ai_wave_cursor"] = nxt
    return picked
