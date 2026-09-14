from server.ai_status import describe_ai


def test_configuration_is_not_live_success():
    result = describe_ai({}, {'llm_key': 'SECRET', 'llm_base': 'https://example.org/v1', 'llm_model': 'm'})
    assert result['state'] == 'configured'
    assert 'SECRET' not in str(result)


def test_zhihu_default_and_missing():
    assert describe_ai({})['state'] == 'missing'
    assert describe_ai({'ZHIHU_ACCESS_SECRET': 'SECRET'})['npc_provider'] == '知乎直答'


def test_latest_failure_overrides_previous_success():
    events = [{'type': 'chat', 'payload': {'source': 'agent', 'provider': 'main'}},
              {'type': 'system', 'payload': {'event': 'ai_reply_failed'}}]
    assert describe_ai({}, session={'events': events})['state'] == 'failed'
    assert describe_ai({}, session={'events': events[:1]})['state'] == 'success'


def test_cache_is_not_a_live_call():
    event = {'type': 'chat', 'payload': {'source': 'agent', 'provider': 'main(cache)'}}
    assert describe_ai({}, session={'events': [event]})['state'] == 'cache'


def test_seat_diagnostics_do_not_expose_secrets():
    session = {'ai_state': {'char_01': {'goal': 'SECRET'}},
               'seats': [{'char_id': 'char_01', 'is_ai': True, 'ai_takeover': True, 'faction': 'SECRET'}]}
    out = describe_ai({}, session=session)
    assert out['seats'] == [{'char_id': 'char_01', 'controller': 'AI 接管'}]
    assert 'SECRET' not in str(out)


def test_mock_session_is_labelled():
    assert describe_ai({}, session={'engine': 'mock'})['state'] == 'offline_demo'
