"""真人公开聊天后的 AI 社交回应链路守护（QA 铁律：mutation test 基线）。

覆盖三条新契约：
1. 真人公开 chat → 走 run_chat_respond（npc_social 公开波），AI 回应
   针对聊天内容（context 含玩家原话），非自走棋（无 booklet_act 标记）。
2. 真人非聊天动作（搜证等）→ 仍走自走棋 run_ai_wave（零行为变更）。
3. phase 跟随 DM 引导（infer_social_phase）+ 自由讨论 2 席轮转限流。
"""
import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from agents.llm_client import LLMClient, Provider
from server.engine_driver import EngineDriver
from server.main import SCENARIO_DIR, GameServer
from server.npc_social import infer_social_phase


class MemoryStore:
    def __init__(self):
        self.sessions = {}

    def load_session(self, sid):
        return copy.deepcopy(self.sessions.get(sid))

    def save_session(self, sid, session):
        self.sessions[sid] = copy.deepcopy(session)


class ReplyProvider(Provider):
    name = "main"

    def __init__(self):
        self.inputs = []

    def chat(self, system, user, **kwargs):
        self.inputs.append(system + '\n' + user)
        return "我们先核对公开口供，再讨论疑点。"


@pytest.fixture
def resp(monkeypatch):
    server = GameServer(SCENARIO_DIR)
    server.store = MemoryStore()
    eng = EngineDriver(SCENARIO_DIR)
    session = eng.create_session('main', 'player:1', 'respond_test')
    session['booklet_roles'] = {'player:1': 'char_01'}
    server.engines['respond_test'] = eng
    server.store.save_session('respond_test', session)
    provider = ReplyProvider()
    llm = LLMClient(providers={'main': provider})
    llm.cache._data = {}
    llm.cache._file = None
    monkeypatch.setattr(server, '_llm_for_session', lambda sid: llm)
    monkeypatch.setattr(server, 'broadcast', AsyncMock())
    monkeypatch.setattr(server, 'broadcast_to', AsyncMock())
    return server, provider


def _ai_replies(events):
    return [e for e in events
            if e.get('type') == 'chat' and str(e.get('actor', '')).startswith('npc:')]


def test_human_chat_triggers_chat_respond_with_context(resp):
    """真人公开聊天 → AI 社交回应（非自走棋），且 prompt 含玩家原话。"""
    server, provider = resp
    events, error = asyncio.run(server.run_action(
        'respond_test', 'chat', 'player:1',
        {'text': '你们昨晚十点到底在哪里？'}))
    assert error is None, error
    replies = _ai_replies(events)
    assert replies, "真人公开聊天后必须有空席 AI 回应"
    # 社交回应通道标记：source=agent + wave，且不带自走棋的 booklet_act 标记
    for r in replies:
        assert r['payload'].get('source') == 'agent'
        assert r['payload'].get('wave') is True
        assert 'booklet_act' not in r['payload']
        assert r['payload'].get('booklet_act') is not True
    # 回应围绕玩家发言：LLM 输入里能看到玩家原话
    assert any('你们昨晚十点到底在哪里' in inp for inp in provider.inputs)


def test_human_search_still_uses_selfplay_wave(resp):
    """真人搜证 → 仍走自走棋 wave（行为不变）；非聊天事件不触发社交回应。"""
    server, provider = resp
    from engine.stage_machine import Stage
    eng = server.engines['respond_test']
    eng.sm.stage = Stage.INVESTIGATE       # 引擎与 session stage 同步
    eng.sm.actions_left = 5
    session = server.store.load_session('respond_test')
    session['stage'] = 'investigate'
    session['actions_left'] = 5
    server.store.save_session('respond_test', session)
    marker = {'type': 'system', 'payload': {'event': 'selfplay_marker'}}
    server.run_ai_wave = AsyncMock(return_value=[marker])
    server.run_chat_respond = AsyncMock(return_value=[])
    events, error = asyncio.run(server.run_action(
        'respond_test', 'search', 'player:1',
        {'location': '监控室', 'keyword': '时间线'}))
    assert error is None, error
    server.run_ai_wave.assert_awaited()
    server.run_chat_respond.assert_not_awaited()
    assert any(e.get('payload', {}).get('event') == 'selfplay_marker' for e in events)


def test_with_ai_wave_routes_by_event_kind(resp):
    """_with_ai_wave 按事件分流：真人广播发言 → 社交回应；定向/其余 → 自走棋。"""
    server, _ = resp
    human_chat = [{'type': 'chat', 'actor': 'player:1',
                   'payload': {'text': '在吗', 'wave': False}}]
    targeted = [{'type': 'chat', 'actor': 'player:1',
                 'payload': {'text': '问你', 'target': 'char_05'}}]
    other = [{'type': 'search_result', 'actor': 'kanshan', 'payload': {}}]
    server.run_chat_respond = AsyncMock(return_value=[{'type': 'chat', 'actor': 'npc:char_02', 'payload': {}}])
    server.run_ai_wave = AsyncMock(return_value=[{'type': 'system', 'payload': {'event': 'selfplay'}}])
    got, _ = asyncio.run(server._with_ai_wave('respond_test', human_chat, allow_ai=False))
    server.run_chat_respond.assert_awaited_once()
    server.run_ai_wave.assert_not_awaited()
    assert got[-1]['actor'] == 'npc:char_02'
    server.run_chat_respond.reset_mock()
    server.run_ai_wave.reset_mock()
    # 定向对具体 NPC 发言：已有引擎内定向回应链路，不重复触发社交回应
    asyncio.run(server._with_ai_wave('respond_test', targeted, allow_ai=False))
    server.run_chat_respond.assert_not_awaited()
    server.run_ai_wave.assert_awaited_once()
    server.run_chat_respond.reset_mock()
    server.run_ai_wave.reset_mock()
    asyncio.run(server._with_ai_wave('respond_test', other, allow_ai=False))
    server.run_chat_respond.assert_not_awaited()
    server.run_ai_wave.assert_awaited_once()


def test_with_ai_wave_skips_ai_and_whisper_chat(resp):
    """自走棋产生的 chat（player:ai:/ai:/whisper）不得再触发社交回应（防递归/防刷屏）。"""
    server, _ = resp
    ai_chat = [{'type': 'chat', 'actor': 'player:ai:char_02',
                'payload': {'text': '按本台词'}}]
    whisper = [{'type': 'chat', 'actor': 'player:1',
                'payload': {'text': '悄悄话', 'whisper': True}}]
    server.run_chat_respond = AsyncMock(return_value=[])
    server.run_ai_wave = AsyncMock(return_value=[])
    asyncio.run(server._with_ai_wave('respond_test', ai_chat, allow_ai=False))
    asyncio.run(server._with_ai_wave('respond_test', whisper, allow_ai=False))
    server.run_chat_respond.assert_not_awaited()


def test_discussion_all_seats_reply_in_order(resp):
    """自由讨论：真人一句话后全体空席 AI 按席位顺序串联回复（比赛模式
    已取消 2 席限流），每次请求覆盖全部空席。"""
    server, provider = resp
    session = server.store.load_session('respond_test')
    session['stage'] = 'investigate'
    server.store.save_session('respond_test', session)
    first = asyncio.run(server.run_chat_respond('respond_test'))
    seats_1 = [e['actor'] for e in _ai_replies(first)]
    assert len(seats_1) == 7, f"自由讨论应全员 7 席串联回复，实际 {len(seats_1)}"
    # 串联顺序 = 席位池顺序（char_02..char_08，char_01 由真人认领）
    assert seats_1 == sorted(seats_1), "AI 应按席位顺序依次回复"
    second = asyncio.run(server.run_chat_respond('respond_test'))
    seats_2 = [e['actor'] for e in _ai_replies(second)]
    assert len(seats_2) == 7


def test_break_ice_intro_follows_dm_guidance(resp):
    """破冰 DM 引导下全员按席位顺序串联自我介绍（一次请求覆盖 7 席），
    覆盖满一轮后落 done 标记。"""
    server, provider = resp
    session = server.store.load_session('respond_test')
    session.setdefault('events', []).append({
        'type': 'system', 'actor': 'dm', 'payload': {'text': '各位请轮流做个自我介绍吧。'}})
    server.store.save_session('respond_test', session)
    out = asyncio.run(server.run_chat_respond('respond_test'))
    seats = [e['actor'] for e in _ai_replies(out)]
    assert len(seats) == 7, f"破冰引导应全员 7 席串联回复，实际 {len(seats)}"
    assert any('自我介绍' in inp for inp in provider.inputs)
    # 全员一轮后落 done：此后同 phase 的自动回应回落自由讨论回应模式
    assert 'intro' in (server.store.load_session('respond_test').get('social_phases_done') or [])


def test_infer_phase_follows_dm_lines():
    """phase 推断：DM 说介绍 → intro；说读本 → testimony；说自由讨论 → 空；
    无 DM 引导证据 → 空（回落讨论回应模式，全员轮流只由显式 phase 触发）。"""
    base = {'stage': 'break_ice', 'events': []}
    assert infer_social_phase(base, 'break_ice') == ''
    s2 = {'stage': 'break_ice', 'events': [
        {'type': 'system', 'actor': 'dm', 'payload': {'text': '读本完成后，依次陈述你当晚的行踪。'}}]}
    assert infer_social_phase(s2, 'break_ice') == 'testimony'
    s3 = {'stage': 'investigate', 'events': [
        {'type': 'system', 'actor': 'dm', 'payload': {'text': '现在开始自由讨论，大家畅所欲言。'}}]}
    assert infer_social_phase(s3, 'investigate') == ''
    s4 = {'stage': 'investigate', 'events': [
        {'type': 'chat', 'actor': 'player:1', 'payload': {'text': 'hello'}}]}
    assert infer_social_phase(s4, 'investigate') == ''


def test_guided_phase_runs_once_then_falls_back(resp):
    """DM 引导环节一次请求全员串联（7 席）后落 done；此后同 phase 自动回应
    回落自由讨论回应模式（不再重复介绍，但同样全员回应）。"""
    server, provider = resp
    session = server.store.load_session('respond_test')
    session.setdefault('events', []).append({
        'type': 'system', 'actor': 'dm', 'payload': {'text': '各位请轮流做个自我介绍吧。'}})
    server.store.save_session('respond_test', session)
    asyncio.run(server.run_chat_respond('respond_test'))   # 全员一轮覆盖 7 席
    saved = server.store.load_session('respond_test')
    assert 'intro' in (saved.get('social_phases_done') or []), "覆盖满一轮后应落 done"
    second = asyncio.run(server.run_chat_respond('respond_test'))
    seats = [e['actor'] for e in _ai_replies(second)]
    assert len(seats) == 7, "引导已轮过一轮，自动回应回落讨论模式（仍全员回应）"
    assert all('按圆桌顺序做 1-2 句自我介绍' not in inp
               for inp in provider.inputs[-7:]), "不应再重复 intro 专属模板"


def test_targeted_reply_contract_not_disturbed(resp):
    """定向发言（target=具体 NPC）不触发社交回应：回应席位由引擎定向链路负责。"""
    server, provider = resp
    from server.npc_social import social_request
    body = {'player_id': 'player:1', 'text': '你好', 'to': 'npc:char_05'}
    out = asyncio.run(social_request(server, 'respond_test', body, private=True))
    assert out['count'] == 1
    assert out['events'][-1]['actor'] == 'npc:char_05'


def test_fallback_without_llm(resp):
    """LLM 未配置 → 回退自走棋 wave（保持旧行为，零副作用）。"""
    server, _ = resp
    marker = [{'type': 'system', 'payload': {'event': 'selfplay_marker'}}]
    server.run_ai_wave = AsyncMock(return_value=marker)
    server._llm_for_session = lambda sid: None
    out = asyncio.run(server.run_chat_respond('respond_test'))
    server.run_ai_wave.assert_awaited_once()
    assert out == marker


def test_social_wave_endpoint_still_all_seats(resp):
    """DM 面板手动"请 AI 依次发言"：一次请求全员 7 席按顺序串联回复完毕，
    remaining=0（契约从"分波轮流"演进为"单请求全员串联"）。"""
    server, _ = resp
    from server.npc_social import social_request
    out = asyncio.run(social_request(server, 'respond_test',
                                     {'player_id': 'player:1'}, private=False))
    total = [e['actor'] for e in out['events']
             if e['type'] == 'chat' and e['actor'].startswith('npc:')]
    assert len(total) == 7, f"单请求应覆盖 7 席（无重复），实际 {len(total)}"
    assert len(set(total)) == 7
    assert out.get('remaining') == 0, "全员一轮完毕应无剩余席位"
    assert out['count'] == 7
