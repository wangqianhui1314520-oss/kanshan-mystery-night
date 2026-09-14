"""游玩角色故事本。认约 docs/PLAYER_BOOK.md。零 LLM。"""

from __future__ import annotations

import json
import re
from pathlib import Path

COVER_KEYS = ("char_id", "name", "archetype", "you_are")
SECRET_KEYS = frozenset({"secrets", "must_not_say", "faction", "guilt", "inner_truth"})


def build_books(world: dict, detail: dict, acts: dict) -> list[dict]:
    world = world or {}
    detail = detail or {}
    acts = acts or {}
    chars = [c for c in (detail.get("characters") or []) if isinstance(c, dict) and c.get("id")]
    names = {c["id"]: c.get("name") or c["id"] for c in chars}
    opening = _opening(world, acts)
    situation = _situation(world)
    books = []
    for ch in chars:
        books.append(_book_of(ch, chars, names, world, situation, opening))
    return books


def render_md(book: dict) -> str:
    book = player_view(book)
    name = book.get("name") or book.get("char_id") or "未名"
    lines = [
        f"# 你是「{name}」",
        "",
        book.get("you_are") or "",
        "",
        book.get("situation") or "",
        "",
        "## 你的任务（本局目标）",
        "",
    ]
    for g in book.get("goals") or []:
        lines.append(f"- {g}")
    if not book.get("goals"):
        lines.append("- 活过这一局，把你看见的说圆")
    lines += ["", "## 你掌握的公开信息", ""]
    for f in book.get("known_facts") or []:
        lines.append(f"- {f}")
    lines += ["", "## 你隐瞒的事（不可主动说出，除非被证据戳穿）", ""]
    for s in book.get("secrets") or []:
        lines.append(f"- {s}")
    if book.get("must_not_say"):
        lines += ["", "### 绝对不能先开口的", ""]
        for s in book["must_not_say"]:
            lines.append(f"- {s}")
    op = book.get("opening") or {}
    lines += [
        "",
        "## 开局提示",
        "",
        f"- 当前时间：{op.get('time') or '锁门之后'}",
        f"- 你所在的场景：{op.get('location') or '圆桌'}",
        f"- 建议第一步：{op.get('first_step') or '先自我介绍，再搜公开线索'}",
    ]
    rels = book.get("relations") or []
    if rels:
        lines += ["", "## 圆桌上的其他人", ""]
        for r in rels:
            hint = r.get("hint") or ""
            lines.append(f"- {r.get('name') or r.get('char_id')}：{hint}")
    return "\n".join(lines).rstrip() + "\n"


def public_cover(book: dict) -> dict:
    book = book or {}
    op = book.get("opening") if isinstance(book.get("opening"), dict) else {}
    return {
        "char_id": book.get("char_id") or book.get("id") or "",
        "name": book.get("name") or "",
        "archetype": book.get("archetype") or "",
        "you_are": book.get("you_are") or "",
        "opening": {"location": (op.get("location") or "")},
    }


def player_view(book: dict) -> dict:
    book = dict(book or {})
    cid = book.get("char_id") or book.get("id") or ""
    op = book.get("opening") if isinstance(book.get("opening"), dict) else {}
    rels = []
    for r in book.get("relations") or []:
        if not isinstance(r, dict):
            continue
        rels.append({
            "char_id": r.get("char_id") or "",
            "name": r.get("name") or "",
            "hint": r.get("hint") or "",
        })
    return {
        "char_id": cid,
        "name": book.get("name") or "",
        "archetype": book.get("archetype") or "",
        "you_are": book.get("you_are") or "",
        "situation": book.get("situation") or "",
        "goals": _strs(book.get("goals")),
        "known_facts": _strs(book.get("known_facts")),
        "secrets": _strs(book.get("secrets")),
        "must_not_say": _strs(book.get("must_not_say")),
        "opening": {
            "time": op.get("time") or "锁门之后",
            "location": op.get("location") or "",
            "first_step": op.get("first_step") or "先在圆桌自我介绍，再搜公开线索",
        },
        "relations": rels,
    }


def write_books(scenario_dir: Path, books: list[dict]) -> None:
    root = Path(scenario_dir)
    sdir = root / "scripts"
    if sdir.exists():
        for old in sdir.glob("player_book_*"):
            old.unlink()
    sdir.mkdir(parents=True, exist_ok=True)
    for raw in books or []:
        book = player_view(raw)
        cid = book["char_id"]
        if not cid:
            continue
        (sdir / f"player_book_{cid}.json").write_text(
            json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (sdir / f"player_book_{cid}.md").write_text(render_md(book), encoding="utf-8")


def load_book(scenario_dir: Path, char_id: str) -> dict:
    cid = str(char_id or "").strip()
    if not re.fullmatch(r"char_\d+", cid):
        raise FileNotFoundError(cid or "missing")
    path = Path(scenario_dir) / "scripts" / f"player_book_{cid}.json"
    if not path.is_file():
        raise FileNotFoundError(cid)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or (data.get("char_id") or data.get("id")) != cid:
        raise FileNotFoundError(cid)
    return player_view(data)


def list_covers(scenario_dir: Path) -> list[dict]:
    sdir = Path(scenario_dir) / "scripts"
    if not sdir.is_dir():
        return []
    out = []
    for f in sorted(sdir.glob("player_book_char_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(public_cover(data))
    return out


def _book_of(ch: dict, chars: list[dict], names: dict, world: dict,
             situation: str, opening: dict) -> dict:
    cid = ch["id"]
    name = ch.get("name") or cid
    arch = ch.get("archetype") or ""
    pub = ch.get("public") if isinstance(ch.get("public"), dict) else {}
    bio = (pub.get("bio") or "").strip()
    secret = ch.get("secret") if isinstance(ch.get("secret"), dict) else {}
    you_are = _you_are(name, arch, bio)
    goal = (ch.get("goal") or "").strip()
    goals = [goal] if goal else ["活过这一局，把你看见的说圆"]
    alibi = (secret.get("alibi") or "").strip()
    motive = (secret.get("motive") or "").strip()
    guilt = (secret.get("guilt") or "").strip()
    known = [situation]
    if alibi:
        known.append(f"你对外坚持：{alibi}")
    secrets = [s for s in (motive, guilt) if s]
    must = []
    if guilt:
        must.append("不可主动承认这件事：" + _clip(guilt, 42))
    if motive:
        must.append("不可先把真实动机摊在桌面上")
    rels = []
    for other in chars:
        oid = other.get("id")
        if oid == cid:
            continue
        opub = other.get("public") if isinstance(other.get("public"), dict) else {}
        hint = (opub.get("bio") or other.get("archetype") or "").strip()
        rels.append({
            "char_id": oid,
            "name": names.get(oid, other.get("name") or oid),
            "hint": _clip(hint, 36) or "圆桌上的另一张脸",
        })
    return player_view({
        "char_id": cid,
        "name": name,
        "archetype": arch,
        "you_are": you_are,
        "situation": situation,
        "goals": goals,
        "known_facts": known,
        "secrets": secrets,
        "must_not_say": must,
        "opening": opening,
        "relations": rels,
    })


def _you_are(name: str, arch: str, bio: str) -> str:
    head = f"你是「{name}」"
    if arch:
        head += f"，{arch}"
    head += "。"
    if bio:
        return head + bio
    return head + "今晚你被锁在局里，必须把自己的故事说圆。"


def _situation(world: dict) -> str:
    hook = (world.get("hook") or "").strip()
    rules = [str(r).strip() for r in (world.get("world_rules") or []) if str(r).strip()]
    lock = ""
    for r in rules:
        if "出" in r or "锁" in r or "门" in r:
            lock = r
            break
    if hook and lock and lock not in hook:
        return f"{hook} {lock}"
    return hook or lock or "大门已锁定。不出真相，不出此门。"


def _opening(world: dict, acts: dict) -> dict:
    act_list = acts.get("acts") if isinstance(acts, dict) else acts
    act1 = {}
    if isinstance(act_list, list) and act_list:
        act1 = act_list[0] if isinstance(act_list[0], dict) else {}
    locs = world.get("locations") or []
    loc_name = ""
    if isinstance(locs, list) and locs:
        loc_name = (locs[0].get("name") if isinstance(locs[0], dict) else "") or ""
    return {
        "time": "锁门之后",
        "location": loc_name or "圆桌",
        "first_step": (act1.get("brief") or "").strip() or "先在圆桌自我介绍，再搜公开线索",
    }


def _strs(val) -> list[str]:
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


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"
