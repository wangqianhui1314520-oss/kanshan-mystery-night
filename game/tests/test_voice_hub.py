"""VoiceHub 信令通道（API / WS 单元）：不进引擎、不写回声链。"""
from __future__ import annotations

import json

from server.voice_hub import ice_servers_from_env, resolve_voice_identity


def _party_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server.main as main_mod
    monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
    return TestClient(main_mod.app)


def _create_party(client, host="player:1"):
    r = client.post("/api/session", json={"mode": "party", "player_id": host})
    assert r.status_code == 200, r.text
    return r.json()["session"]


class TestVoiceIdentity:
    def test_seated_vs_spectator(self):
        session = {
            "mode": "party",
            "players": [{"player_id": "player:1"}],
            "spectators": ["spectator:judge01"],
        }
        seated = resolve_voice_identity(session, "player:1")
        assert seated and seated["listen_only"] is False
        spec = resolve_voice_identity(session, "judge01")
        assert spec and spec["listen_only"] is True
        assert spec["player_id"] == "spectator:judge01"
        assert resolve_voice_identity(session, "player:9") is None

    def test_ice_servers_turn_env(self, monkeypatch):
        monkeypatch.setenv("TURN_URL", "turn:example.com:3478")
        monkeypatch.setenv("TURN_USER", "u")
        monkeypatch.setenv("TURN_PASS", "p")
        body = ice_servers_from_env()
        assert body["turn_configured"] is True
        urls = [u for s in body["ice_servers"] for u in s["urls"]]
        assert "stun:stun.l.google.com:19302" in urls
        turn = next(s for s in body["ice_servers"] if "turn:example.com:3478" in s["urls"])
        assert turn["username"] == "u" and turn["credential"] == "p"


class TestVoiceRoutes:
    def test_health_voice_peers_and_ice_servers(self, tmp_path, monkeypatch):
        with _party_client(tmp_path, monkeypatch) as client:
            h = client.get("/api/health").json()
            assert h["voice_peers"] == 0
            solo = client.post("/api/session",
                               json={"mode": "main", "player_id": "player:1"}
                               ).json()["session"]
            bad = client.get(f"/api/session/{solo['session_id']}/voice/ice-servers")
            assert bad.status_code == 400
            missing = client.get("/api/session/no_such_session/voice/ice-servers")
            assert missing.status_code == 404
            s = _create_party(client)
            ice = client.get(f"/api/session/{s['session_id']}/voice/ice-servers")
            assert ice.status_code == 200
            body = ice.json()
            assert body["ok"] and body["ice_servers"]
            assert any("stun:" in u for s in body["ice_servers"] for u in s["urls"])

    def test_reject_solo_and_unseated(self, tmp_path, monkeypatch):
        with _party_client(tmp_path, monkeypatch) as client:
            solo = client.post("/api/session",
                               json={"mode": "main", "player_id": "player:1"}
                               ).json()["session"]
            with client.websocket_connect(
                    f"/ws/{solo['session_id']}/voice?player_id=player:1") as ws:
                err = json.loads(ws.receive_text())
                assert err["type"] == "error"
                assert err["payload"]["code"] == 4403
            s = _create_party(client)
            sid = s["session_id"]
            with client.websocket_connect(f"/ws/{sid}/voice?player_id=player:9") as ws:
                err = json.loads(ws.receive_text())
                assert err["type"] == "error"
                assert err["payload"]["code"] == 4403

    def test_mesh_signal_forward_and_no_echo(self, tmp_path, monkeypatch):
        with _party_client(tmp_path, monkeypatch) as client:
            s = _create_party(client)
            sid, rc = s["session_id"], s["room_code"]
            events_before = len(s.get("events") or [])
            j2 = client.post(f"/api/session/{sid}/join",
                             json={"room_code": rc, "player_id": "player:2"})
            assert j2.status_code == 200, j2.text
            with client.websocket_connect(
                    f"/ws/{sid}/voice?player_id=player:1") as ws1, \
                    client.websocket_connect(
                        f"/ws/{sid}/voice?player_id=player:2") as ws2:
                snap1 = json.loads(ws1.receive_text())
                snap2 = json.loads(ws2.receive_text())
                assert snap1["type"] == "peers"
                assert snap1["payload"]["you"] == "player:1"
                assert snap1["payload"]["listen_only"] is False
                assert snap2["type"] == "peers"
                joined = json.loads(ws1.receive_text())
                assert joined["type"] == "join" and joined["from"] == "player:2"
                assert client.get("/api/health").json()["voice_peers"] == 2
                ws1.send_text(json.dumps({
                    "type": "offer", "from": "player:evil", "to": "player:2",
                    "payload": {"sdp": "v=0-fake"},
                }))
                offer = json.loads(ws2.receive_text())
                assert offer["type"] == "offer"
                assert offer["from"] == "player:1"
                assert offer["to"] == "player:2"
                assert offer["payload"]["sdp"] == "v=0-fake"
                ws2.send_text(json.dumps({
                    "type": "answer", "to": "player:1",
                    "payload": {"sdp": "v=0-ans"},
                }))
                ans = json.loads(ws1.receive_text())
                assert ans["type"] == "answer" and ans["from"] == "player:2"
                ws1.send_text(json.dumps({
                    "type": "ice", "to": "player:2",
                    "payload": {"candidate": "cand-1"},
                }))
                ice = json.loads(ws2.receive_text())
                assert ice["type"] == "ice" and ice["payload"]["candidate"] == "cand-1"
                ws1.send_text(json.dumps({"type": "mute", "payload": {"muted": True}}))
                mute = json.loads(ws2.receive_text())
                assert mute["type"] == "mute" and mute["payload"]["muted"] is True
                ws1.send_text(json.dumps({"type": "chat", "payload": {"text": "不该进引擎"}}))
                err = json.loads(ws1.receive_text())
                assert err["type"] == "error"
            view = client.get(f"/api/session/{sid}").json()["session"]
            assert len(view.get("events") or []) == events_before + 1  # join p2 一条
            types = [e.get("type") for e in view.get("events") or []]
            assert "offer" not in types and "mute" not in types
            assert client.get("/api/health").json()["voice_peers"] == 0

    def test_spectator_listen_only(self, tmp_path, monkeypatch):
        with _party_client(tmp_path, monkeypatch) as client:
            s = _create_party(client)
            sid, rc = s["session_id"], s["room_code"]
            sp = client.post(f"/api/session/{sid}/join",
                             json={"room_code": rc, "player_id": "judge01",
                                   "role": "spectator"})
            assert sp.status_code == 200
            spec_id = sp.json()["player_id"]
            with client.websocket_connect(
                    f"/ws/{sid}/voice?player_id={spec_id}") as ws:
                snap = json.loads(ws.receive_text())
                assert snap["type"] == "peers"
                assert snap["payload"]["listen_only"] is True
                ws.send_text(json.dumps({
                    "type": "offer", "to": "player:1",
                    "payload": {"sdp": "nope"},
                }))
                err = json.loads(ws.receive_text())
                assert err["type"] == "error"
                assert "只听" in err["payload"]["notice"]
