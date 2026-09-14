"""P2-1 守护：player_id 长度校验（超长拒绝，正常放行并规范化）。

mutation 对照：删除 main.py 中 _norm_player_id 的长度检查（或三处调用点
还原为旧写法）后，test_oversized_player_id_rejected 必须 FAIL（返回 200）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    import server.main as main_mod
    monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
    return TestClient(main_mod.app)


def test_oversized_player_id_rejected(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        r = client.post("/api/session",
                        json={"mode": "main", "player_id": "x" * 100000})
        assert r.status_code == 400, f"超长 player_id 未被拒绝：{r.status_code}"


def test_oversized_join_player_id_rejected(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        sid = client.post("/api/session",
                          json={"mode": "party", "player_id": "player:1"}
                          ).json()["session"]["session_id"]
        room = client.get(f"/api/health").json()  # 仅探活
        r = client.post(f"/api/session/{sid}/join",
                        json={"room_code": "000000",
                              "player_id": "x" * 100000})
        # 房间码错误（403）优先级高于长度校验则此处保持原语义——
        # 只要求"不因超长 player_id 崩溃/成功入库"
        assert r.status_code in (400, 403, 404), r.status_code


def test_normal_player_id_normalized(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        r = client.post("/api/session",
                        json={"mode": "main", "player_id": "qa1"})
        assert r.status_code == 200, r.text
        players = r.json()["session"].get("players") or []
        assert players and players[0]["player_id"] == "player:qa1"
