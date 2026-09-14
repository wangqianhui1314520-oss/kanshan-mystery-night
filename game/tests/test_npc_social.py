"""HTTP social integration with real engine/agents and a deterministic provider."""
import copy
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

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

    def __init__(self):
        self.inputs = []

    def chat(self, system, user, **kwargs):
        self.inputs.append(system + '\n' + user)
        return "我们先核对公开口供，再讨论疑点。"


@pytest.fixture
def social(monkeypatch):
    import server.main as main
    server = GameServer(SCENARIO_DIR)
    server.store = MemoryStore()
    eng = EngineDriver(SCENARIO_DIR)
    session = eng.create_session('main', 'player:1', 'social_test')
    session['booklet_roles'] = {'player:1': 'char_01'}
    server.engines['social_test'] = eng
    server.store.save_session('social_test', session)
    provider = ReplyProvider()
    llm = LLMClient(providers={'main': provider})
    llm.cache._data = {}
    llm.cache._file = None
    monkeypatch.setattr(server, '_llm_for_session', lambda sid: llm)
    monkeypatch.setattr(server, 'broadcast', AsyncMock())
    monkeypatch.setattr(server, 'broadcast_to', AsyncMock())
    monkeypatch.setattr(main, 'game_server', server)
    monkeypatch.setattr(main.app.state, 'store', server.store, raising=False)
    monkeypatch.setattr(main.app.state, 'api_cfg', {}, raising=False)
    return TestClient(main.app), server, provider


def test_whisper_reply_is_private_and_persisted(social):
    client, server, provider = social
    before = server.store.load_session('social_test')['actions_left']
    response = client.post('/api/session/social_test/npc-whisper', json={
        'from': 'player:1', 'to': 'npc:char_02', 'text': '私聊暗号蓝色雨伞'})
    assert response.status_code == 200, response.text
    events = response.json()['events']
    assert len(events) == 2 and all(e['payload']['whisper'] for e in events)
    assert events[0]['actor'] == 'player:1'
    assert events[1]['actor'] == 'npc:char_02'
    saved = server.store.load_session('social_test')
    assert saved['events'][-2:] == events
    assert saved['actions_left'] == before
    assert '私聊暗号蓝色雨伞' in str(saved['npc_private_memory'])
    assert '私聊暗号蓝色雨伞' not in str(server.runtimes['social_test'].npcs['char_02'].memory)
    server.broadcast.assert_not_awaited()
    server.broadcast_to.assert_awaited_once_with('social_test', ['player:1'], events)
    public = client.get('/api/session/social_test').json()
    assert '私聊暗号蓝色雨伞' not in str(public)
    assert 'npc_private_memory' not in str(public)


def test_wave_excludes_human_and_does_not_use_private_memory(social):
    client, server, provider = social
    client.post('/api/session/social_test/npc-whisper', json={
        'to': 'char_02', 'text': '不能公开的蓝色雨伞'})
    provider.inputs.clear()
    r = client.post('/api/session/social_test/npc-wave', json={'player_id': 'player:1'})
    assert r.status_code == 200, r.text
    events = r.json()['events']
    assert r.json()['count'] == 7
    assert all(e['payload']['wave'] for e in events)
    assert 'npc:char_01' not in {e['actor'] for e in events}
    assert '不能公开的蓝色雨伞' not in str(provider.inputs)
    server.broadcast.assert_awaited_once_with('social_test', events)


@pytest.mark.parametrize('body,status', [
    ([], 400), ({'to': 'char_02', 'text': ''}, 400),
    ({'to': 'char_99', 'text': '你好'}, 404),
    ({'to': 'char_01', 'text': '你好'}, 409),
    ({'from': 'spectator:1', 'to': 'char_02', 'text': '你好'}, 403),
])
def test_private_validation(social, body, status):
    client, server, provider = social
    r = client.post('/api/session/social_test/npc-whisper', json=body)
    assert r.status_code == status, r.text
    assert not provider.inputs


def test_no_api_and_ended_game_are_honest_errors(social, monkeypatch):
    client, server, _ = social
    monkeypatch.setattr(server, '_llm_for_session', lambda sid: None)
    assert client.post('/api/session/social_test/npc-wave', json={}).status_code == 503
    session = server.store.load_session('social_test')
    session['status'] = 'ended'
    server.store.save_session('social_test', session)
    assert client.post('/api/session/social_test/npc-wave', json={}).status_code == 409


def test_served_frontend_has_social_controls(social):
    client, _, _ = social
    assert 'npcWhisper' in client.get('/js/store.js').text
    assert 'requestNpcWave' in client.get('/js/store.js').text
    chat = client.get('/js/views/chat.js').text
    assert '请 AI 角色依次发言' in chat
    assert '选队友或 AI' in chat


def test_memory_unlock_synced_from_engine(social, monkeypatch):
    client, server, _ = social
    eng = server.engines['social_test']
    eng.ms.unlock_next('char_02', 'memory_fix')
    seen = []
    from agents.npc_agent import NPCAgent
    original = NPCAgent.respond

    def capture(self, *args, **kwargs):
        seen.append(self.memory_version)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(NPCAgent, 'respond', capture)
    r = client.post('/api/session/social_test/npc-whisper', json={'to': 'char_02', 'text': '你记起来了吗'})
    assert r.status_code == 200, r.text
    assert seen == [eng.ms.current_version('char_02')]


def test_provider_failure_does_not_claim_success(social, monkeypatch):
    client, server, provider = social

    def unavailable(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr(provider, 'chat', unavailable)
    before = server.store.load_session('social_test')
    r = client.post('/api/session/social_test/npc-whisper', json={'to': 'char_02', 'text': '你好'})
    assert r.status_code == 503
    assert server.store.load_session('social_test') == before
    server.broadcast_to.assert_not_awaited()


def test_stage_prompt_and_partial_failure(social, monkeypatch):
    client, server, provider = social
    session = server.store.load_session('social_test')
    session['stage'] = 'round_table'
    server.store.save_session('social_test', session)
    from agents.npc_agent import NPCAgent
    original = NPCAgent.respond

    def partial(self, *args, **kwargs):
        if self.character['id'] == 'char_02':
            raise TimeoutError()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(NPCAgent, 'respond', partial)
    r = client.post('/api/session/social_test/npc-wave', json={})
    assert r.status_code == 200, r.text
    assert r.json()['failed_roles'] == ['char_02']
    assert r.json()['count'] == 6
    assert '围绕公开讨论表态' in str(provider.inputs)
