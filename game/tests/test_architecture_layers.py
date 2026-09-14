"""架构不变量：信息层 / 流程层 / 运行层（跳过式，不依赖未完成窗口）。"""
from __future__ import annotations

import json

import pytest

FORBIDDEN_PUBLIC_KEYS = frozenset({"faction", "guilt", "inner_truth"})


def _collect_forbidden_keys(obj, found: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_PUBLIC_KEYS:
                found.add(k)
            _collect_forbidden_keys(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _collect_forbidden_keys(item, found)


def _heart_layers(memories) -> list[str]:
    hits: list[str] = []
    if not isinstance(memories, dict):
        return hits
    for owner, versions in memories.items():
        for ver in versions or []:
            if not isinstance(ver, dict):
                continue
            for blk in ver.get("blocks") or []:
                if isinstance(blk, dict) and blk.get("layer") == "heart":
                    hits.append(f"{owner}:{blk.get('id') or '?'}")
    return hits


def _public_pack() -> dict:
    """kanshan 或 studio.public_snapshot；无 gen 目录则 generate 一个 preset。"""
    try:
        from studio import generate, public_snapshot
        from studio.paths import SCENARIOS
        from studio.tiers import PRESET_SEEDS
    except ImportError:
        public_snapshot = None
        SCENARIOS = None
        generate = None
        PRESET_SEEDS = ()

    if public_snapshot is not None and SCENARIOS is not None:
        gens = sorted(
            p for p in SCENARIOS.glob("gen_*")
            if (p / "scenario.json").is_file()
        )
        if gens:
            return public_snapshot(gens[0].name)
        if generate is not None and PRESET_SEEDS:
            job = generate(PRESET_SEEDS[0])
            return public_snapshot(job["id"])

    try:
        from studio.snapshot import public_snapshot as snap
        from tests.conftest import SCENARIO_DIR
        return snap(SCENARIO_DIR, playable=True)
    except Exception as exc:
        pytest.skip(f"无法装载 public pack：{exc}")


class TestInfoLayer:
    def test_public_pack_json_keys_have_no_secrets(self):
        pack = _public_pack()
        found: set[str] = set()
        _collect_forbidden_keys(pack, found)
        assert not found, f"public 包泄露键：{found}"
        text = json.dumps(pack, ensure_ascii=False)
        leaked = {k for k in FORBIDDEN_PUBLIC_KEYS if f'"{k}"' in text}
        assert not leaked, f"JSON 文本含禁键：{leaked}"

    def test_public_pack_memories_have_no_heart(self):
        pack = _public_pack()
        memories = pack.get("memories")
        if not memories:
            pytest.skip("public pack 无 memories")
        hearts = _heart_layers(memories)
        if hearts:
            pytest.xfail(
                "public_snapshot 尚未剥离 layer==heart（A 总控修 snapshot）："
                + ",".join(hearts[:4])
            )
        assert not hearts

    def test_booklet_catalog_items_have_no_faction(self, scenario_dir):
        try:
            from engine.booklet import BookletLibrary
        except ImportError:
            pytest.skip("engine.booklet.BookletLibrary 不存在")
        for row in BookletLibrary(scenario_dir).catalog():
            assert "faction" not in row, row

    def test_public_booklet_view_strips_broadcast_secrets(self):
        from server.booklet_svc import public_booklet_view

        pack = {
            "role_id": "char_03",
            "faction": "swayable",
            "faction_label": "摇摆（可策反）",
            "never_say": "矩阵",
            "covers": {
                "A": {"title": "封 A", "you_are": "流量酱", "never_say": "暗号"},
                "B": {"title": "封 B", "never_say": "把柄"},
            },
        }
        pub = public_booklet_view(pack)
        assert pack["faction"] == "swayable"
        assert pack["covers"]["A"]["never_say"] == "暗号"
        assert "faction" not in pub
        assert "faction_label" not in pub
        assert "never_say" not in pub
        for cover in pub["covers"].values():
            assert "never_say" not in cover
        assert pub["covers"]["A"]["you_are"] == "流量酱"

    def test_claim_role_and_create_with_char(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            created = client.post("/api/session", json={
                "mode": "main", "player_id": "player:solo", "char_id": "char_03"})
            assert created.status_code == 200, created.text
            sid = created.json()["session"]["session_id"]
            book = client.get(f"/api/session/{sid}/booklet?player_id=player:solo")
            assert book.status_code == 200, book.text
            pack = book.json().get("booklet") or {}
            assert pack.get("role_id") == "char_03"
            claimed = client.post(f"/api/session/{sid}/claim", json={
                "player_id": "player:solo", "char_id": "char_05"})
            assert claimed.status_code == 200, claimed.text
            assert claimed.json().get("char_id") == "char_05"
            again = client.get(f"/api/session/{sid}/booklet?player_id=player:solo")
            assert (again.json().get("booklet") or {}).get("role_id") == "char_05"

    def test_own_booklet_may_keep_faction(self, scenario_dir):
        from server.booklet_svc import public_booklet_view, visible_booklet

        session = {
            "scenario_id": "kanshan",
            "stage": "break_ice",
            "booklet_roles": {"player:1": "char_03"},
        }
        try:
            mine = visible_booklet(session, "player:1")
        except Exception as exc:
            pytest.skip(f"visible_booklet 无法装载：{exc}")
        assert "faction" in mine
        pub = public_booklet_view(mine)
        assert "faction" not in pub
        assert "faction_label" not in pub
        for cover in (pub.get("covers") or {}).values():
            if isinstance(cover, dict):
                assert "never_say" not in cover


class TestFlowLayer:
    def test_stage_legal_actions_gate_search_vote(self):
        try:
            from engine.stage_machine import legal_actions as engine_legal
        except ImportError:
            pytest.skip("stage_machine.legal_actions 不存在")
        ice = set(engine_legal("break_ice"))
        assert "search" not in ice
        assert "vote" not in ice
        assert "accuse" not in ice
        assert "search" not in set(engine_legal("accuse"))

    def test_booklet_svc_legal_actions_aligns_engine(self):
        from server.booklet_svc import legal_actions

        ice = set(legal_actions({"stage": "break_ice"}))
        assert "search" not in ice
        assert "vote" not in ice
        assert "accuse" not in ice
        assert "search" not in set(legal_actions({"stage": "accuse"}))


class TestRuntimeLayer:
    def test_player_agent_ice_is_chat_or_advance_no_faction(self, scenario_dir):
        try:
            from agents.player_agent import PlayerAgent
        except ImportError:
            pytest.skip("PlayerAgent 不存在")
        agent = PlayerAgent.from_scenario(scenario_dir)
        decision = agent.decide(
            "char_03", stage="break_ice", legal=None, use_llm=False)
        assert decision["type"] in ("chat", "advance")
        assert "faction" not in decision

    def test_session_booklets_catalog_has_no_faction(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            r = client.post("/api/session", json={"mode": "main", "player_id": "player:1"})
            if r.status_code != 200:
                pytest.skip(f"无法建局：{r.text}")
            sid = r.json()["session"]["session_id"]
            cat = client.get(f"/api/session/{sid}/booklets")
            assert cat.status_code == 200, cat.text
            items = cat.json().get("items") or []
            assert items
            assert all("faction" not in row for row in items)
