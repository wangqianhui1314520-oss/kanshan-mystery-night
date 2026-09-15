"""Cross-platform client for the Studio HTTP API.

This helper deliberately builds JSON with Python and uses a direct urllib opener.
It avoids Windows cmd/PowerShell quote parsing and local system proxy surprises.

Examples:
    python tools/studio_request.py generate --seed "深夜自习室，所有课本一夜之间变成空白"
    python tools/studio_request.py catalog
    python tools/studio_request.py job gen_pack_xxx
    python tools/studio_request.py public gen_pack_xxx
    python tools/studio_request.py session --scenario-id gen_pack_xxx --mode quick
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:8899"


class StudioRequestError(RuntimeError):
    """An HTTP or response-format error from the local Studio server."""


class StudioClient:
    def __init__(self, base: str, timeout: float = 15.0) -> None:
        self.base = str(base or DEFAULT_BASE).rstrip("/")
        self.timeout = float(timeout)
        # Never inherit the Windows system proxy for a local development API.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers=headers,
            method=method.upper(),
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return int(response.status), self._decode(response.read())
        except urllib.error.HTTPError as exc:
            body = self._decode(exc.read())
            detail = body.get("detail") or body.get("message") or body
            raise StudioRequestError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise StudioRequestError(f"无法连接 {self.base}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise StudioRequestError(f"请求超时（{self.timeout:g}s）: {self.base + path}") from exc

    @staticmethod
    def _decode(raw: bytes) -> dict[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StudioRequestError(f"服务端返回的不是合法 JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise StudioRequestError("服务端返回体必须是 JSON 对象")
        return value

    def wait_job(
        self,
        job_id: str,
        timeout: float = 90.0,
        interval: float = 1.5,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, float(timeout))
        while time.monotonic() < deadline:
            _, body = self.request("GET", "/api/studio/jobs/" + urllib.parse.quote(job_id, safe=""))
            job = body.get("job") if isinstance(body.get("job"), dict) else body
            if job.get("status") in {"ready", "failed"}:
                return job
            time.sleep(max(0.05, float(interval)))
        raise StudioRequestError(f"生成任务轮询超时（{timeout:g}s）: {job_id}")


def _scenario_path(value: str) -> str:
    from urllib.parse import quote

    return quote(str(value or "").strip(), safe="")


def _read_json_file(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioRequestError(f"无法读取 JSON 文件 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StudioRequestError(f"JSON 文件 {path} 顶层必须是对象")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="跨平台访问求真档案局生产工作台 API")
    parser.add_argument("--base", default=DEFAULT_BASE, help="服务地址，默认直连 127.0.0.1:8899")
    parser.add_argument("--timeout", type=float, default=15.0, help="单次 HTTP 超时秒数")
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate", help="生成剧本并等待终态")
    generate.add_argument("--seed", required=True, help="一句话种子")
    generate.add_argument("--tier", default="demo")
    generate.add_argument("--use-llm", action="store_true")
    generate.add_argument("--inner-boss", action="store_true")
    generate.add_argument("--brief-file", help="可选：JSON 简报文件")
    generate.add_argument("--no-wait", action="store_true", help="只返回 202 受理结果")
    generate.add_argument("--wait-timeout", type=float, default=90.0)
    generate.add_argument("--interval", type=float, default=1.5)

    sub.add_parser("catalog", help="读取可玩剧本目录")

    for name, help_text in (("job", "读取作者 job"), ("public", "读取公开试玩包")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("scenario_id")

    session = sub.add_parser("session", help="创建对局")
    session.add_argument("--scenario-id", default="kanshan")
    session.add_argument("--mode", choices=("main", "daily", "quick", "party"), default="quick")
    session.add_argument("--player-id", default="player:studio-cli")

    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    client = StudioClient(args.base, args.timeout)
    if args.command == "generate":
        payload: dict[str, Any] = {
            "seed": args.seed,
            "tier": args.tier,
            "use_llm": bool(args.use_llm),
            "inner_boss": bool(args.inner_boss),
        }
        if args.brief_file:
            payload["brief"] = _read_json_file(args.brief_file)
        _, accepted = client.request("POST", "/api/studio/generate", payload)
        if args.no_wait or not accepted.get("job_id"):
            return accepted
        job = client.wait_job(
            str(accepted["job_id"]),
            timeout=args.wait_timeout,
            interval=args.interval,
        )
        return {"ok": job.get("status") == "ready", "job": job}
    if args.command == "catalog":
        return client.request("GET", "/api/studio/catalog")[1]
    if args.command == "job":
        return client.request("GET", "/api/studio/" + _scenario_path(args.scenario_id))[1]
    if args.command == "public":
        return client.request("GET", "/api/studio/" + _scenario_path(args.scenario_id) + "/public")[1]
    if args.command == "session":
        payload = {
            "mode": args.mode,
            "player_id": args.player_id,
            "scenario_id": args.scenario_id,
        }
        return client.request("POST", "/api/session", payload)[1]
    raise StudioRequestError(f"未知命令: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except StudioRequestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
