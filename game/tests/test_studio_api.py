"""Pipeline 全链路 API 验收：generate(202 后台任务) → catalog → jobs → 建局。

零网络零凭证：conftest autouse 已清 AI 凭证（ZHIHU_*/LLM_*）；generate 走
mock 快速出包（tier=demo, use_llm=False），真实落盘 content/scenarios/gen_*
（允许：id 由 title+seed 确定性导出，重跑覆盖同一目录，不堆积）。
"""
from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from server.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
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
