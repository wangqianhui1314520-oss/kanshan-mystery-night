import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from server.engine_driver import EngineDriver
from server.main import GameServer, SCENARIO_DIR
from engine.stage_machine import Stage
from test_npc_social import MemoryStore


def ready():
    eng = EngineDriver(SCENARIO_DIR)
    session = eng.create_session('main', 'player:1', 'bridge_test')
    eng.apply_action(session, 'advance', 'player:1', {})
    return eng, session


def test_memory_read_is_unlock_filtered_and_socket_bound():
    eng, session = ready()
    before = eng.memory_view('char_02')
    assert not before['heart_unlocked']
    assert all(b['layer'] != 'heart' for b in before['blocks'])
    server = GameServer(SCENARIO_DIR)
    server.store = MemoryStore()
    server.store.save_session('bridge_test', session)
    server.engines['bridge_test'] = eng
    ws = SimpleNamespace(state=SimpleNamespace(room_id='bridge_test', player_id='player:1', spectator=False), send_text=AsyncMock())
    message = json.dumps({'type': 'skill', 'payload': {'skill': 'memory_read', 'target': 'char_02'}})
    asyncio.run(server.handle(ws, message))
    assert 'memory_snapshot' not in ws.send_text.call_args.args[0]
    ws.send_text.reset_mock()
    server.rooms['bridge_test'] = {'players': {'player:1': ws}}
    asyncio.run(server.handle(ws, message))
    assert json.loads(ws.send_text.call_args.args[0])['payload']['blocks'] == before['blocks']
    assert server.store.load_session('bridge_test')['actions'] == session['actions']


def test_unlock_payload_and_puzzle_replay():
    eng, session = ready()
    for cid in ('char_01', 'char_02', 'char_03'):
        events, error = eng.apply_action(session, 'skill', 'player:1', {'skill': 'memory_fix', 'target': cid})
        assert error is None
        unlock = next(e['payload'] for e in events if e['type'] == 'memory_unlock')
        assert unlock['char_id'] == cid
        assert unlock['version'] == unlock['unlocked_version']
        assert unlock['blocks'] == eng.memory_view(cid)['blocks']
    assert eng.ms.tamper_available() >= 2
    before = eng.ms.tamper_available()
    answer = eng.ms.puzzle_answer('char_02')
    events, error = eng.apply_action(session, 'skill', 'player:1', {'skill': 'puzzle', 'target': 'char_02', 'proposal': answer})
    assert error is None and events[0]['payload']['correct']
    assert eng.ms.tamper_available() == before - 2
    replay = EngineDriver(SCENARIO_DIR)
    replay_session = replay.create_session('main', 'player:1', 'replay')
    for action in session['actions']:
        _, error = replay.apply_action(replay_session, action['type'], action['actor'], action['payload'])
        assert error is None
    assert replay.ms.tamper_available() == eng.ms.tamper_available()
    assert replay.ms.puzzle_wins() == eng.ms.puzzle_wins()


def test_incomplete_puzzle_does_not_spend_points():
    eng, session = ready()
    before = eng.ms.tamper_available()
    _, error = eng.apply_action(session, 'skill', 'player:1', {'skill': 'puzzle', 'target': 'char_02', 'proposal': ['unknown']})
    assert error and eng.ms.tamper_available() == before


def test_headline_in_finale_cost_and_invalid_amount():
    eng, session = ready()
    eng.sm.stage = Stage.ACCUSE
    session['stage'] = 'accuse'
    post = next(iter(eng.of._posts))
    before = eng.sm.actions_left
    events, error = eng.apply_action(session, 'skill', 'player:1', {'skill': 'bid_headline', 'amount': 2, 'post': post})
    assert error is None
    assert session['actions_left'] == before - 2
    assert events[0]['payload']['settle']['winner'] == 'player:1'
    assert 'faction' not in json.dumps(events)
    before = session['actions_left']
    for amount in (0, -1, 2.5, True, 99):
        _, error = eng.apply_action(session, 'skill', 'player:1', {'skill': 'bid_headline', 'amount': amount, 'post': post})
        assert error and session['actions_left'] == before
    _, error = eng.apply_action(session, 'skill', 'player:1', {'skill': 'truth_check'})
    assert error is None


def test_closed_game_rejects_finale_skills():
    eng, session = ready()
    session['status'] = 'ended'
    _, error = eng.apply_action(session, 'skill', 'player:1', {'skill': 'bid_headline', 'amount': 1, 'post': 'post_001'})
    assert error
