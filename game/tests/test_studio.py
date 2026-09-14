

# ---------------------------------------------------------------- LLM 线（桩实测）

_VALID_PAYLOAD = json.dumps({
    "title": "桩线实测·雨夜档案馆",
    "acts": [{"id": "act1"}, {"id": "act2"}, {"id": "act3"}],
}, ensure_ascii=False)


class _StubLLM:
    """确定性桩 LLM：mode=valid 返回合法 JSON；mode=bad 返回畸形文本。"""

    last_provider = "main"

    def __init__(self, mode: str = "valid"):
        self.mode = mode
        self.calls = 0

    def chat(self, messages, provider="main", temperature=0.35, **kw):
        self.calls += 1
        return _VALID_PAYLOAD if self.mode == "valid" else "这不是JSON {{{ 完全畸形"


@pytest.fixture()
def llm_sandbox(tmp_path, monkeypatch):
    """把 studio 落盘重定向到临时目录，零副作用验证 LLM 线。"""
    from studio import paths, pipeline

    monkeypatch.setattr(paths, "SCENARIOS", tmp_path)
    monkeypatch.setattr(pipeline, "SCENARIOS", tmp_path)


class TestStudioLlmLine:
    def test_valid_stub_three_steps_green(self, llm_sandbox):
        from studio import pipeline

        stub = _StubLLM("valid")
        job = pipeline.generate(
            PRESET_SEEDS[0], tier="demo", use_llm=True, llm=stub)
        assert stub.calls == 3  # world / detail / acts 恰好三步
        assert job["provider"] == "main"
        assert job["gate"]["ok"] is True and job["status"] == "ready"
        assert job["world"]["title"] == "桩线实测·雨夜档案馆"

    def test_malformed_stub_falls_back_to_mock(self, llm_sandbox):
        from studio import pipeline

        stub = _StubLLM("bad")
        job = pipeline.generate(
            PRESET_SEEDS[0], tier="demo", use_llm=True, llm=stub)
        assert job["provider"] == "mock"  # 回退 mock 不抛路由
        assert job["gate"]["ok"] is True and job["status"] == "ready"

    def test_repair_truncated_json(self):
        from studio.llm_steps import _repair_truncated

        broken = '{"a": {"b": [1, 2, {"c": "未完字符串'
        assert json.loads(_repair_truncated(broken)) == {"a": {"b": [1, 2, {}]}}
        dangling = '{"x": "v", "y": '
        assert json.loads(_repair_truncated(dangling)) == {"x": "v"}
["id"].startswith("gen_")

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
        assert job["modules"]["hotfeed"] is False
        pack = public_snapshot(job["id"])
        assert pack.get("modules", {}).get("hotfeed") is False

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
        assert gate["ok"] is False
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
            encoding="utf-8",
        )

        gate = validate_dir(dest)
        assert gate["ok"] is False
        assert _errors_match_contract(gate["errors"]), gate["errors"]

    def test_kanshan_blacklisted(self):
        gate = validate_dir(SCENARIO_DIR)
        assert gate["ok"] is False
        assert any("BLACKLIST" in err for err in gate["errors"])


class TestStudioPublicSnapshot:
    def test_playable_without_secret_keys(self, ready_job):
        pack = public_snapshot(ready_job["id"])
        assert pack["playable"] is True

        found: set[str] = set()
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
        assert ("盐言" in blob_b) or ("横幅" in blob_b)
        assert "热搜日志" not in blob_b
        names_a = {c["name"] for c in a["detail"]["characters"]}
        names_b = {c["name"] for c in b["detail"]["characters"]}
        assert names_a != names_b

    def test_horror_space_and_player_truth_enter_clues(self):
        job = generate("灯灭之后只剩井号的呼吸声", brief={
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
            (t for c in ready_job["detail"]["clues"] if c["location"] == loc_name for t in c.get("tags") or []),
            "",
        )
        if keyword:
            # quick 建局已跳过破冰，停在搜证幕；再 advance 会进圆桌，search 被拒。
            if session.get("stage") == "break_ice":
                events, err = driver.apply_action(session, "advance", "player:1", {})
                assert err is None, err
            events, err = driver.apply_action(
                session, "search", "player:1", {"location": loc_id, "keyword": keyword}
            )
            assert err is None, err
            kinds = [(e.get("payload") or {}).get("event") for e in events]
            assert "bad_location" not in kinds, loc_id + "/" + loc_name
            assert "clue_gained" in kinds or "search_result" in kinds or any(
                "clue" in str(e).lower() for e in events
            )


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
        resp = client.post(
            "/api/studio/generate",
            json={"seed": PRESET_SEEDS[0], "tier": "demo", "use_llm": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True
        job = body.get("job") or {}
        assert job.get("gate", {}).get("ok") is True
        assert str(job.get("id", "")).startswith("gen_")

    def test_session_defaults_to_kanshan(self, client):
        if not _app_has_route("/api/session"):
            pytest.skip("POST /api/session 不可用")
        resp = client.post("/api/session", json={"mode": "quick", "player_id": "player:1"})
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
