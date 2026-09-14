"""剧本目录解析。kanshan/template 只读。"""

from __future__ import annotations

from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = GAME_ROOT / "content" / "scenarios"
KANSHAN = SCENARIOS / "kanshan"
BLACKLIST = frozenset({"kanshan", "template"})


def scenario_dir(scenario_id: str) -> Path:
    sid = str(scenario_id or "").strip()
    if not sid or "/" in sid or "\\" in sid or ".." in sid:
        raise ValueError("非法 scenario_id")
    return SCENARIOS / sid


def assert_writable(scenario_id: str) -> Path:
    sid = str(scenario_id or "").strip()
    if sid in BLACKLIST:
        raise ValueError("BLACKLIST: 拒绝写入 kanshan/template")
    if not sid.startswith("gen_"):
        raise ValueError("只许写入 gen_* 目录")
    path = scenario_dir(sid)
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(scenario_id: str) -> Path:
    return scenario_dir(scenario_id) / "_studio" / "job.json"
