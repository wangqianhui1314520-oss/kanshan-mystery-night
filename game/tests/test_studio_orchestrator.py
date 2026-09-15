"""IR 与生成编排器的确定性契约回归测试。"""
from __future__ import annotations

import json

import pytest

from studio.ir import ScriptPackage, stable_hash
from studio.orchestrator import (
    can_start,
    create_state,
    lock_stage,
    record_failure,
    record_success,
    start,
    unlock_stage,
)


def test_stable_hash_is_independent_of_dict_order():
    left = {"b": [2, {"z": 1, "a": 0}], "a": "文本"}
    right = {"a": "文本", "b": [2, {"a": 0, "z": 1}]}

    assert stable_hash(left) == stable_hash(right)
    assert stable_hash(left) != stable_hash({**left, "extra": True})


def test_legacy_job_round_trip_preserves_old_fields():
    old_job = {
        "id": "gen_legacy_case",
        "status": "ready",
        "tier": "demo",
        "seed": {"text": "一句话种子"},
        "world": {"title": "旧剧本", "locations": [{"name": "现场"}]},
        "detail": {"characters": [{"id": "char_01"}]},
        "acts": {"acts": [{"id": "act1"}]},
        "gate": {"ok": True, "errors": [], "warnings": []},
        "provider": "mock",
        "scenario_dir": "content/scenarios/gen_legacy_case",
        "created_at": "2026-09-15T00:00:00+00:00",
    }

    package = ScriptPackage.from_job(old_job)
    legacy = package.to_legacy_job()

    for key, value in old_job.items():
        assert legacy[key] == value, key
    assert legacy["id"] == package.id
    assert legacy["generation"]["draft_id"] == old_job["id"]


def test_generation_four_stages_follow_truth_cast_acts_assemble_dependencies():
    state = create_state("draft_contract")

    assert can_start(state, "truth")
    assert not can_start(state, "cast")
    assert not can_start(state, "acts")
    assert not can_start(state, "assemble")

    for stage, output in (
        ("truth", {"title": "真相"}),
        ("cast", {"characters": ["char_01", "char_02", "char_03", "char_04"]}),
        ("acts", {"acts": ["act1", "act2", "act3"]}),
        ("assemble", {"scenario_id": "gen_contract"}),
    ):
        start(state, stage, {"input": stage})
        record_success(state, stage, output)
        if stage != "assemble":
            assert state.stage_states[stage].status == "awaiting_human"
            lock_stage(state, stage)
        else:
            assert state.stage_states[stage].status == "succeeded"
            lock_stage(state, stage)

        following = {
            "truth": "cast",
            "cast": "acts",
            "acts": "assemble",
        }.get(stage)
        if following:
            assert can_start(state, following), following

    assert state.status == "succeeded"
    assert state.current_stage is None


def test_failed_stage_can_retry_until_max_retries_then_cannot_start():
    state = create_state("draft_retries", max_retries=2)

    start(state, "truth", {"attempt": 0})
    record_failure(state, "truth", "暂时网络错误")
    assert can_start(state, "truth")
    assert state.stage_states["truth"].retry == 0

    start(state, "truth", {"attempt": 1})
    record_failure(state, "truth", "再次失败")
    assert can_start(state, "truth")
    assert state.stage_states["truth"].retry == 1

    start(state, "truth", {"attempt": 2})
    record_failure(state, "truth", "达到重试上限")
    assert state.stage_states["truth"].retry == 2
    assert not can_start(state, "truth")
    assert state.stage_states["truth"].status == "failed"


def test_lock_stage_keeps_downstream_runnable():
    state = create_state("draft_lock")
    start(state, "truth", {"seed": "x"})
    record_success(state, "truth", {"title": "锁定真相"})
    lock_stage(state, "truth")

    assert state.stage_states["truth"].locked
    assert state.stage_states["truth"].status == "succeeded"
    assert can_start(state, "cast")


def test_unlock_stage_blocks_descendants_and_clears_output_hashes():
    state = create_state("draft_unlock")
    for stage in ("truth", "cast", "acts", "assemble"):
        start(state, stage, {"input": stage})
        record_success(state, stage, {"output": stage})
        lock_stage(state, stage)

    assert all(state.stage_states[name].locked for name in ("truth", "cast", "acts", "assemble"))
    unlock_stage(state, "truth")

    assert state.stage_states["truth"].status == "pending"
    assert state.stage_states["truth"].output_hash is None
    for stage in ("cast", "acts", "assemble"):
        current = state.stage_states[stage]
        assert current.status == "blocked", stage
        assert current.output_hash is None, stage
        assert not current.locked, stage
    assert not can_start(state, "cast")


def _metadata_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key).lower()
            yield from _metadata_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _metadata_keys(item)


def test_generation_state_preserves_explicit_terminal_current_stage():
    state = create_state("draft_terminal")
    raw = state.to_dict()
    raw["status"] = "succeeded"
    raw["current_stage"] = None
    restored = create_state("draft_unused")
    from studio.orchestrator import from_dict
    restored = from_dict(raw)
    assert restored.current_stage is None
    assert restored.status == "succeeded"


def test_private_metadata_is_removed_from_ir_projection():
    package = ScriptPackage.from_job({
        "id": "gen_private_metadata",
        "status": "ready",
        "world": {"title": "公开标题"},
        "agents": {
            "provider": "mock",
            "prompt": "原始 prompt 不应进入元数据",
            "inner_truth": "隐藏真相",
            "nested": {"guilt": "罪责", "secret": "秘密"},
        },
        "locks": {"prompt": "系统 prompt", "stage": "truth"},
        "provenance": {"secret": "token", "source": "preset"},
        "validation": {"ok": True, "details": {"guilt": "private"}},
    })
    legacy = package.to_legacy_job()
    metadata = {
        key: legacy[key]
        for key in ("agents", "locks", "provenance", "validation")
    }

    private = {"inner_truth", "guilt", "secret", "prompt"}
    assert not (private & set(_metadata_keys(metadata)))
    assert "公开标题" in json.dumps(legacy["world"], ensure_ascii=False)


def test_staged_truth_cast_acts_wait_for_human_lock_and_unlock_downstream(tmp_path, monkeypatch):
    import studio.staged as staged

    monkeypatch.setattr(staged, "DRAFTS", tmp_path / "drafts")
    draft = staged.create_draft("四人密室的一句话谜案", None)

    draft = staged.stage_truth(draft)
    assert draft["generation"]["stage_states"]["truth"]["status"] == "awaiting_human"
    with pytest.raises(RuntimeError, match="前置阶段"):
        staged.stage_cast(draft)

    staged.lock_draft_stage(draft, "truth")
    draft = staged.stage_cast(draft)
    assert draft["generation"]["stage_states"]["cast"]["status"] == "awaiting_human"
    staged.lock_draft_stage(draft, "cast")

    draft = staged.stage_acts(draft)
    assert draft["generation"]["stage_states"]["acts"]["status"] == "awaiting_human"
    staged.lock_draft_stage(draft, "acts")
    assert staged._generation_for_draft(draft).stage_states["acts"].locked


def test_staged_lock_rejects_missing_or_failed_output_and_updates_edit_hash(tmp_path, monkeypatch):
    import studio.staged as staged

    monkeypatch.setattr(staged, "DRAFTS", tmp_path / "drafts")
    draft = staged.create_draft("锁定错误状态回归", None)
    with pytest.raises(ValueError, match="尚无可锁定产物"):
        staged.lock_draft_stage(draft, "truth")

    draft = staged.stage_truth(draft)
    original_hash = draft["generation"]["stage_states"]["truth"]["output_hash"]
    edited = dict(draft["world"])
    edited["title"] = "作者编辑后的标题"
    staged.lock_draft_stage(draft, "truth", output=edited)
    current = staged._generation_for_draft(draft).stage_states["truth"]
    assert current.locked
    assert current.output_hash == stable_hash(edited)
    assert current.output_hash != original_hash
    with pytest.raises(RuntimeError, match="必须先解锁"):
        staged.lock_draft_stage(draft, "truth", output={"title": "二次静默覆盖"})
    staged.unlock_draft_stage(draft, "truth")
    edited_again = dict(draft["world"])
    edited_again["title"] = "解锁后重新编辑"
    staged.lock_draft_stage(draft, "truth", output=edited_again)
    current = staged._generation_for_draft(draft).stage_states["truth"]
    assert current.output_hash == stable_hash(edited_again)
    assert current.status == "succeeded"

    failed = staged.create_draft("失败状态不可锁", None)
    failed["generation"]["stage_states"]["truth"]["status"] = "failed"
    failed["world"] = {"title": "失败产物"}
    with pytest.raises(RuntimeError, match="尚未生成成功"):
        staged.lock_draft_stage(failed, "truth")


def test_staged_assemble_requires_all_locks_and_job_exposes_metadata(tmp_path, monkeypatch):
    import studio.staged as staged

    # 编译器会清理同一确定性 scenario_id 的旧目录；测试只验证编排/元数据，
    # 因此替换 IO 边界，避免触发环境的批量删除保护。
    monkeypatch.setattr(staged, "compile_bibles", lambda *args, **kwargs: None)
    monkeypatch.setattr(staged, "build_books", lambda *args, **kwargs: {})
    monkeypatch.setattr(staged, "validate_dir", lambda *args, **kwargs: {
        "ok": True, "errors": [], "warnings": []
    })
    monkeypatch.setattr(staged, "DRAFTS", tmp_path / "drafts")
    draft = staged.create_draft("四人剧本编译元数据", None)
    draft = staged.stage_truth(draft)
    with pytest.raises(RuntimeError, match="未锁定"):
        staged.assemble(draft, draft["world"], {"characters": []}, {"acts": []})

    staged.lock_draft_stage(draft, "truth")
    draft = staged.stage_cast(draft)
    staged.lock_draft_stage(draft, "cast")
    draft = staged.stage_acts(draft)
    staged.lock_draft_stage(draft, "acts")
    job = staged.assemble(draft, draft["world"], draft["detail"], draft["acts"])

    assert job["generation"]["stage_states"]["assemble"]["status"] == "succeeded"
    assert job["generation"]["stage_states"]["assemble"]["locked_at"]
    for key in ("generation", "agents", "locks", "provenance", "validation"):
        assert key in job
    assert "assemble" in job["locks"]


def test_staged_downstream_rejects_tampered_locked_upstream(tmp_path, monkeypatch):
    import studio.staged as staged

    monkeypatch.setattr(staged, "DRAFTS", tmp_path / "drafts")
    draft = staged.create_draft("下游输入哈希回归", None)
    draft = staged.stage_truth(draft)
    staged.lock_draft_stage(draft, "truth")
    tampered = dict(draft["world"])
    tampered["title"] = "未重新锁定的上游"
    with pytest.raises(RuntimeError, match="偏离锁定版本"):
        staged.stage_cast(draft, tampered)


def test_staged_assemble_rejects_locked_hash_tampering(tmp_path, monkeypatch):
    import studio.staged as staged

    monkeypatch.setattr(staged, "DRAFTS", tmp_path / "drafts")
    draft = staged.create_draft("锁定哈希篡改回归", None)
    draft = staged.stage_truth(draft)
    staged.lock_draft_stage(draft, "truth")
    draft = staged.stage_cast(draft)
    staged.lock_draft_stage(draft, "cast")
    draft = staged.stage_acts(draft)
    staged.lock_draft_stage(draft, "acts")

    tampered_world = dict(draft["world"])
    tampered_world["title"] = "未重新锁定的篡改标题"
    with pytest.raises(RuntimeError, match="hash|锁定|篡改"):
        staged.assemble(draft, tampered_world, draft["detail"], draft["acts"])
