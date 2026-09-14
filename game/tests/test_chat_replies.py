import asyncio
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from server.main import GameServer, SCENARIO_DIR
from server.store.session_store import SessionStore
from agents.llm_client import LLMClient, Provider, MockProvider


class ReplyProvider(Provider):
    name = 'main'

    def chat(self, *args, **kwargs):
        return '我在这里，请继续提问。'


def test_player_chat_replies_and_persists_without_ui_key():
    root = Path(__file__).parent.parent / 'data' / 'test_chat' / uuid4().hex
    server = GameServer(SCENARIO_DIR)
    server.store = SessionStore(root)
    from server.engine_driver import EngineDriver
    eng = EngineDriver(SCENARIO_DIR)
    session = eng.create_session('main', 'player:1', 'chat_test')
    server.engines['chat_test'] = eng
    server.store.save_session('chat_test', session)
    llm = LLMClient(cache_dir=root / 'cache', providers={'main': ReplyProvider(), 'mock': MockProvider()})

    async def no_wave(*args):
        return []

    async def _flow(target):
        events, error = await server.run_action('chat_test', 'chat', 'player:1', {'target': target, 'text': '你好'})
        # P0-3 终版：wave 后台化 → 同一循环内等待任务完成后再断言
        task = getattr(server, '_last_wave_task', None)
        if task is not None:
            await asyncio.wait_for(task, timeout=30)
        return events, error

    with patch.object(server, '_llm_for_session', return_value=llm), \
         patch.object(server, 'run_ai_wave', no_wave), \
         patch.object(server, 'broadcast', AsyncMock()) as bmock, \
         patch.object(server, 'broadcast_to', AsyncMock()):
        for target in ('char_05', 'dm'):
            bmock.reset_mock()   # 迭代隔离：上一定向回复的主广播不进本步断言
            events, error = asyncio.run(_flow(target))
            assert error is None
            replies = [e for e in events if e['type'] == 'chat' and e['payload'].get('source') == 'agent']
            # 后台 wave 产物经逐席广播通道可见（AsyncMock 记录）
            wave_chats = [e for call in bmock.call_args_list
                          for e in (call.args[1] if call.args else [])
                          if e.get('type') == 'chat' and e['payload'].get('source') == 'agent']
            if target == 'dm':
                # V3.2 → 比赛模式契约演进：对 DM/全场广播 → DM 回应之外，自动
                # 社交回应全员串联接话（run_chat_respond，一席一句按序调用）。
                # chat_test 未设 booklet_roles → 8 席全部为 AI 空席。
                # 2026-09-14 P0-3 终版：社交波后台化，产物走广播通道。
                dm_reply = [e for e in replies if e['payload'].get('char_id') == 'dm']
                npc_replies = [e for e in wave_chats if e['payload'].get('char_id') != 'dm']
                assert len(dm_reply) == 1
                assert len(npc_replies) == 8
                assert all(e['payload'].get('wave') for e in npc_replies)
            else:
                # 定向对具体 NPC：保持引擎定向回应契约，恰好 1 条（不再触发 wave）
                assert len(replies) == 1
                assert replies[0]['payload']['char_id'] == target
            assert all(e in server.store.load_session('chat_test')['events'] for e in replies)
            assert not any(e['payload'].get('event') == 'npc_pending' for e in events)

    with patch.object(server, '_llm_for_session', return_value=None), patch.object(server, 'run_ai_wave', no_wave):
        events, _ = asyncio.run(server.run_action('chat_test', 'chat', 'player:1', {'target': 'char_05', 'text': '再问一次'}))
        assert any(e['payload'].get('event') == 'ai_reply_failed' for e in events)


def test_provider_failure_is_not_cached():
    class FailsOnce(ReplyProvider):
        calls = 0

        def chat(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError()
            return super().chat(*args, **kwargs)

    provider = FailsOnce()
    root = Path(__file__).parent.parent / 'data' / 'test_chat' / uuid4().hex
    llm = LLMClient(cache_dir=root, providers={'main': provider})
    messages = [{'role': 'user', 'content': 'hello'}]
    llm.chat(messages)
    assert llm.last_provider == 'fallback' and llm.last_error
    assert llm.chat(messages) == '我在这里，请继续提问。'
    assert provider.calls == 2 and not llm.last_error
