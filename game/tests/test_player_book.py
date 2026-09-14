"""创一本 · 每人一本故事本（认约 docs/PLAYER_BOOK.md）。

只测契约：build_books / public_cover / generate 落盘 / 闸门 / 可选 REST。
零 LLM、不写 kanshan。pytest 从 game/ 运行。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio import generate, public_snapshot, validate_dir
from studio import scenario_dir as studio_scenario_dir
from studio.tiers import PRESET_SEEDS

BOOK_GATE = "BOOK: 每个角色必须有故事本"
COVER_FORBIDDEN = frozenset({"secrets", "must_not_say", "faction", "guilt"})
PUBLIC_JSON_FORBIDDEN = ('"secrets"', '"guilt"', '"faction"')


def _copy_tree_safe(src: Path, dest: Path) -> None:
    """Windows 下 shutil.copytree 偶发 WinError 2，改字节流复制。"""
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.iterdir():
        target = dest / path.name
        if path.is_dir():
            _copy_tree_safe(path, target)
        else:
            target.write_bytes(path.read_bytes())


def _minimal_bibles() -> tuple[dict, dict, dict]:
    """4 席最小圣经，每人带可识别的 guilt / motive 原文。"""
    world = {
        "hook": "全员被锁在 24 小时热榜机房里",
        "world_rules": ["不出真相，不出此门"],
        "surface_truth": "对外口径是系统例行维护",
        "locations": [{"id": "loc_reception", "name": "前台"}],
    }
    characters = []
    for i in range(1, 5):
        characters.append({
            "id": f"char_0{i}",
            "name": f"角色{i}",
            "archetype": "圆桌席位",
            "faction": "truth",
            "public": {"bio": f"公开人设{i}，今晚只讲能说的话。"},
            "secret": {
                "motive": f"UNIQUE_MOTIVE_{i}_先保住自己的把柄",
                "alibi": f"声称一直在前台{i}",
                "guilt": f"UNIQUE_GUILT_{i}_按下删除并准备嫁祸旁人",
            },
            "goal": f"活过这一局{i}",
        })
    detail = {"characters": characters}
    acts = {"acts": [{"id": "act1", "name": "开场锁门", "brief": "先自我介绍再搜证"}]}
    return world, detail, acts


@pytest.fixture(scope="module")
def ready_job():
    return generate(PRESET_SEEDS[0], use_llm=False)


class TestBuildBooks:
    def test_four_books_hide_guilt_keep_secrets(self):
        pb = pytest.importorskip("studio.player_book")
        world, detail, acts = _minimal_bibles()
        books = pb.build_books(world, detail, acts)
        assert len(books) == 4
        by_id = {b.get("char_id"): b for b in books}
        assert set(by_id) == {"char_01", "char_02", "char_03", "char_04"}

        for ch in detail["characters"]:
            book = by_id[ch["id"]]
            guilt = ch["secret"]["guilt"]
            motive = ch["secret"]["motive"]
            you_are = book.get("you_are") or ""
            assert you_are, f"{ch['id']} 缺 you_are"
            assert guilt not in you_are
            secrets = book.get("secrets") or []
            blob = "\n".join(str(s) for s in secrets)
            assert guilt in blob, f"{ch['id']} secrets 应含 guilt 原文"
            assert motive in blob, f"{ch['id']} secrets 应含 motive 原文"


class TestPublicCover:
    def test_cover_keys_omit_secrets(self):
        pb = pytest.importorskip("studio.player_book")
        cover = pb.public_cover({
            "char_id": "char_01",
            "name": "热搜主理",
            "archetype": "把信息当武器的人",
            "you_are": "你是「热搜主理」，把信息当武器的人。",
            "secrets": ["热搜日志是我让人删的"],
            "must_not_say": ["不可主动承认删除令"],
            "faction": "pollution",
            "guilt": "遥控按下删除",
            "opening": {"time": "锁门之后", "location": "前台", "first_step": "先说话"},
        })
        assert COVER_FORBIDDEN.isdisjoint(cover.keys())
        found: set[str] = set()
        stack = [cover]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                found.update(k for k in obj if k in COVER_FORBIDDEN)
                stack.extend(obj.values())
            elif isinstance(obj, list):
                stack.extend(obj)
        assert not found, f"public_cover 含禁键：{found}"


class TestGenerateBooks:
    def test_gate_ok(self, ready_job):
        assert ready_job["gate"]["ok"], ready_job["gate"].get("errors")

    def test_four_json_and_md_contain_you_are(self, ready_job):
        root = studio_scenario_dir(ready_job["id"])
        scripts = root / "scripts"
        for i in range(1, 5):
            cid = f"char_0{i}"
            json_path = scripts / f"player_book_{cid}.json"
            md_path = scripts / f"player_book_{cid}.md"
            assert json_path.is_file(), f"缺 {json_path.name}"
            assert md_path.is_file(), f"缺 {md_path.name}"
            assert "你是" in md_path.read_text(encoding="utf-8")

    def test_public_snapshot_books_no_leak(self, ready_job):
        pack = public_snapshot(ready_job["id"])
        assert len(pack["books"]) == 4
        text = json.dumps(pack, ensure_ascii=False)
        leaked = [token for token in PUBLIC_JSON_FORBIDDEN if token in text]
        assert not leaked, f"public JSON 含禁串：{leaked}"


class TestBookGate:
    def test_missing_book_json_triggers_literal(self, ready_job, tmp_path):
        src = studio_scenario_dir(ready_job["id"])
        dest = tmp_path / ready_job["id"]
        _copy_tree_safe(src, dest)

        books = sorted((dest / "scripts").glob("player_book_char_*.json"))
        assert books, "生成目录应含故事本 json"
        books[0].unlink()

        gate = validate_dir(dest)
        assert BOOK_GATE in gate["errors"], gate["errors"]


def _app_has_route(path: str, method: str = "GET") -> bool:
    try:
        from server.main import app
    except Exception:
        return False
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        methods = getattr(route, "methods", None) or set()
        if method in methods:
            return True
    return False


class TestPlayerBookOptionalApi:
    @pytest.fixture()
    def client(self):
        pytest.importorskip("fastapi")
        try:
            from fastapi.testclient import TestClient
            from server.main import app
        except Exception as exc:
            pytest.skip(f"app 无法装载：{exc}")
        with TestClient(app) as c:
            yield c

    def test_get_books_covers(self, client, ready_job):
        if not _app_has_route("/api/studio/{scenario_id}/books"):
            pytest.skip("GET /api/studio/{id}/books 尚未装载")
        resp = client.get(f"/api/studio/{ready_job['id']}/books")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True
        assert len(body.get("items") or []) == 4
        text = json.dumps(body, ensure_ascii=False)
        leaked = [token for token in PUBLIC_JSON_FORBIDDEN if token in text]
        assert not leaked, f"books 列表含禁串：{leaked}"

    def test_get_one_book(self, client, ready_job):
        if not _app_has_route("/api/studio/{scenario_id}/book/{char_id}"):
            pytest.skip("GET /api/studio/{id}/book/{char_id} 尚未装载")
        resp = client.get(f"/api/studio/{ready_job['id']}/book/char_01")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True
        book = body.get("book") or {}
        assert book.get("char_id") == "char_01"
        assert book.get("you_are")
        assert book.get("secrets")
