from pathlib import Path

from server.engine_driver import EngineDriver
from engine.opinion_feed import OpinionFeed


def test_search_feedback_carries_actor_hint_and_environment():
    driver = EngineDriver(Path(__file__).resolve().parents[1] / 'content/scenarios/kanshan')
    session = {'session_id': 'feedback-test', 'round': 2}
    events = driver._do_search(session, 'player:test', {'location': '前台', 'keyword': '不存在的物品'})
    feedback = next(e for e in events if e['type'] == 'search_result')
    assert feedback['actor'] == 'player:test'
    assert feedback['payload']['hit'] is False
    assert feedback['payload']['ambient']
    assert feedback['payload']['hint']['keywords']
    assert any(e['type'] == 'clue_gained' for e in events)


def test_unverified_post_signals_do_not_reveal_truth():
    feed = OpinionFeed()
    real = {'id': 'real', 'heat_delta': 5, 'is_fake': False}
    fake = {**real, 'id': 'fake', 'is_fake': True}
    assert feed._display(real)['signals'] == feed._display(fake)['signals']
    assert feed._display(fake)['signals']['credibility'] is None


def test_hotfeed_event_carries_panel_and_signals():
    driver = EngineDriver(Path(__file__).resolve().parents[1] / 'content/scenarios/kanshan')
    payload = driver._hotfeed_event('feedback-test', 2)['payload']
    assert payload['panel']
    assert set(payload['signals']) == {'exposure', 'credibility', 'emotion'}
    assert all(0 <= value <= 100 for value in payload['signals'].values())
