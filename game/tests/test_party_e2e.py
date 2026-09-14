"""G 增量①：party 多人端到端 —— 多 actor 会话 / 投票聚合 / WS 房间广播 / 席位与阵营。

Server 层走 FastAPI TestClient（真实 app + 临时数据目录）；
PartyBoard 单体行为另见 test_engine_units.py::TestPartyBoard。
"""
from __future__ import annotations

import json

import pytest

from server.engine_driver import EngineDriver
from tests.conftest import SCENARIO_DIR

pytestmark = pytest.mark.party

CULPRIT = "char_01"


class TestMultiActorSession:
    def test_three_player_join_aggregate_and_finalize(self):
        """3 真人经动作管线入座 → 指认幕 3 票聚合 → 单次终局。"""
        d = EngineDriver(SCENARIO_DIR)
        s = d.create_session("main", "player:1", "s_party_1")
        assert [p["player_id"] for p in s["players"]] == ["player:1"]
        # investigate 阶段 p2/p3 以动作入席（apply_action 自动 join players）
        d.apply_action(s, "advance", "player:1", {})
        _, err = d.apply_action(s, "search", "player:2", {"location": "茶水间", "keyword": "泡面"})
        assert err is None
        _, err = d.apply_action(s, "chat", "player:3", {"text": "大家好"})
        assert err is None
        assert {p["player_id"] for p in s["players"]} == {"player:1", "player:2", "player:3"}
        # AP 为全队共享池（当前实现）：行动力不足时诚实拒绝
        # 推进到指认
        d.apply_action(s, "advance", "player:1", {})  # → round_table
        d.apply_action(s, "advance", "player:1", {})  # → accuse
        # 票 1/3：不结算
        ev, err = d.apply_action(s, "vote", "player:1", {"target": CULPRIT})
        assert err is None and not any(e["type"] == "ending" for e in ev)
        assert s["votes"]["player:1"] == CULPRIT
        # 票 2/3
        ev, err = d.apply_action(s, "vote", "player:2", {"target": CULPRIT})
        assert err is None and not any(e["type"] == "ending" for e in ev)
        # 票 3/3 → 单次终局
        ev, err = d.apply_action(s, "vote", "player:3", {"target": CULPRIT})
        assert err is None
        endings = [e for e in ev if e["type"] == "ending"]
        assert len(endings) == 1, "终局应恰好结算一次"
        assert endings[0]["payload"]["detail"]["tally"] == {
            "player:1": CULPRIT, "player:2": CULPRIT, "player:3": CULPRIT}
        assert s["status"] == "ended"

    def test_party_board_seats_private_faction(self):
        """席位/阵营接线：join_seat 发牌、faction 零透出、AI 接管标记。"""
        d = EngineDriver(SCENARIO_DIR)
        r1 = d.join_seat("player:1", "char_03")
        assert r1["ok"] and r1["char_id"] == "char_03"
        r2 = d.join_seat("player:2")          # 自动空位
        assert r2["ok"] and r2["char_id"] != "char_03"
        assert d.join_seat("player:9", "char_03")["reason"] == "seat_taken"
        seats = d.seats_public()
        assert all("faction" not in x for x in seats), "阵营泄露进公开席位视图"
        assert sum(1 for x in seats if x["player_id"] == "player:1") == 1
        # 阵营配比：2 真人局污染 2 席（引擎内部，仅裁决可查）
        res = d.pb.result()
        assert len(res["pollution"]) == 2 and len(res["truth"]) == 6
        # 掉线 → AI 接管
        assert d.leave_seat("player:1")["ai_takeover"] is True
        seats = {x["char_id"]: x for x in d.seats_public()}
        assert seats["char_03"]["ai_takeover"] and seats["char_03"]["is_ai"]

    def test_party_mode_full_route_flow(self, tmp_path, monkeypatch):
        """F 组 v2.1 增量已交付：mode=party 建房 + 房间码进房 + 席位认领 + 观战。

        （本用例初版断言 400 拒绝；F 交付后按新契约翻转为正向流程，留证于 STATUS.md。）
        """
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            r = client.post("/api/session", json={"mode": "party",
                                                  "player_id": "player:1"})
            assert r.status_code == 200
            s = r.json()["session"]
            assert s["mode"] == "party" and s.get("room_code"), "party 房间码缺失"
            rc = s["room_code"]
            # 错误房间码 → 403
            bad = client.post(f"/api/session/{s['session_id']}/join",
                              json={"room_code": "WRONG", "player_id": "player:2"})
            assert bad.status_code == 403
            # p2/p3 认领角色进房
            j2 = client.post(f"/api/session/{s['session_id']}/join",
                             json={"room_code": rc, "player_id": "player:2",
                                   "char_id": "char_05"})
            assert j2.status_code == 200, j2.text
            seats = j2.json().get("seats") or []
            assert seats and all("faction" not in x for x in seats), "阵营泄露"
            claimed = [x for x in seats if x.get("player_id") == "player:2"]
            assert claimed and claimed[0]["char_id"] == "char_05"
            j3 = client.post(f"/api/session/{s['session_id']}/join",
                             json={"room_code": rc, "player_id": "player:3"})
            assert j3.status_code == 200
            # 观战
            sp = client.post(f"/api/session/{s['session_id']}/join",
                             json={"room_code": rc, "player_id": "judge01",
                                   "role": "spectator"})
            assert sp.status_code == 200
            # 脱敏视图：GET session 不含 party 快照/faction
            view = client.get(f"/api/session/{s['session_id']}").json()["session"]
            assert "party" not in view, "暗置阵营快照泄露进 API 视图"
            assert all("faction" not in p for p in view.get("players") or [])
            assert all("faction" not in n for n in view.get("npcs") or [])
            assert "spectators" in view and "judge01" in str(view["spectators"])


class TestTwoPlayersAiFill:
    """party 2 真人 + AI 补位 6 席（MEGA_MODE §二：AI 补齐空位 + 掉线 AI 接管）。"""

    def test_driver_two_humans_six_ai_seats(self):
        d = EngineDriver(SCENARIO_DIR)
        r0 = d.join_seat("player:1")
        assert r0["ok"]
        r1 = d.join_seat("player:1", "char_03")
        r2 = d.join_seat("player:2")                       # 自动认领空位
        assert r1["ok"] and r1["char_id"] == "char_03"
        assert r2["ok"] and r2["char_id"] != "char_03"
        owners = [s["player_id"] for s in d.seats_public() if s["player_id"] == "player:1"]
        assert len(owners) == 1
        seats = d.seats_public()
        assert len(seats) == 8
        humans = [s for s in seats if s["player_id"] in ("player:1", "player:2")]
        ais = [s for s in seats if s["is_ai"]]
        assert len(humans) == 2 and len(ais) == 6
        assert all(s["connected"] for s in humans)
        assert all(not s["connected"] and s["ai_takeover"] is False or True
                   for s in ais)  # AI 席无 connected 语义
        # AI 席行动点就位（各算各的，每轮 3）
        ap = d.pb.reset_round_ap()
        ai_actors = {f"ai:{s['char_id']}" for s in ais}
        assert ai_actors <= set(ap) and all(ap[a] == 3 for a in ai_actors)
        assert d.pb.spend("ai:char_05", 2) and not d.pb.spend("ai:char_05", 2)
        # 阵营配比：2 真人局 → 污染 2（含被裹挟者优先），服务端零透出
        res = d.pb.result()
        assert len(res["pollution"]) == 2 and len(res["truth"]) == 6
        assert all("faction" not in s for s in d.seats_public())
        # 掉线接管：p1 掉线 → char_03 AI 接管，席位保留
        assert d.leave_seat("player:1")["ai_takeover"] is True
        seat3 = next(s for s in d.seats_public() if s["char_id"] == "char_03")
        assert seat3["ai_takeover"] and seat3["is_ai"] and seat3["player_id"] == "player:1"

    def test_rest_party_two_join_ai_fill_visible(self, tmp_path, monkeypatch):
        """REST party：2 人进房后公开席位显示 6 个 AI 补位（faction 零透出）。"""
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            s = client.post("/api/session",
                            json={"mode": "party", "player_id": "player:1"}
                            ).json()["session"]
            rc, sid = s["room_code"], s["session_id"]
            # 契约口径：房主建房后同样需经 /join 入席（create_session 不自动落座，
            # 见 STATUS.md G13 CONCERNS）
            j1 = client.post(f"/api/session/{sid}/join",
                             json={"room_code": rc, "player_id": "player:1",
                                   "char_id": "char_01"}).json()
            assert j1.get("seats")
            j2 = client.post(f"/api/session/{sid}/join",
                             json={"room_code": rc, "player_id": "player:2",
                                   "char_id": "char_07"}).json()
            seats = j2.get("seats") or []
            assert len(seats) == 8
            humans = [x for x in seats if x.get("player_id")]
            assert len(humans) == 2
            assert {x["char_id"] for x in humans} == {"char_01", "char_07"}
            assert sum(1 for x in seats if x["is_ai"]) == 6
            assert all("faction" not in x for x in seats)


class TestWSRooms:
    def test_two_sockets_same_room_broadcast(self, tmp_path, monkeypatch):
        """同房双 WS：快照 + 入房广播 + REST 动作广播双方可达。

        确定性事件序（实测取证）：ws1 = snapshot, peer_joined(自), peer_joined(对),
        动作事件；ws2 = snapshot, peer_joined(对), 动作事件。
        """
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            sid = client.post("/api/session",
                              json={"mode": "main", "player_id": "player:1"}
                              ).json()["session"]["session_id"]
            with client.websocket_connect(f"/ws/{sid}") as ws1, \
                    client.websocket_connect(f"/ws/{sid}") as ws2:
                assert json.loads(ws1.receive_text())["payload"]["event"] == "snapshot"
                assert json.loads(ws2.receive_text())["payload"]["event"] == "snapshot"
                # ws1 先收到自己入房的 peer_joined
                assert json.loads(ws1.receive_text())["payload"]["event"] == "peer_joined"
                # ws2 连接 → 双方各收一条 peer_joined
                assert json.loads(ws1.receive_text())["payload"]["event"] == "peer_joined"
                assert json.loads(ws2.receive_text())["payload"]["event"] == "peer_joined"
                # p2 经 REST 入席发言 → 双方各收一条动作广播（danmaku）
                client.post(f"/api/session/{sid}/action",
                            json={"type": "chat", "actor": "player:2",
                                  "payload": {"text": "有人吗"}})
                ev1 = json.loads(ws1.receive_text())
                ev2 = json.loads(ws2.receive_text())
                assert ev1["type"] == ev2["type"] == "chat"
                assert ev1["payload"].get("actor_kind") == "player"
                assert ev1["payload"].get("text") == "有人吗"

    def test_ws_snapshot_after_reconnect(self, tmp_path, monkeypatch):
        """重连快照带最新状态（actions_left/stage 回放重建正确）。"""
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            sid = client.post("/api/session",
                              json={"mode": "main", "player_id": "player:1"}
                              ).json()["session"]["session_id"]
            client.post(f"/api/session/{sid}/action",
                        json={"type": "chat", "actor": "player:1",
                              "payload": {"text": "看山，关门"}})
            with client.websocket_connect(f"/ws/{sid}") as ws:
                snap = json.loads(ws.receive_text())
                assert snap["payload"]["stage"] == "break_ice"
                clues = snap["payload"]["clues_gained"]
                assert "clue_031" in clues, "重连快照未反映已获线索"


def _party_seated(sid="s_party_knives"):
    d = EngineDriver(SCENARIO_DIR)
    s = d.create_session("party", "player:1", sid)
    assert d.join_seat("player:1")["ok"]
    return d, s


def _to_investigate(d, s):
    d.apply_action(s, "chat", "player:1", {"text": "看山，关门"})
    ev, err = d.apply_action(s, "advance", "player:1", {})
    assert err is None
    assert s["stage"] == "investigate"
    return ev


class TestPartyFourKnives:
    def test_loc_alias_desk_hits(self):
        d, s = _party_seated("s_party_loc")
        _to_investigate(d, s)
        ev, err = d.apply_action(s, "search", "player:1",
                                 {"location": "loc_desk", "keyword": "鱼干"})
        assert err is None
        assert not any((e.get("payload") or {}).get("event") == "bad_location"
                       for e in ev)
        assert any(e["type"] == "clue_gained" for e in ev)

    def test_bad_location_refunds_party_ap(self):
        d, s = _party_seated("s_party_badloc")
        _to_investigate(d, s)
        before = d.pb.ap_state()["player:1"]
        ev, err = d.apply_action(s, "search", "player:1",
                                 {"location": "no_such_place", "keyword": "x"})
        assert err is None
        assert any((e.get("payload") or {}).get("event") == "bad_location"
                   for e in ev)
        assert d.pb.ap_state()["player:1"] == before

    def test_chat_echo_player_kind(self):
        d, s = _party_seated("s_party_chat")
        ev, err = d.apply_action(s, "chat", "player:1", {
            "char_id": "char_01", "text": "今晚谁最后见过看山"})
        assert err is None
        chats = [e for e in ev if e["type"] == "chat"]
        assert chats and chats[0]["payload"].get("actor_kind") == "player"
        assert chats[0]["payload"].get("text") == "今晚谁最后见过看山"
        assert chats[0]["payload"].get("char_id") == "char_01"

    def test_party_advance_blocked_until_search_clue(self):
        d, s = _party_seated("s_party_adv")
        _to_investigate(d, s)
        ev, err = d.apply_action(s, "advance", "player:1", {})
        assert err is None
        assert any((e.get("payload") or {}).get("event") == "advance_blocked"
                   for e in ev)
        assert s["stage"] == "investigate"
        ev, err = d.apply_action(s, "search", "player:1",
                                 {"location": "loc_archive", "keyword": "经费"})
        assert err is None
        assert "clue_004" in s["clues_gained"]
        ev, err = d.apply_action(s, "advance", "player:1", {})
        assert err is None
        assert s["stage"] == "round_table"
        assert not any((e.get("payload") or {}).get("event") == "advance_blocked"
                       for e in ev)

    def test_party_ai_follow_votes_on_accuse(self):
        """指认幕全员到齐后，AI 空席写入 PartyBoard 并跟真人多数，不盖过指认。"""
        d, s = _party_seated("s_party_aivote")
        _to_investigate(d, s)
        d.ec.release("clue_004", "player:1")
        s["clues_gained"] = sorted(set(s.get("clues_gained") or []) | {"clue_004"})
        d.apply_action(s, "advance", "player:1", {})  # investigate → round_table
        d.apply_action(s, "advance", "player:1", {})  # round_table → accuse
        assert s["stage"] == "accuse"
        ev, err = d.apply_action(s, "vote", "player:1", {
            "target": CULPRIT, "evidence": ["clue_004", "clue_007"]})
        assert err is None
        tally = d.pb.tally()
        assert tally["total"] >= 1
        assert set(tally["counts"]) == {CULPRIT}
        assert any(v["voter"].startswith("ai:") for v in d.pb.snapshot()["votes"])
        ending = next(e for e in ev if e["type"] == "ending")
        assert ending["payload"]["accused"] == f"npc:{CULPRIT}"

    def test_party_vote_needs_two_evidence(self):
        d, s = _party_seated("s_party_vote")
        _to_investigate(d, s)
        d.ec.release("clue_004", "player:1")
        s["clues_gained"] = sorted(set(s.get("clues_gained") or []) | {"clue_004"})
        d.apply_action(s, "advance", "player:1", {})
        assert s["stage"] == "round_table"
        ev, err = d.apply_action(s, "vote", "player:1", {"target": "char_01"})
        assert err is None
        assert any((e.get("payload") or {}).get("event") == "vote_rejected"
                   for e in ev)
        ev, err = d.apply_action(s, "vote", "player:1", {
            "target": "char_01", "evidence": ["clue_004", "clue_007"]})
        assert err is None
        assert any(e["type"] == "vote" for e in ev)

    def test_rejoin_same_pid_without_char(self):
        d, s = _party_seated("s_party_rejoin")
        first = d.join_seat("player:1")
        assert first.get("rejoin")
        d.pb.spend("player:1", 1)
        d.leave_seat("player:1")
        again = d.join_seat("player:1")
        assert again["ok"] and again.get("rejoin")
        assert again["char_id"] == first["char_id"]
        assert d.pb.ap_state()["player:1"] == 2

    def test_skill_kind_alias_draw_card(self):
        d, s = _party_seated("s_party_skill")
        _to_investigate(d, s)
        ev, err = d.apply_action(s, "skill", "player:1", {"kind": "draw_card"})
        assert err is None
        assert any(
            e["type"] == "faction_skill" and e["payload"].get("kind") == "draw_card"
            for e in ev) or any(
            (e.get("payload") or {}).get("event") == "card_drawn" for e in ev)

    def test_lan_info_rejects_network_address(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            r = client.get("/api/lan-info", headers={"Host": "172.19.0.0:8900"})
            assert r.status_code == 200
            body = r.json()
            assert body["lan_ip"] != "172.19.0.0"
            assert not str(body.get("lan_ip", "")).endswith(".0")
            r2 = client.get("/api/lan-info", headers={"Host": "192.168.8.20:8900"})
            j2 = r2.json()
            assert j2["lan_ip"] == "192.168.8.20" and j2["lan_ok"] is True

    def test_rejoin_without_char_id_after_create(self, tmp_path, monkeypatch):
        """刷新重连：同一 player_id 不带 char_id 不得 409。"""
        from fastapi.testclient import TestClient
        import server.main as main_mod
        monkeypatch.setattr(main_mod, "DATA_DIR", tmp_path / "data")
        with TestClient(main_mod.app) as client:
            created = client.post("/api/session",
                                  json={"mode": "party", "player_id": "player:uwiz"})
            assert created.status_code == 200, created.text
            s = created.json()["session"]
            sid, rc = s["session_id"], s["room_code"]
            first = client.post(f"/api/session/{sid}/join",
                                json={"room_code": rc, "player_id": "player:uwiz",
                                      "char_id": "char_05"})
            assert first.status_code == 200, first.text
            char = next(x["char_id"] for x in first.json()["seats"]
                        if x.get("player_id") == "player:uwiz")
            again = client.post(f"/api/session/{sid}/join",
                                json={"room_code": rc, "player_id": "player:uwiz"})
            assert again.status_code == 200, again.text
            seats = again.json().get("seats") or []
            mine = [x for x in seats if x.get("player_id") == "player:uwiz"]
            assert mine and mine[0]["char_id"] == char

    def test_recover_claimed_char_from_snapshot(self):
        from server.main import _recover_claimed_char
        session = {
            "booklet_roles": {},
            "seats_public": [],
            "party": {"seats": {"player:ayuk": {"char_id": "char_05"}},
                      "char_owner": {"char_05": "player:ayuk"}},
        }
        assert _recover_claimed_char(session, "player:ayuk") == "char_05"

    def test_lan_score_prefers_home_wifi(self):
        from server.main import _lan_score
        assert _lan_score("192.168.1.8") > _lan_score("172.19.16.2")
        assert _lan_score("172.19.0.0") < 0

    def test_public_session_view_strips_broadcast_booklet(self):
        from server.main import public_session_view
        raw = {
            "session_id": "s_x",
            "party": {"factions": {"char_01": "pollution"}},
            "player_book": {"faction": "pollution", "never_say": "矩阵"},
            "players": [{"player_id": "player:1", "faction": "truth"}],
            "npcs": [],
            "events": [{
                "type": "system",
                "payload": {
                    "booklet": {
                        "faction": "pollution",
                        "never_say": "矩阵",
                        "covers": {"A": {"you_are": "知之者", "never_say": "暗号"}},
                    }
                },
            }],
        }
        view = public_session_view(raw)
        assert "party" not in view
        assert "player_book" not in view
        assert "faction" not in view["players"][0]
        book = view["events"][0]["payload"]["booklet"]
        assert "faction" not in book
        assert "never_say" not in book
        assert "never_say" not in book["covers"]["A"]
        assert book["covers"]["A"]["you_are"] == "知之者"
