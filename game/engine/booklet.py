"""分幕闭卷：公共本 + 调查员本 + 8 嫌疑人本。

玩家可见性：只发自己的本；封 A=第一章（破冰+搜证），封 B=第二章，封 C=第三章。
里层 Boss（看山设局）禁止写入任何 cover。faction 只进「仅自己可见」包。
AI 游玩读 agent_prompt / play_hints，不得把秘密写进公共事件。
"""
from __future__ import annotations

import json
from pathlib import Path

COVERS = ("A", "B", "C")
BOSS_BAN = ("看山设局", "你们破的局", "扮系统提示音", "假失踪", "指认：DM")
FACTION_LABEL = {
    "truth": "求真",
    "pollution": "污染",
    "swayable": "摇摆（可策反）",
    "": "",
}


def stage_to_chapter(stage: str) -> int:
    """引擎 stage → 玩家章节（与前端 act 对齐）。"""
    return {
        "break_ice": 1,
        "investigate": 1,
        "round_table": 2,
        "accuse": 3,
        "review": 3,
    }.get(str(stage or ""), 1)


def chapter_to_covers(chapter: int) -> tuple[str, ...]:
    chapter = max(1, min(3, int(chapter or 1)))
    return COVERS[:chapter]


def _cover_dict(raw: dict) -> dict:
    hints = dict(raw.get("play_hints") or {})
    hints.setdefault("prefer_actions", [])
    hints.setdefault("search_locations", [])
    hints.setdefault("search_keywords", [])
    hints.setdefault("chat_style", "")
    hints.setdefault("avoid", [])
    hints.setdefault("must_not", [])
    return {
        "title": str(raw.get("title") or ""),
        "you_are": str(raw.get("you_are") or ""),
        "tonight": str(raw.get("tonight") or ""),
        "impressions": list(raw.get("impressions") or []),
        "task": str(raw.get("task") or ""),
        "never_say": str(raw.get("never_say") or ""),
        "play_hints": hints,
        # 角色剧本扩展：阶段里程碑与个人结局只对本人可见。
        "milestones": [str(x) for x in (raw.get("milestones") or [])],
        "personal_endings": [str(x) for x in (raw.get("personal_endings") or [])],
    }


class BookletLibrary:
    def __init__(self, scenario_dir: Path | str):
        self.scenario_dir = Path(scenario_dir)
        self.dir = self.scenario_dir / "booklets"
        self.public: dict = {}
        self.roles: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        self.public = {}
        self.roles = {}
        if not self.dir.is_dir():
            return
        for path in sorted(self.dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not data.get("id"):
                continue
            covers = {}
            for key in COVERS:
                raw_cover = dict((data.get("covers") or {}).get(key) or {})
                covers[key] = _cover_dict(raw_cover)
            row = {
                "id": data["id"],
                "name": data.get("name") or data["id"],
                "role_kind": data.get("role_kind") or "suspect",
                "faction": data.get("faction") or "",
                "public_title": data.get("public_title") or "",
                "covers": covers,
            }
            self._assert_no_boss(row)
            if row["id"] == "public" or row["role_kind"] == "public":
                self.public = row
            else:
                self.roles[row["id"]] = row

    def _assert_no_boss(self, row: dict) -> None:
        blob = json.dumps(row, ensure_ascii=False)
        for banned in BOSS_BAN:
            if banned in blob:
                raise ValueError(f"booklet {row.get('id')} 含里层禁语：{banned}")

    def role_ids(self) -> list[str]:
        return sorted(self.roles)

    def catalog(self) -> list[dict]:
        """选角预览：不含秘密、不含 faction。"""
        out = []
        for rid, row in sorted(self.roles.items()):
            a = row["covers"]["A"]
            out.append({
                "id": rid,
                "name": row["name"],
                "role_kind": row["role_kind"],
                "public_title": row["public_title"],
                "preview": a["you_are"][:80],
            })
        return out

    def resolve_role(self, role_id: str | None, *, solo: bool = True) -> str:
        rid = str(role_id or "").strip()
        if rid in self.roles:
            return rid
        if solo and "investigator" in self.roles:
            return "investigator"
        return "investigator" if "investigator" in self.roles else next(iter(self.roles), "")

    def visible_pack(self, role_id: str, chapter: int = 1,
                     *, include_faction: bool = True) -> dict:
        """仅自己可见的闭卷。chapter 1/2/3 → 封 A / A+B / A+B+C。"""
        rid = self.resolve_role(role_id)
        row = self.roles.get(rid) or {}
        letters = chapter_to_covers(chapter)
        covers = {k: row.get("covers", {}).get(k, _cover_dict({})) for k in letters}
        pack = {
            "role_id": rid,
            "name": row.get("name") or rid,
            "role_kind": row.get("role_kind") or "suspect",
            "public_title": row.get("public_title") or "",
            "chapter": max(1, min(3, int(chapter or 1))),
            "unlocked": list(letters),
            "public": {
                "name": self.public.get("name") or "公共剧本",
                "pages": [
                    self.public.get("covers", {}).get("A", {}).get("you_are") or "",
                    self.public.get("covers", {}).get("A", {}).get("tonight") or "",
                    self.public.get("covers", {}).get("A", {}).get("task") or "",
                ],
            },
            "covers": covers,
        }
        if include_faction:
            fac = row.get("faction") or ""
            pack["faction"] = fac
            pack["faction_label"] = FACTION_LABEL.get(fac, fac)
        return pack

    def public_preview(self, role_id: str) -> dict:
        """无会话预览：只要封 A 的人设，不要秘密/阵营/封 B/C。"""
        rid = self.resolve_role(role_id)
        row = self.roles.get(rid) or {}
        a = row.get("covers", {}).get("A") or _cover_dict({})
        return {
            "role_id": rid,
            "name": row.get("name") or rid,
            "role_kind": row.get("role_kind") or "suspect",
            "public_title": row.get("public_title") or "",
            "you_are": a.get("you_are") or "",
            "preview_task": a.get("task") or "",
        }

    def merged_hints(self, role_id: str, chapter: int = 1) -> dict:
        pack = self.visible_pack(role_id, chapter, include_faction=True)
        merged = {
            "prefer_actions": [],
            "search_locations": [],
            "search_keywords": [],
            "chat_style": "",
            "avoid": [],
            "must_not": [],
        }
        for letter in pack.get("unlocked") or []:
            h = ((pack["covers"].get(letter) or {}).get("play_hints") or {})
            for key in ("prefer_actions", "search_locations", "search_keywords",
                        "avoid", "must_not"):
                for item in h.get(key) or []:
                    if item and item not in merged[key]:
                        merged[key].append(item)
            if h.get("chat_style"):
                merged["chat_style"] = h["chat_style"]
        return merged

    def agent_prompt(self, role_id: str, chapter: int = 1) -> str:
        """注入 NPC / 玩家 Agent 的闭卷正文（按幕裁切）。"""
        pack = self.visible_pack(role_id, chapter, include_faction=True)
        lines = [
            f"【你的闭卷 · {pack['name']} · 第{pack['chapter']}章已开到封 {','.join(pack['unlocked'])}】",
            f"公开栏：{pack.get('public_title') or ''}",
        ]
        if pack.get("faction_label"):
            lines.append(f"阵营（仅你可见）：{pack['faction_label']}")
        pub = pack.get("public") or {}
        if pub.get("pages"):
            lines.append("【公共剧本】")
            lines.extend(p for p in pub["pages"] if p)
        for letter in pack.get("unlocked") or []:
            c = pack["covers"][letter]
            lines.append(f"【{c.get('title') or letter}】")
            lines.append(f"你是谁：{c.get('you_are')}")
            lines.append(f"今晚你记得：{c.get('tonight')}")
            lines.append(f"本封任务：{c.get('task')}")
            for milestone in c.get("milestones") or []:
                lines.append(f"本幕行动目标：{milestone}")
            lines.append(f"不能说：{c.get('never_say')}")
            for imp in c.get("impressions") or []:
                lines.append(f"对{imp.get('who', '?')}的印象：{imp.get('note', '')}")
        hints = self.merged_hints(role_id, chapter)
        if hints.get("must_not"):
            lines.append("硬禁：" + "；".join(hints["must_not"]))
        if hints.get("avoid"):
            lines.append("尽量避开：" + "；".join(hints["avoid"]))
        lines.append("规则：只根据已开启的封行动；未开的封当作不存在。禁止向玩家透露闭卷文件本身。禁止编造本上没有的证据。")
        return "\n".join(lines)


_CACHE: dict[str, BookletLibrary] = {}
_CACHE_REVISIONS: dict[str, tuple] = {}


def load_library(scenario_dir: Path | str) -> BookletLibrary:
    key = str(Path(scenario_dir).resolve())
    revision = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                     for p in sorted((Path(key) / "booklets").glob("*.json")))
    lib = _CACHE.get(key)
    if lib is None or _CACHE_REVISIONS.get(key) != revision:
        lib = BookletLibrary(scenario_dir)
        _CACHE[key] = lib
        _CACHE_REVISIONS[key] = revision
    return lib
