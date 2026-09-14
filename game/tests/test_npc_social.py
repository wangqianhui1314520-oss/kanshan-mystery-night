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
    # 比赛模式契约演进：取消分波/QPS 限流，单请求全员 7 席按席位顺序串联回复
    # （char_01 由真人认领；AI 可选择性沉默，本测试的确定性 provider 总是发言）。
    assert r.json()['count'] == 7
    assert r.json().get('remaining') == 0
    actors = [e['actor'] for e in events]
    assert actors == sorted(actors), "AI 应按席位顺序依次回复"
    assert all(e['payload']['wave'] for e in events)
    assert 'npc:char_01' not in {e['actor'] for e in events}
    assert '不能公开的蓝色雨伞' not in str(provider.inputs)
    # 逐席实时广播：每席成功后立刻广播单事件（串联节奏），调用次数 = 事件数
    assert server.broadcast.await_count == len(events)
    for call in server.broadcast.await_args_list:
        assert call.args[0] == 'social_test' and len(call.args[1]) == 1


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
    # 比赛模式契约：单请求全员 7 席串联，char_02 失败被跳过 → 6 成功
    assert r.json()['count'] == 6
    # V3.2 行为演进：讨论模板升级为「回应玩家发言」导向（AI 围绕聊天内容表态/质疑）
    assert '针对刚才玩家们的公开发言表态' in str(provider.inputs)


# ---------------------------------------------------------------------------
# 串联调用契约（比赛模式：一席一句、逐个 API、上下文衔接、可选沉默）
# ---------------------------------------------------------------------------

class SequenceProvider(Provider):
    """第 n 次调用返回「第n席发言」；calls 记录 (char_id, user prompt)。

    char_id 通过用户 prompt 中的「角色名」行回查（npc_social context 首段
    含扮演角色名）；silent_at 指定第几次调用返回沉默标记。"""
    name = "main"

    def __init__(self, silent_at: set[int] | None = None):
        self.inputs = []          # [(role_name, user_prompt)]
        self.n = 0
        self.silent_at = silent_at or set()

    def chat(self, system, user, **kwargs):
        self.n += 1
        import re as _re
        m = _re.search(r"扮演角色「([^」]+)」", user)
        self.inputs.append((m.group(1) if m else "", user))
        return "【沉默】" if self.n in self.silent_at else f"第{self.n}席发言"


def _wave_with(llm, server, monkeypatch, body=None):
    # 测试隔离铁律：清掉磁盘缓存（conftest 开 LLM_CACHE=1），确保 provider 真调用
    llm.cache._data = {}
    llm.cache._file = None
    monkeypatch.setattr(server, '_llm_for_session', lambda sid: llm)
    from server.npc_social import social_request
    return asyncio_run(social_request(server, 'social_test',
                                      body or {'player_id': 'player:1'}, private=False))


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


def test_serial_chain_context_includes_previous_replies(social, monkeypatch):
    """串联上下文：后手 AI 的 prompt 必须包含玩家原话与前面全部 AI 的回复。"""
    client, server, _ = social
    seq = SequenceProvider()
    out = _wave_with(LLMClient(providers={'main': seq}), server, monkeypatch,
                     body={'player_id': 'player:1', 'prompt': '昨晚十点你们在哪？'})
    assert out['count'] == 7
    users = [u for _, u in seq.inputs]
    # 第 1 席：含玩家原话，无其他 AI 回复
    assert '昨晚十点你们在哪？' in users[0]
    assert '第' not in users[0].split('玩家说')[0][-50:] or '第1席发言' not in users[0]
    # 第 2 席起：prompt 含前面每一席的回复（逐席衔接，不丢上下文）
    for i in range(1, 7):
        for j in range(i):
            assert f'第{j + 1}席发言' in users[i], \
                f"第 {i + 1} 席的上下文缺少第 {j + 1} 席的回复"
    # 事件顺序 = 席位顺序，且台词逐席递增（一席一句，无合并生成）
    actors = [e['actor'] for e in out['events']]
    assert actors == sorted(actors)
    texts = [e['payload']['text'] for e in out['events']]
    assert texts == [f'第{i}席发言' for i in range(1, 8)]


def test_optional_silence_skips_seat_without_breaking_chain(social, monkeypatch):
    """选择性回复：AI 回【沉默】标记 → 该席不出消息，其余席位照常串联。"""
    client, server, _ = social
    # 第 3 次调用（char_04）沉默
    seq = SequenceProvider(silent_at={3})
    out = _wave_with(LLMClient(providers={'main': seq}), server, monkeypatch,
                     body={'player_id': 'player:1', 'prompt': '谁最后见到看山？'})
    actors = [e['actor'] for e in out['events']]
    assert 'npc:char_04' not in actors, "沉默席位不应产出任何消息"
    assert len(actors) == 6 and out['count'] == 6
    assert 'npc:char_05' in actors, "沉默后后续席位继续按序回复"
    users = [u for _, u in seq.inputs]
    assert '第2席发言' in users[3], "沉默后第 4 席仍应带此前全部回复"
    assert '：【沉默】' not in users[3], "沉默席不应作为发言行进入其他 AI 的上下文"
