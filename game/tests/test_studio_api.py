"""Pipeline 全链路 API 验收：generate(202 后台任务) → catalog → jobs → 建局。

零网络零凭证：conftest autouse 已清 AI 凭证（ZHIHU_*/LLM_*）；generate 走
mock 快速出包（tier=demo, use_llm=False），真实落盘 content/scenarios/gen_*
（允许：id 由 title+seed 确定性导出，重跑覆盖同一目录，不堆积）。
"""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("fastapi")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from server.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def generated_scenario(client) -> str:
    """落盘一个 mock 快本包，轮询 jobs 到终态，返回 scenario_id。"""
    resp = client.post("/api/studio/generate", json={
        "seed": "api测试：热搜日志缺了七分钟", "tier": "demo",
        "use_llm": False, "zhihu": {"refs": ["topic:demo"]},
    })
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("status") == "running"
    job_id = body["job_id"]
    deadline = time.time() + 90
    job: dict = {}
    while time.time() < deadline:
        r = client.get(f"/api/studio/jobs/{job_id}")
        assert r.status_code == 200, r.text
        job = r.json()["job"]
        if job.get("status") in ("ready", "failed"):
            break
        time.sleep(0.3)
    assert job.get("status") == "ready", job
    assert (job.get("gate") or {}).get("ok") is True
    assert job.get("scenario_id") == job.get("id")
    # zhihu 参数本版本只透传占位
    assert job.get("zhihu_refs") == {"refs": ["topic:demo"]}
    sid = job.get("id") or ""
    assert sid.startswith("gen_"), sid
    return sid


def test_generate_rejects_empty_seed(client):
    r = client.post("/api/studio/generate", json={"seed": "  "})
    assert r.status_code == 400


def test_generate_rejects_bad_tier(client):
    r = client.post("/api/studio/generate", json={"seed": "x", "tier": "mega"})
    assert r.status_code == 400
    assert "tier" in r.json()["detail"]


def test_jobs_unknown_404(client):
    r = client.get("/api/studio/jobs/job_does_not_exist")
    assert r.status_code == 404


def test_generate_202_and_job_ready(client, generated_scenario):
    assert generated_scenario.startswith("gen_")


def test_catalog_contains_generated(client, generated_scenario):
    r = client.get("/api/studio/catalog")
    assert r.status_code == 200
    items = r.json().get("items") or []
    match = [it for it in items if it.get("scenario_id") == generated_scenario]
    assert match, generated_scenario
    it = match[0]
    assert it.get("status") == "ready"
    assert it.get("title")
    assert all(str(x["scenario_id"]).startswith("gen_") for x in items)


def test_session_with_generated_scenario(client, generated_scenario):
    r = client.post("/api/session", json={
        "mode": "quick", "player_id": "player:1",
        "scenario_id": generated_scenario,
    })
    if r.status_code == 503:
        pytest.skip("真实引擎未就绪（TestClient 环境常见）")
    assert r.status_code == 200, r.text
    session = (r.json() or {}).get("session") or {}
    assert session.get("scenario_id") == generated_scenario
    assert session.get("session_id")


def _create_staged_draft(client, seed="API 阶段锁定回归"):
    response = client.post("/api/studio/draft", json={"seed": seed})
    assert response.status_code == 200, response.text
    return response.json()["draft_id"]


def test_staged_lock_api_rejects_ungenerated_stage_and_updates_edited_hash(client):
    draft_id = _create_staged_draft(client, "API 锁定错误状态与编辑哈希")

    before = client.post(
        f"/api/studio/draft/{draft_id}/stage/truth/lock", json={})
    assert before.status_code == 409, before.text

    generated = client.post(
        f"/api/studio/draft/{draft_id}/stage/truth", json={"use_llm": False})
    assert generated.status_code == 200, generated.text
    body = generated.json()
    old_hash = body["generation"]["stage_states"]["truth"]["output_hash"]
    edited = dict(body["world"])
    edited["title"] = "API 编辑后的真相标题"

    locked = client.post(
        f"/api/studio/draft/{draft_id}/stage/truth/lock",
        json={"output": edited},
    )
    assert locked.status_code == 200, locked.text
    state = locked.json()["generation"]["stage_states"]["truth"]
    assert state["status"] == "succeeded"
    assert state["locked_at"]
    assert state["output_hash"] != old_hash


def test_staged_api_sequence_and_assemble_metadata(client, monkeypatch):
    import studio.staged as staged

    # 本用例验证 API 编排契约；隔离编译器/落盘清理，避免测试运行时触发
    # 编译同一确定性 scenario_id 的批量删除保护。
    monkeypatch.setattr(staged, "compile_bibles", lambda *args, **kwargs: None)
    monkeypatch.setattr(staged, "build_books", lambda *args, **kwargs: {})
    monkeypatch.setattr(staged, "validate_dir", lambda *args, **kwargs: {
        "ok": True, "errors": [], "warnings": []
    })
    draft_id = _create_staged_draft(client, "API 四阶段编译元数据")
    truth = client.post(
        f"/api/studio/draft/{draft_id}/stage/truth", json={"use_llm": False})
    assert truth.status_code == 200, truth.text
    assert truth.json()["generation"]["stage_states"]["truth"]["status"] == "awaiting_human"
    assert client.post(
        f"/api/studio/draft/{draft_id}/stage/truth/lock", json={}).status_code == 200

    cast = client.post(
        f"/api/studio/draft/{draft_id}/stage/cast", json={"use_llm": False})
    assert cast.status_code == 200, cast.text
    assert cast.json()["generation"]["stage_states"]["cast"]["status"] == "awaiting_human"
    assert client.post(
        f"/api/studio/draft/{draft_id}/stage/cast/lock", json={}).status_code == 200

    acts = client.post(
        f"/api/studio/draft/{draft_id}/stage/acts", json={"use_llm": False})
    assert acts.status_code == 200, acts.text
    assert acts.json()["generation"]["stage_states"]["acts"]["status"] == "awaiting_human"
    assert client.post(
        f"/api/studio/draft/{draft_id}/stage/acts/lock", json={}).status_code == 200

    assembled = client.post(
        f"/api/studio/draft/{draft_id}/assemble",
        json={"world": truth.json()["world"],
              "detail": cast.json()["detail"],
              "acts": acts.json()["acts"]})
    assert assembled.status_code == 200, assembled.text
    body = assembled.json()
    job = body["job"]
    assert job["generation"]["stage_states"]["assemble"]["locked_at"]
    assert job["generation"]["stage_states"]["assemble"]["status"] == "succeeded"
    for key in ("generation", "agents", "locks", "provenance", "validation"):
        assert key in job
    assert "assemble" in job["locks"]


def test_party_session_with_scenario_is_publicly_sanitized(client):
    response = client.post("/api/session", json={
        "mode": "party", "player_id": "player:api-party",
        "scenario_id": "kanshan",
    })
    if response.status_code == 503:
        pytest.skip("真实引擎未就绪（TestClient 环境常见）")
    assert response.status_code == 200, response.text
    body = response.json()
    session = body["session"]
    assert session["mode"] == "party"
    assert session["scenario_id"] == "kanshan"
    assert isinstance(session.get("room_code"), str) and len(session["room_code"]) == 6
    public_text = json.dumps(session, ensure_ascii=False).lower()
    for forbidden in ("faction", "guilt", "inner_truth", "secret"):
        assert forbidden not in public_text, forbidden
    assert "party" not in session
