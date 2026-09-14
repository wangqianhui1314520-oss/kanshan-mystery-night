"""缺口修复回归：暗拍照片 owner 隔离 + share_photo 服务端流、cross_check 服务端裁决。

零 AI、零网络：AgentRuntime 仅做确定性引擎裁决（EvidenceChain 静态剧本池），
AI wave 全部 patch 掉；会话状态手工构造（mock 档计数），不真实调 LLM。
"""
import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from server.main import GameServer, SCENARIO_DIR, RT_SKILL_FLOWS
from server.store.session_store import SessionStore

ACTOR = "player:1"
OTHER = "player:2"


def make_server(tmp_root: Path) -> GameServer:
    server = GameServer(SCENARIO_DIR)
    server.store = SessionStore(tmp_root)
    return server


def make_session(server: GameServer, sid: str, held: list[str] | None = None) -> dict:
    """mock 档最小会话：rt 演出层 + AP 计数 + 持有线索均可确定性驱动。"""
    session = {
        "session_id": sid, "round": 1, "stage": "round_table",
        "engine": "mock", "mode": "main", "status": "playing",
        "players": [{"player_id": ACTOR}, {"player_id": OTHER}],
        "actions_left": 6, "actions": [], "events": [],
        "clues_gained": list(held or []),
    }
    server.store.save_session(sid, session)
    return session


def photo_of_rt(server: GameServer, session: dict, actor: str):
    """直接用引擎证据链造一张照片（确定性：快递柜 + 冰袋关键词命中 clue_011）。"""
    rt = server.get_runtime(session)
    res = rt.evidence.stealth_photo("快递柜", "冰袋", actor, round_no=1)
    assert res.get("ok"), f"测试造照片失败：{res}"
    return res["photo"]


# --------------------------------------------------------------- 缺口1：share_photo

def test_share_photo_is_server_routed():
    """share_photo 已进入 rt 技能流白名单（WS/REST 同一服务端管线）。"""
    assert "share_photo" in RT_SKILL_FLOWS
    assert "cross_check" in RT_SKILL_FLOWS


def test_share_photo_owner_scope_and_broadcast(tmp_path):
    """owner 隔离：本人可流出自己的照片（事件带 owner）；他人不能流出。"""
    server = make_server(tmp_path / uuid4().hex)
    sid = "s_share_photo"
    session = make_session(server, sid)
    photo = photo_of_rt(server, session, OTHER)

    # 他人（player:1）流出 player:2 的照片 → 服务端拒绝，不伪造事件
    events, error = server._rt_skill_flow(session, ACTOR, {
        "skill": "share_photo", "photo_id": photo["photo_id"], "claim": "我的照片"})
    assert error is not None and not events

    # 持有人本人流出 → photo_shared 事件，owner 归属正确
    events, error = server._rt_skill_flow(session, OTHER, {
        "skill": "share_photo", "photo_id": photo["photo_id"], "claim": "深夜的快递柜"})
    assert error is None
    evt = events[0]
    assert evt["payload"]["event"] == "photo_shared"
    assert evt["payload"]["owner"] == OTHER
    assert evt["payload"]["photo_id"] == photo["photo_id"]
    assert evt["payload"]["claim"] == "深夜的快递柜"


def test_share_photo_via_run_action_persists_event(tmp_path):
    """全链路：REST/WS 统一动作管线可达 share_photo 流并落库。"""
    server = make_server(tmp_path / uuid4().hex)
    sid = "s_share_full"
    session = make_session(server, sid)
    photo = photo_of_rt(server, session, ACTOR)

    async def no_wave(*args):
        return []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server, "run_ai_wave", no_wave)
        events, error = asyncio.run(server.run_action(
            sid, "skill", ACTOR,
            {"skill": "share_photo", "photo_id": photo["photo_id"], "claim": "声称"}))
    assert error is None
    assert any(e["payload"].get("event") == "photo_shared" for e in events)
    persisted = server.store.load_session(sid)
    assert any(e["payload"].get("event") == "photo_shared"
               for e in persisted["events"])


def test_stealth_photo_event_carries_owner(tmp_path):
    """暗拍结果事件的 photo.owner=暗拍者（前端照片墙按此隔离）。"""
    server = make_server(tmp_path / uuid4().hex)
    session = make_session(server, "s_stealth_owner")

    events, error = server._rt_skill_flow(session, ACTOR, {
        "skill": "stealth_photo", "location": "快递柜", "keyword": "冰袋"})
    assert error is None
    evt = next(e for e in events if e["payload"].get("event") == "stealth_photo_result")
    assert evt["payload"]["ok"] is True
    assert evt["payload"]["photo"]["owner"] == ACTOR
    assert evt["payload"]["owner"] == ACTOR


# --------------------------------------------------------------- 缺口2：cross_check

def test_cross_check_exposed_when_real_clue_held(tmp_path):
    """持有 fake_of 真线索 → verdict=exposed（clue_022 fake → clue_011 真）。"""
    server = make_server(tmp_path / uuid4().hex)
    session = make_session(server, "s_cc_hit", held=["clue_011", "clue_022"])

    events, error = server._rt_skill_flow(session, ACTOR,
                                          {"skill": "cross_check", "clue_id": "clue_022"})
    assert error is None
    evt = events[0]
    assert evt["payload"]["event"] == "cross_check_result"
    assert evt["payload"]["verdict"] == "exposed"
    assert evt["payload"]["exposed"] is True
    assert evt["payload"]["real_id"] == "clue_011"


def test_cross_check_insufficient_without_real_clue(tmp_path):
    """未持有真线索 → verdict=insufficient，exposed 不误标。"""
    server = make_server(tmp_path / uuid4().hex)
    session = make_session(server, "s_cc_miss", held=["clue_022"])

    events, error = server._rt_skill_flow(session, ACTOR,
                                          {"skill": "cross_check", "clue_id": "clue_022"})
    assert error is None
    payload = events[0]["payload"]
    assert payload["event"] == "cross_check_result"
    assert payload["verdict"] == "insufficient"
    assert payload["exposed"] is False


def test_cross_check_rejects_non_fake_clue(tmp_path):
    """非伪证线索 → 服务端明确报错（不伪造裁决事件）。"""
    server = make_server(tmp_path / uuid4().hex)
    session = make_session(server, "s_cc_reject", held=["clue_011"])

    events, error = server._rt_skill_flow(session, ACTOR,
                                          {"skill": "cross_check", "clue_id": "clue_011"})
    assert error is not None and not events
