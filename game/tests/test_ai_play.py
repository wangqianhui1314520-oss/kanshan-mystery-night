"""空席 AI 按本行动：HTTP /ai_act、vacant 过滤、wave、引擎 AP 与发言人。"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from server.booklet_svc import vacant_ai_roles
from server.engine_driver import EngineDriver, _ai_speaker_char
from tests.conftest import SCENARIO_DIR


def test_vacant_excludes_claimed_connected_and_investigator():
    session = {
        "npcs": [{"id": f"char_{i:02d}"} for i in range(1, 9)],
        "booklet_roles": {"player:1": "char_03", "player:host": "investigator"},
        "seats": [
            {"char_id": "char_01", "player_id": "player:2",
             "is_ai": False, "connected": True},
            {"char_id": "char_02", "player_id": "player:3",
             "is_ai": True, "connected": False},
            {"char_id": "char_04", "player_id": "player:4",
             "is_ai": False, "connected": False},
        ],
        "seats_public": [],
    }
    vacant = vacant_ai_roles(session)
    assert "investigator" not in vacant
    assert "char_03" not in vacant
    assert "char_01" not in vacant
    assert "char_02" in vacant
    assert "char_04" in vacant
    assert "char_05" in vacant


def test_vacant_defaults_char_01_to_08():
    vacant = vacant_ai_roles({"npcs": [], "booklet_roles": {}, "seats": []})
    assert vacant == [f"char_{i:02d}" for i in range(1, 9)]


def test_ai_speaker_char_parses_prefixes():
    assert _ai_speaker_char("ai:char_03") == "char_03"
    assert _ai_speaker_char("player:ai:char_08") == "char_08"
    assert _ai_speaker_char("player:1") is None


def test_apply_action_rejects_ai_without_flag(fresh_driver):
    eng, _ = fresh_driver()
    session = eng.create_session("main", "player:1")
    ev, err = eng.apply_action(session, "chat", "ai:char_03",
                               {"text": "hi", "target": "char_01"})
    assert ev == []
    assert err and "player:" in err


def test_ai_chat_uses_npc_actor_kind(fresh_driver):
    eng, _ = fresh_driver()
    session = eng.create_session("main", "player:1")
    ev, err = eng.apply_action(
        session, "chat", "ai:char_03",
        {"text": "我是流量酱。#先认识一下#", "target": "char_01"},
        allow_ai=True)
    assert err is None
    chats = [e for e in ev if e.get("type") == "chat"]
    assert chats
    payload = chats[0]["payload"]
    assert payload.get("actor_kind") == "npc"
    assert payload.get("char_id") == "char_03"
    assert payload.get("player_id") == "ai:char_03"
    assert "faction" not in payload
    assert "faction" not in chats[0]


def test_vacant_ai_does_not_steal_shared_ap(fresh_driver):
    eng, _ = fresh_driver()
    session = eng.create_session("main", "player:1")
    ev, err = eng.apply_action(session, "advance", "player:1", {})
    assert err is None
    assert session["stage"] == "investigate"
    before = session["actions_left"]
    ev, err = eng.apply_action(
        session, "search", "player:ai:char_03",
        {"location": "档案室", "keyword": "芯片"}, allow_ai=True)
    assert err is None
    assert session["actions_left"] == before


def test_party_ai_actor_gets_own_ap(fresh_driver):
    eng, _ = fresh_driver()
    session = eng.create_session("party", "player:1")
    assert eng.join_seat("player:1", "char_01")["ok"]
    eng.pb._ap.pop("ai:char_03", None)
    assert "ai:char_03" not in eng.pb.ap_state()
    ev, err = eng.apply_action(
        session, "chat", "ai:char_03",
        {"text": "先认识一下", "target": "char_01"}, allow_ai=True)
    assert err is None
    assert "ai:char_03" in eng.pb.ap_state()
    ev, err = eng.apply_action(session, "advance", "player:1", {})
    assert err is None
    shared_before = session["actions_left"]
    ai_before = eng.pb.ap_state()["ai:char_03"]
    ev, err = eng.apply_action(
        session, "search", "ai:char_03",
        {"location": "档案室", "keyword": "芯片"}, allow_ai=True)
    assert err is None
    assert session["actions_left"] == shared_before
    assert eng.pb.ap_state()["ai:char_03"] == ai_before - 1


def _client(tmp_path, monkeypatch):
    import server.main as main_mod
    monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
    return TestClient(main_mod.app)


def test_ai_act_route_dry_run_and_apply(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        dry = client.post(f"/api/session/{sid}/ai_act",
                          json={"char_id": "char_03", "dry_run": True})
        assert dry.status_code == 200, dry.text
        body = dry.json()
        assert body["ok"] is True
        assert body["role_id"] == "char_03"
        assert body["applied"] is False
        assert body["decision"]["type"]
        assert "faction" not in json.dumps(body.get("decision") or {})

        applied = client.post(f"/api/session/{sid}/ai_act",
                              json={"role": "char_03", "dry_run": False})
        assert applied.status_code == 200, applied.text
        out = applied.json()
        assert out["applied"] is True
        assert isinstance(out.get("events"), list)
        for e in out.get("events") or []:
            assert "faction" not in (e.get("payload") or {})


def test_action_rejects_ai_actor(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/action",
                        json={"type": "chat", "actor": "ai:char_03",
                              "payload": {"text": "绕过", "target": "char_01"}})
        assert r.status_code == 400


def test_human_action_triggers_wave_max_three(tmp_path, monkeypatch):
    import server.main as main_mod
    waves = []
    orig = main_mod.GameServer.run_ai_wave

    async def spy(self, session_id):
        waves.append(session_id)
        return await orig(self, session_id)

    monkeypatch.setattr(main_mod.GameServer, "run_ai_wave", spy)
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/action",
                        json={"type": "chat", "actor": "player:1",
                              "payload": {"text": "大家好", "target": "char_01"}})
        assert r.status_code == 200, r.text
        assert waves == [sid]
        events = r.json()["events"]
        roles = {e.get("payload", {}).get("booklet_role")
                 for e in events if (e.get("payload") or {}).get("booklet_act")}
        roles.discard(None)
        assert "investigator" not in roles
        assert 1 <= len(roles) <= 8
        for e in events:
            assert "faction" not in (e.get("payload") or {})


def test_ai_act_does_not_reenter_wave(tmp_path, monkeypatch):
    import server.main as main_mod
    waves = []
    orig = main_mod.GameServer.run_ai_wave

    async def spy(self, session_id):
        waves.append(1)
        return await orig(self, session_id)

    monkeypatch.setattr(main_mod.GameServer, "run_ai_wave", spy)
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(f"/api/session/{sid}/ai_act",
                        json={"char_id": "char_03", "dry_run": False})
        assert r.status_code == 200, r.text
        assert waves == []


def test_ai_wave_route_after_claim(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        claimed = client.post(f"/api/session/{sid}/claim",
                              json={"player_id": "player:1", "char_id": "char_03"})
        assert claimed.status_code == 200, claimed.text
        r = client.post(f"/api/session/{sid}/ai_wave")
        assert r.status_code == 200, r.text
        events = r.json()["events"]
        assert isinstance(events, list)
        roles = {e.get("payload", {}).get("booklet_role")
                 for e in events if (e.get("payload") or {}).get("booklet_act")}
        roles.discard(None)
        assert "char_03" not in roles
        assert "investigator" not in roles
        assert 1 <= len(roles) <= 8


def test_ai_wave_ingests_llm_headers(tmp_path, monkeypatch):
    import server.main as main_mod
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        r = client.post(
            f"/api/session/{sid}/ai_wave",
            headers={"X-LLM-KEY": "sk-test",
                     "X-LLM-BASE": "http://127.0.0.1:9/v1",
                     "X-LLM-MODEL": "dummy"})
        assert r.status_code == 200, r.text
        cfg = (getattr(main_mod.app.state, "api_cfg", {}) or {}).get(sid) or {}
        assert cfg.get("llm_key") == "sk-test"
        assert cfg.get("llm_model") == "dummy"
        events = r.json()["events"]
        roles = {e.get("payload", {}).get("booklet_role")
                 for e in events if (e.get("payload") or {}).get("booklet_act")}
        roles.discard(None)
        assert "investigator" not in roles
        assert 1 <= len(roles) <= 8


def test_llm_for_session_needs_full_triple(tmp_path, monkeypatch):
    import server.main as main_mod
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    # game/.env 可能注入知乎凭证（load_dotenv 进程级）；key-only 语义测试
    # 必须隔离 ZHIHU_*，否则会误走知乎网关分支返回非 None。
    monkeypatch.delenv("ZHIHU_APP_KEY", raising=False)
    monkeypatch.delenv("ZHIHU_ACCESS_SECRET", raising=False)
    with _client(tmp_path, monkeypatch) as client:
        main_mod.app.state.api_cfg = {"s1": {"llm_key": "sk-only"}}
        assert main_mod.game_server._llm_for_session("s1") is None
        main_mod.app.state.api_cfg = {
            "s1": {"llm_key": "sk-x", "llm_base": "http://127.0.0.1:9/v1",
                   "llm_model": "dummy"}}
        llm = main_mod.game_server._llm_for_session("s1")
        assert llm is not None
        assert llm.providers["main"].available() is True


def test_openai_provider_rereads_env(monkeypatch):
    from agents.llm_client import OpenAICompatProvider
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    p = OpenAICompatProvider()
    assert p.available() is False
    monkeypatch.setenv("LLM_API_KEY", "sk-later")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_MODEL", "dummy")
    assert p.available() is True


def test_rotate_or_vacant_after_claim(tmp_path, monkeypatch):
    import server.main as main_mod
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "main", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        claimed = client.post(f"/api/session/{sid}/claim",
                              json={"player_id": "player:1", "char_id": "char_03"})
        assert claimed.status_code == 200, claimed.text
        session = main_mod.app.state.store.load_session(sid)
        vacant = vacant_ai_roles(session)
        assert "char_03" not in vacant


def test_rotate_roles_does_not_repeat_when_n_exceeds_bag():
    from agents.seat_runner import rotate_roles
    picked, nxt = rotate_roles(["char_01", "char_02"], 0, 3)
    assert picked == ["char_01", "char_02"]
    assert nxt == 0


def test_ai_draw_card_honest_and_no_shared_ap(fresh_driver):
    eng, _ = fresh_driver()
    session = eng.create_session("main", "player:1")
    ev, err = eng.apply_action(session, "advance", "player:1", {})
    assert err is None
    before = session["actions_left"]
    ev, err = eng.apply_action(
        session, "skill", "player:ai:char_05",
        {"skill": "draw_card"}, allow_ai=True)
    assert err is None
    assert session["actions_left"] == before
    kinds = {e.get("type") for e in ev}
    events = [e.get("payload", {}).get("event") for e in ev]
    assert "faction_skill" in kinds or "card_drawn" in events
    blob = json.dumps(ev, ensure_ascii=False)
    assert "faction" not in blob or '"faction_skill"' in blob
    for e in ev:
        assert "faction" not in (e.get("payload") or {}) or e.get("type") == "faction_skill"
