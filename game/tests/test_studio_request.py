"""跨平台 Studio CLI 回归：JSON、直连、轮询和错误提示。"""
from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "studio_request.py"
_spec = importlib.util.spec_from_file_location("studio_request", MODULE_PATH)
assert _spec and _spec.loader
studio_request = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(studio_request)


class _Response:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


class _Opener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


def test_client_uses_direct_opener_and_utf8_json():
    client = studio_request.StudioClient("http://127.0.0.1:8899", timeout=7)
    proxy_handlers = [
        h for h in client.opener.handlers
        if isinstance(h, studio_request.urllib.request.ProxyHandler)
    ]
    # build_opener omits the default ProxyHandler when an empty one is passed;
    # either representation must mean that no proxy can be inherited.
    assert proxy_handlers == []

    opener = _Opener(_Response(b'{"ok":true}'))
    client.opener = opener
    status, body = client.request(
        "POST",
        "/api/studio/generate",
        {"seed": "中文\"嵌套\"", "brief": {"hook": "第一行\n第二行"}},
    )

    assert status == 200
    assert body == {"ok": True}
    request, timeout = opener.requests[0]
    assert timeout == 7
    assert request.get_header("Content-type") == "application/json"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload == {"seed": "中文\"嵌套\"", "brief": {"hook": "第一行\n第二行"}}


def test_wait_job_polls_running_then_ready(monkeypatch):
    client = studio_request.StudioClient("http://127.0.0.1:8899")
    responses = iter([
        (200, {"ok": True, "job": {"status": "running"}}),
        (200, {"ok": True, "job": {"status": "ready", "id": "gen_demo"}}),
    ])
    calls = []

    def request(method, path, payload=None):
        calls.append((method, path, payload))
        return next(responses)

    monkeypatch.setattr(client, "request", request)
    monkeypatch.setattr(studio_request.time, "sleep", lambda _seconds: None)
    job = client.wait_job("job/with space", timeout=1, interval=0)

    assert job == {"status": "ready", "id": "gen_demo"}
    assert len(calls) == 2
    assert calls[0][0] == "GET"
    assert calls[0][1].endswith("job%2Fwith%20space")


def test_run_generate_posts_then_waits(monkeypatch):
    accepted = {
        "ok": True,
        "job_id": "job_abc",
        "status": "running",
    }
    ready = {"id": "gen_demo", "status": "ready", "gate": {"ok": True}}
    calls = []

    class FakeClient:
        def __init__(self, base, timeout):
            calls.append(("init", base, timeout))

        def request(self, method, path, payload=None):
            calls.append((method, path, payload))
            return 202, accepted

        def wait_job(self, job_id, timeout, interval):
            calls.append(("wait", job_id, timeout, interval))
            return ready

    monkeypatch.setattr(studio_request, "StudioClient", FakeClient)
    args = studio_request._parser().parse_args([
        "--base", "http://127.0.0.1:8899",
        "--timeout", "3",
        "generate",
        "--seed", "中文种子\"带引号\"",
        "--wait-timeout", "12",
        "--interval", "0.2",
    ])

    result = studio_request._run(args)

    assert result == {"ok": True, "job": ready}
    assert calls[1] == (
        "POST", "/api/studio/generate",
        {"seed": "中文种子\"带引号\"", "tier": "demo",
         "use_llm": False, "inner_boss": False},
    )
    assert calls[2] == ("wait", "job_abc", 12.0, 0.2)


def test_request_reports_http_error():
    client = studio_request.StudioClient("http://127.0.0.1:8899")
    client.opener = _Opener(error=urllib.error.HTTPError(
        url="http://127.0.0.1:8899/api/studio/generate",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=None,
    ))
    # HTTPError stores the stream in both `fp` and `file` on Python 3.14.
    body = _BodyReader('{"detail":"seed 不能为空"}'.encode("utf-8"))
    client.opener.error.fp = body
    client.opener.error.file = body

    with pytest.raises(studio_request.StudioRequestError, match=r"HTTP 400.*seed 不能为空"):
        client.request("POST", "/api/studio/generate", {"seed": ""})


def test_request_reports_connection_and_timeout_errors():
    client = studio_request.StudioClient("http://127.0.0.1:8899", timeout=0.5)
    client.opener = _Opener(error=urllib.error.URLError("connection refused"))
    with pytest.raises(studio_request.StudioRequestError, match="无法连接"):
        client.request("GET", "/api/studio/catalog")

    client.opener = _Opener(error=TimeoutError())
    with pytest.raises(studio_request.StudioRequestError, match=r"请求超时（0\.5s）"):
        client.request("GET", "/api/studio/catalog")


class _BodyReader:
    def __init__(self, body: bytes):
        self.body = body

    def read(self, _size=-1):
        return self.body
