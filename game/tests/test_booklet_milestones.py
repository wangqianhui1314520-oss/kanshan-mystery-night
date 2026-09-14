import json

from engine.booklet import load_library


def test_goals_reach_private_pack_and_agent_without_future_chapters(scenario_dir):
    lib = load_library(scenario_dir)
    for role in lib.roles:
        for chapter in (1, 2, 3):
            pack = lib.visible_pack(role, chapter)
            assert list(pack['covers']) == list('ABC'[:chapter])
            current = pack['covers']['ABC'[chapter - 1]]
            assert len(current['milestones']) >= 2
            prompt = lib.agent_prompt(role, chapter)
            assert all(goal in prompt for goal in current['milestones'])


def test_editing_booklet_refreshes_library_cache(tmp_path):
    directory = tmp_path / 'booklets'
    directory.mkdir()
    path = directory / 'investigator.json'
    data = {'id': 'investigator', 'covers': {'A': {'milestones': ['first']}}}
    path.write_text(json.dumps(data), encoding='utf-8')
    assert load_library(tmp_path).roles['investigator']['covers']['A']['milestones'] == ['first']
    data['covers']['A']['milestones'] = ['revised goal']
    path.write_text(json.dumps(data), encoding='utf-8')
    assert load_library(tmp_path).roles['investigator']['covers']['A']['milestones'] == ['revised goal']
