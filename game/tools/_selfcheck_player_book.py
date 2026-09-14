"""故事本自检：边界 / 封面不泄密 / 全本有秘密 / 公开栏不写真凶。"""
from __future__ import annotations

import json
from pathlib import Path

from studio import list_jobs, load_player_book, public_snapshot
from studio.paths import SCENARIOS
from studio.player_book import public_cover

FORBIDDEN_PUBLIC_KEYS = ("secrets", "must_not_say", "faction", "guilt", "inner_truth")
LEAK_IN_PUBLIC_TEXT = ("嫁祸", "指使")


def _walk_keys(obj):
    found = set()
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            found.update(k for k in cur if k in FORBIDDEN_PUBLIC_KEYS)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return found


def main() -> int:
    fails = []
    kanshan = list((SCENARIOS / "kanshan").rglob("player_book*"))
    if kanshan:
        fails.append(f"kanshan 被写入故事本: {kanshan}")
    print("kanshan 未被写入", not kanshan)

    jobs = list_jobs()
    ready = [j for j in jobs if j.get("ok")]
    print(f"jobs={len(jobs)} ready={len(ready)}")

    legacy = 0
    for job in ready:
        sid = job["id"]
        root = SCENARIOS / sid
        books = sorted((root / "scripts").glob("player_book_char_*.json"))
        if not books:
            legacy += 1
            continue
        if len(books) != 4:
            fails.append(f"{sid} 故事本数量 {len(books)}")
            continue
        pack = public_snapshot(sid)
        leaked = _walk_keys(pack.get("books"))
        if leaked:
            fails.append(f"{sid} /public.books 含禁键 {leaked}")
        for token in FORBIDDEN_PUBLIC_KEYS:
            if f'"{token}"' in json.dumps(pack, ensure_ascii=False):
                fails.append(f"{sid} /public JSON 含 {token}")
        for fp in books:
            data = json.loads(fp.read_text(encoding="utf-8"))
            pub = " ".join(
                [data.get("you_are") or "", data.get("situation") or ""]
                + list(data.get("known_facts") or [])
            )
            if any(w in pub for w in LEAK_IN_PUBLIC_TEXT):
                fails.append(f"{sid}/{fp.name} 公开栏疑似剧透: {pub[:60]}")
            cover = public_cover(data)
            if set(cover) - {"char_id", "name", "archetype", "you_are", "opening"}:
                fails.append(f"{sid} 封面多键 {cover.keys()}")
        book = load_player_book(sid, "char_01")
        if not book.get("secrets"):
            fails.append(f"{sid} char_01 全本无 secrets")

    print(f"legacy_without_books={legacy} (旧本允许，开局直玩)")
    print("fails", len(fails))
    for line in fails:
        print("FAIL", line)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
