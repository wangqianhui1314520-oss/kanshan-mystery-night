"""S4：剧本杀一键工作台验收（STUDIO_WORKBENCH.md §7 §9）。

覆盖：generate 闸门绿、故意破坏拷贝、public 无剧透键、EngineDriver 快本、
kanshan 黑名单、空 seed 异常；可选 REST 路由（不存在则 skip）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from studio import generate, public_snapshot, validate_dir
from studio import scenario_dir as studio_scenario_dir
from studio.tiers import PRESET_SEEDS
from tests.conftest import SCENARIO_DIR

CONTRACT_ERROR_PREFIXES = ("QUOTA:", "REF:", "FAKE:", "FACTION:", "TAG:", "KC:")
FORBIDDEN_PUBLIC_KEYS = frozenset({"faction", "guilt", "inner_truth"})


def _copy_tree_safe(src: Path, dest: Path) -> None:
    """Windows 下 shutil.copytree 偶发 WinError 2，改字节流复制。"""
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.iterdir():
        target = dest / path.name
        if path.is_dir():
            _copy_tree_safe(path, target)
        else:
            target.write_bytes(path.read_bytes())


@pytest.fixture(scope="module")
def ready_job():
    job = generate(PRESET_SEEDS[0])
    assert job["gate"]["ok"], job["gate"]["errors"]
    return job


def _collect_forbidden_keys(obj, found: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_PUBLIC_KEYS:
                found.add(k)
            _collect_forbidden_keys(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _collect_forbidden_keys(item, found)


def _errors_match_contract(errors: list[str]) -> bool:
    return any(
        any(err.startswith(prefix) for prefix in CONTRACT_ERROR_PREFIXES)
        for err in errors
    )


def _json_has_forbidden_key(text: str) -> set[str]:
    leaked = set()
    for key in FORBIDDEN_PUBLIC_KEYS:
        if f'"{key}"' in text:
            leaked.add(key)
    return leaked


class TestStudioGenerate:
    def test_preset_seed_ready(self, ready_job):
        assert ready_job["gate"]["ok"] is True
        assert ready_job["status"] == "ready"
        assert ready_job["id"].startswith("gen_")

    def test_empty_seed_raises(self):
        with pytest.raises(ValueError, match="seed"):
            generate("")

    def test_brief_overlay_keeps_gate(self):
        brief = {
            "hook": PRESET_SEEDS[0],
            "lock": {"theme": "热度不是真相·改", "space": "热榜机房"},
            "cast": [{"id": "char_01", "name": "井号君", "archetype": "操盘手"}],
            "truth": {"crime": "指使删除热搜日志"},
            "acts": [{"id": "act1", "name": "开场锁门", "brief": "先说话再搜证"}],
            "modules": {"hotfeed": False, "memory": True, "counsel": True, "kcards": True},
        }
        job = generate(PRESET_SEEDS[0], brief=brief)
        assert job["gate"]["ok"] is True, job["gate"]["errors"]
        assert job["world"]["cast_slots"][0]["name"] == "井号君"
        assert job["world"]["theme"] == "热度不是真相·改"
        act1 = (job["acts"]["acts"] if isinstance(job["acts"], dict) else job["acts"])[0]
        assert act1["name"] == "开场锁门"
        assert act1["stage"] == "break_ice"
        pack = public_snapshot(job["id"])
        assert (pack.get("modules") or {}).get("hotfeed") is False

    def test_horror_pack_type_public_fields(self):
        job = generate(PRESET_SEEDS[0], brief={
            "hook": PRESET_SEEDS[0],
            "pack_type": "horror",
            "vibe": {"mood": "horror", "horror_beats": "灯灭七分钟"},
            "minis": ["heart"],
            "camp": {"pollution": "黑雾", "public": False},
        })
        assert job["gate"]["ok"] is True, job["gate"]["errors"]
        pack = public_snapshot(job["id"])
        assert pack.get("pack_type") == "horror"
        assert pack.get("vibe") == "horror"
        assert pack.get("minis") == ["heart"]
        assert "faction" not in json.dumps(pack, ensure_ascii=False)


class TestStudioGate:
    def test_broken_copy_triggers_contract_error(self, ready_job, tmp_path):
        src = studio_scenario_dir(ready_job["id"])
        dest = tmp_path / ready_job["id"]
        _copy_tree_safe(src, dest)

        clues = sorted((dest / "clues").glob("clue_*.json"))
        assert clues, "生成目录应含线索文件"
        clues[0].unlink()

        gate = validate_dir(dest)
        assert gate["ok"] is False, gate["errors"]
        assert _errors_match_contract(gate["errors"]), gate["errors"]

    def test_broken_clue_pool_triggers_ref(self, ready_job, tmp_path):
        src = studio_scenario_dir(ready_job["id"])
        dest = tmp_path / "broken_pool"
        _copy_tree_safe(src, dest)

        scenario_path = dest / "scenario.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        first_loc = next(iter(scenario["scene_map"].values()))
        pool = list(first_loc.get("clue_pool") or [])
        pool.append("clue_nonexistent_999")
        first_loc["clue_pool"] = pool
        scenario_path.write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

        gate = validate_dir(dest)
        assert gate["ok"] is False, gate["errors"]
        assert _errors_match_contract(gate["errors"]), gate["errors"]

    def test_kanshan_blacklisted(self):
        gate = validate_dir(SCENARIO_DIR)
        assert gate["ok"] is False, gate["errors"]
        assert any("BLACKLIST" in err for err in gate["errors"]), gate["errors"]


class TestStudioPublicSnapshot:
    def test_playable_without_secret_keys(self, ready_job):
        pack = public_snapshot(ready_job["id"])
        assert pack["playable"] is True

        found = set()
        _collect_forbidden_keys(pack, found)
        assert not found, f"public 包泄露键：{found}"

        text = json.dumps(pack, ensure_ascii=False)
        json_leaked = _json_has_forbidden_key(text)
        assert not json_leaked, f"JSON 文本含禁键：{json_leaked}"


class TestStudioNewCase:
    def test_two_hooks_make_different_cases(self):
        a = generate(PRESET_SEEDS[0])
        b = generate(PRESET_SEEDS[1])
        assert a["gate"]["ok"] and b["gate"]["ok"]

        fact_a = a["detail"]["clues"][0]["fact"]
        fact_b = b["detail"]["clues"][0]["fact"]
        assert fact_a != fact_b

        blob_a = json.dumps(a["detail"], ensure_ascii=False)
        blob_b = json.dumps(b["detail"], ensure_ascii=False)
        assert "热搜" in blob_a
        assert "盐言" in blob_b or "横幅" in blob_b
        assert "热搜日志" not in blob_b

        names_a = {c["name"] for c in a["detail"]["characters"]}
        names_b = {c["name"] for c in b["detail"]["characters"]}
        assert names_a != names_b

    def test_horror_space_and_player_truth_enter_clues(self):
        job = generate(PRESET_SEEDS[0], brief={
            "hook": "灯灭之后只剩井号的呼吸声",
            "pack_type": "horror",
            "lock": {"space": "黑灯机房", "lock_rule": "灯亮之前不准走"},
            "cast": [{"id": "char_01", "name": "井号君", "archetype": "操盘手"}],
            "truth": {"crime": "调换了灭灯原片", "motive": "掩盖井号指令"},
            "vibe": {"mood": "horror"},
        })
        assert job["gate"]["ok"], job["gate"]["errors"]

        loc_names = [l["name"] for l in job["world"]["locations"]]
        assert any("黑灯" in n for n in loc_names)
        clue_locs = {c["location"] for c in job["detail"]["clues"]}
        assert clue_locs <= set(loc_names)

        blob = json.dumps({"w": job["world"], "d": job["detail"]}, ensure_ascii=False)
        assert "井号君" in blob
        assert "灭灯原片" in blob
        assert job["detail"]["culprit"]["crime"] == "调换了灭灯原片"

        pack = public_snapshot(job["id"])
        assert pack["playable"] is True
        assert any("黑灯" in (loc.get("name") or "") for loc in pack["locations"])
        assert any(c.get("name") == "井号君" for c in pack["characters"])

    def test_same_brief_is_deterministic(self):
        brief = {
            "hook": PRESET_SEEDS[1],
            "pack_type": "emotion",
            "lock": {"space": "盐言房间", "theme": "不出真相不出此门"},
        }
        a = generate(PRESET_SEEDS[1], brief=brief)
        b = generate(PRESET_SEEDS[1], brief=brief)
        assert a["detail"]["clues"][2]["fact"] == b["detail"]["clues"][2]["fact"]
        assert a["world"]["logline"] == b["world"]["logline"]


class TestStudioEngine:
    def test_quick_session_roster_four(self, ready_job):
        from server.engine_driver import EngineDriver

        driver = EngineDriver(studio_scenario_dir(ready_job["id"]))
        session = driver.create_session("quick", "player:1")
        assert session["engine"] == "engine_v3"
        assert len(session["npcs"]) == 4

        loc_id = next(iter(driver._loc_names))
        loc_name = driver._loc_names[loc_id]
        keyword = next(
            (t for c in ready_job["detail"]["clues"]
             if c["location"] == loc_name
             for t in (c.get("tags") or [])),
            "")
        if keyword:
            # quick 建局已跳过破冰，停在搜证幕（create_session 的 mode_setup
            # 事件明示"快速局：已跳过破冰，直接搜证/对质"）；再 advance 会进
            # 圆桌，search 被拒。
            if session.get("stage") == "break_ice":
                events, err = driver.apply_action(session, "advance", "player:1", {})
                assert err is None, err
            events, err = driver.apply_action(
                session, "search", "player:1",
                {"location": loc_id, "keyword": keyword})
            assert err is None

            kinds = [e.get("payload", {}).get("event") for e in events]
            assert "bad_location" not in kinds, str(loc_id) + "/" + str(loc_name)
            assert ("clue_gained" in kinds or "search_result" in kinds
                    or any("clue" in str(e).lower() for e in events))


def _app_has_route(path: str, method: str = "POST") -> bool:
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


class TestStudioOptionalApi:
    @pytest.fixture()
    def client(self):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from server.main import app
        with TestClient(app) as c:
            yield c

    def test_studio_generate_route(self, client):
        if not _app_has_route("/api/studio/generate"):
            pytest.skip("POST /api/studio/generate 尚未实现（S2）")
        resp = client.post("/api/studio/generate", json={
            "seed": PRESET_SEEDS[0], "tier": "demo", "use_llm": False,
        })
        # 202 异步受理契约：轮询 /api/studio/jobs/{job_id} 到终态
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body.get("ok") is True
        assert body.get("status") == "running"
        job_id = body["job_id"]
        deadline = time.time() + 90
        job = {}
        while time.time() < deadline:
            r = client.get(f"/api/studio/jobs/{job_id}")
            assert r.status_code == 200, r.text
            job = r.json()["job"]
            if job.get("status") in ("ready", "failed"):
                break
            time.sleep(0.3)
        assert job.get("status") == "ready", job
        assert (job.get("gate") or {}).get("ok") is True
        assert str(job.get("id", "")).startswith("gen_")

    def test_session_defaults_to_kanshan(self, client):
        if not _app_has_route("/api/session"):
            pytest.skip("POST /api/session 不可用")
        resp = client.post("/api/session", json={
            "mode": "quick", "player_id": "player:1",
        })
        if resp.status_code == 503:
            pytest.skip("真实引擎未就绪（TestClient 环境常见）")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True
        session = body.get("session") or {}
        assert session.get("scenario_id", "kanshan") == "kanshan"
        assert len(session.get("npcs") or []) == 8

    def test_session_studio_pack(self, client, ready_job):
        if not _app_has_route("/api/session"):
            pytest.skip("POST /api/session 不可用")
        resp = client.post("/api/session", json={
            "mode": "quick",
            "player_id": "player:1",
            "scenario_id": ready_job["id"],
        })
        if resp.status_code == 503:
            pytest.skip("真实引擎未就绪（TestClient 环境常见）")
        assert resp.status_code == 200
        session = (resp.json() or {}).get("session") or {}
        assert session.get("scenario_id") == ready_job["id"]
        assert len(session.get("npcs") or []) == 4
