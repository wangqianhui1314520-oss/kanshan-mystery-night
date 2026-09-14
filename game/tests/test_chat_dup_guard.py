"""AI 台词重复上屏守护（QA 铁律 regression guard · 2026-09-14）。

背景事故：run_ai_act → run_action(allow_ai=True) 内部已统一广播 seat_events，
run_ai_wave 又对同一批事件二次广播；事件无 message_id，前端 socialMessagesSeen
去重失效 → WS 玩家每条 AI 台词相邻上屏两遍。

本文件两条守护：
1. 自走棋波（搜证触发）：每条事件在广播通道中恰好出现一次。
2. 真人公开聊天社交回应波：每条 message_id 在广播通道中恰好出现一次。

Mutation 基线：恢复 run_ai_wave 内二次广播后两条用例必须 FAIL。
"""
import asyncio
import copy
import json
from unittest.mock import AsyncMock

import pytest

from agents.llm_client import LLMClient, Provider
from server.engine_driver import EngineDriver
from server.main import SCENARIO_DIR, GameServer


class MemoryStore:
    def __init__(self):
        self.sessions = {}

    def load_session(self, sid):
        return copy.deepcopy(self.sessions.get(sid))

    def save_session(self, sid, session):
        self.sessions[sid] = copy.deepcopy(session)


class ReplyProvider(Provider):
    name = "main"

    def chat(self, system, user, **kwargs):
        return "我们先核对公开口供，再讨论疑点。"


@pytest.fixture
def guard(monkeypatch):
    server = GameServer(SCENARIO_DIR)
    server.store = MemoryStore()
    eng = EngineDriver(SCENARIO_DIR)
    session = eng.create_session('main', 'player:1', 'dup_guard')
    session['booklet_roles'] = {'player:1': 'char_01'}
    server.engines['dup_guard'] = eng
    server.store.save_session('dup_guard', session)
    llm = LLMClient(providers={'main': ReplyProvider()})
    llm.cache._data = {}
    llm.cache._file = None
    monkeypatch.setattr(server, '_llm_for_session', lambda sid: llm)
    # 广播记录器：保留每次调用的完整事件列表（空中流取证）
    calls: list[list[dict]] = []
    server.broadcast = AsyncMock(side_effect=lambda rid, evs: calls.append(list(evs)))
    server.broadcast_to = AsyncMock()
    return server, calls


def _air_chats(calls):
    """空中流中的全部 chat 事件（按广播顺序展开）。"""
    return [e for batch in calls for e in batch if e.get('type') == 'chat']


def test_selfplay_wave_broadcasts_each_event_once(guard):
    """真人搜证 → 自走棋波（后台任务）：每条 (type, actor, 席位, text) 恰好一次。"""
    from engine.stage_machine import Stage
    server, calls = guard
    eng = server.engines['dup_guard']
    eng.sm.stage = Stage.INVESTIGATE
    eng.sm.actions_left = 5
    session = server.store.load_session('dup_guard')
    session['stage'] = 'investigate'
    session['actions_left'] = 5
    server.store.save_session('dup_guard', session)

    async def _flow():
        events, error = await server.run_action(
            'dup_guard', 'search', 'player:1',
            {'location': '监控室', 'keyword': '时间线'})
        assert error is None, error
        # 同一事件循环内等待后台 wave 完成（asyncio.run 退出会取消 pending task）
        task = getattr(server, '_last_wave_task', None)
        if task is not None:
            await asyncio.wait_for(task, timeout=30)
        return events, error

    events, error = asyncio.run(_flow())
    assert calls, "自走棋波必须有广播"
    seen: dict[tuple, int] = {}
    for batch in calls:
        for e in batch:
            payload = e.get('payload') or {}
            # 签名含席位角色：引擎会对不同席位产出同文案群嘲弹幕（合法事件），
            # 不含席位会把"多席同文案"误判为双广播（2026-09-14 实测 7 连误报）。
            key = (e.get('type'), e.get('actor'),
                   str(payload.get('booklet_role') or ''),
                   str(payload.get('text', ''))[:60],
                   json.dumps(payload.get('items') or payload.get('event') or '',
                              ensure_ascii=False, sort_keys=True)[:80])
            seen[key] = seen.get(key, 0) + 1
    dups = {k: c for k, c in seen.items() if c > 1}
    assert not dups, f"广播通道出现重复事件（双广播回归）：{list(dups.items())[:3]}"


def test_social_wave_message_id_broadcast_once(guard):
    """真人公开聊天 → 社交回应波（后台任务）：每条 message_id 恰好一次。"""
    server, calls = guard

    async def _flow():
        events, error = await server.run_action(
            'dup_guard', 'chat', 'player:1', {'text': '大家好，我是新来的。'})
        assert error is None, error
        task = getattr(server, '_last_wave_task', None)
        if task is not None:
            await asyncio.wait_for(task, timeout=30)
        return events, error

    events, error = asyncio.run(_flow())
    mids = [(e.get('payload') or {}).get('message_id')
            for e in _air_chats(calls)]
    mids = [m for m in mids if m]
    assert mids, "社交回应波事件应携带 message_id（前端去重依据）"
    dup = {m: mids.count(m) for m in set(mids) if mids.count(m) > 1}
    assert not dup, f"同一 message_id 被多次广播：{dup}"


def test_wave_return_events_still_intact(guard):
    """修复不得改变返回值契约：run_ai_wave 仍返回全量席位事件
    （HTTP /ai_wave 响应、非 WS 前端依赖）。"""
    from engine.stage_machine import Stage
    server, calls = guard
    eng = server.engines['dup_guard']
    eng.sm.stage = Stage.INVESTIGATE
    eng.sm.actions_left = 5
    session = server.store.load_session('dup_guard')
    session['stage'] = 'investigate'
    session['actions_left'] = 5
    server.store.save_session('dup_guard', session)
    collected = asyncio.run(server.run_ai_wave('dup_guard'))
    # 席位动作类型由 PlayerAgent.decide 决定（investigate 阶段倾向搜证/开导，
    # 实测 3 次复跑均 0 chat），契约点是"返回值携带席位事件"，不限定类型。
    assert collected, "run_ai_wave 返回值仍须携带席位事件（契约不变）"
