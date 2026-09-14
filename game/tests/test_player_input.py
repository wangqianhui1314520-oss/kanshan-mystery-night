import asyncio
from unittest.mock import patch

import pytest

from engine.stage_machine import Stage
from server.engine_driver import EngineDriver
from server.main import GameServer, SCENARIO_DIR
from server.player_input import parse_player_intent
from server.store.session_store import SessionStore


@pytest.mark.parametrize('verb', ['搜证', '调查', '查找', '搜索', '搜查'])
def test_synonyms(verb):
    assert parse_player_intent(f'我要去监控室{verb}监控', stage='investigate',
                               locations={'room': '监控室'}) == {
        'action_type': 'search', 'payload': {'location': 'room', 'keyword': '监控'}}


@pytest.mark.parametrize('stage', [None, 'break_ice', 'round_table', 'accuse', 'review', 'unknown'])
def test_stage_gate(stage):
    assert parse_player_intent('去监控室搜证监控', stage=stage,
                               locations={'room': '监控室'}) is None


@pytest.mark.parametrize('text', ['去监控室搜证', '搜证监控', '去未知地点搜证监控',
    '不要去监控室搜证监控', '去监控室搜证监控吗', '去监控室搜证监控？',
    '“去监控室搜证监控”', '他说去监控室搜证监控', '去监控室和茶馆搜证监控',
    '去监控室搜证监控，然后去茶馆', '你好'])
def test_unclear_falls_back(text):
    assert parse_player_intent(text, stage='investigate',
                               locations={'room': '监控室', 'tea': '茶馆'}) is None


def test_ambiguous_location():
    assert parse_player_intent('去监控室搜证监控', stage='investigate',
                               locations={'a': '监控室', 'b': '监控室'}) is None


@pytest.fixture
def game(tmp_path):
    server = GameServer(SCENARIO_DIR)
    server.store = SessionStore(tmp_path)
    engine = EngineDriver(SCENARIO_DIR)
    session = engine.create_session('main', 'player:1', 'intent_test')
    engine.sm.stage = Stage.INVESTIGATE
    session['stage'] = 'investigate'
    server.engines['intent_test'] = engine
    server.store.save_session('intent_test', session)
    async def no_wave(*args):
        return []
    with patch.object(server, 'run_ai_wave', no_wave), patch.object(server, 'get_runtime', return_value=None), \
         patch.object(server, '_llm_for_session', return_value=None):
        yield server, engine, session


def command(engine):
    return {'text': f'去{next(iter(engine._loc_names.values()))}搜证监控', 'target': 'dm'}


def test_routes_once_through_engine_and_charges_ap(game):
    server, engine, session = game
    before = session['actions_left']
    with patch.object(engine, 'apply_action', wraps=engine.apply_action) as apply:
        events, error = asyncio.run(server.run_action('intent_test', 'chat', 'player:1', command(engine)))
    assert error is None
    assert apply.call_count == 1
    assert apply.call_args.args[1] == 'search'
    assert server.store.load_session('intent_test')['actions_left'] == before - 1
    assert any(e['type'] == 'search_result' for e in events)


def test_ap_cannot_be_bypassed(game):
    server, engine, session = game
    session['actions_left'] = engine.sm.actions_left = 0
    server.store.save_session('intent_test', session)
    events, error = asyncio.run(server.run_action('intent_test', 'chat', 'player:1', command(engine)))
    assert events == [] and '行动力不足' in error['notice']
    assert server.store.load_session('intent_test')['actions_left'] == 0
    assert server.store.load_session('intent_test')['actions'] == []


def test_engine_rechecks_stage(game):
    server, engine, session = game
    engine.sm.stage = Stage.BREAK_ICE  # 存档阶段过期也不能越过真实引擎。
    events, error = asyncio.run(server.run_action('intent_test', 'chat', 'player:1', command(engine)))
    assert events == [] and '不允许动作 search' in error['notice']
    assert server.store.load_session('intent_test')['actions_left'] == session['actions_left']


@pytest.mark.parametrize('extra,allow_ai', [({'whisper': True}, False), ({'team': True}, False), ({}, True)])
def test_non_public_or_ai_chat_stays_chat(game, extra, allow_ai):
    server, engine, session = game
    with patch.object(engine, 'apply_action', wraps=engine.apply_action) as apply:
        _, error = asyncio.run(server.run_action('intent_test', 'chat', 'player:1',
                                                {**command(engine), **extra}, allow_ai=allow_ai))
    assert error is None
    assert apply.call_args.args[1] == 'chat'
    assert server.store.load_session('intent_test')['actions_left'] == session['actions_left']


def test_mock_not_adapted(game):
    server, engine, session = game
    session['engine'] = 'mock'
    server.store.save_session('intent_test', session)
    with patch.object(server, 'get_mock_engine') as mock:
        mock.return_value.apply_action.return_value = ([], None)
        _, error = asyncio.run(server.run_action('intent_test', 'chat', 'player:1', command(engine)))
    assert error is None
    assert mock.return_value.apply_action.call_args.args[1] == 'chat'
