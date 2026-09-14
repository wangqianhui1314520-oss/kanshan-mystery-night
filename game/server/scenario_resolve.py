"""scenario_id → 剧本目录解析与建局校验（S2 服务端）。"""
from __future__ import annotations

from pathlib import Path
import json

_SCENARIOS = Path(__file__).resolve().parent.parent / "content" / "scenarios"

try:
    from studio import load_job
    from studio.paths import scenario_dir
except Exception:  # studio 并发编辑时不拖垮看山建局
    def scenario_dir(scenario_id: str) -> Path:  # type: ignore[misc]
        sid = str(scenario_id or "").strip()
        if not sid or "/" in sid or "\\" in sid or ".." in sid:
            raise ValueError("非法 scenario_id")
        return _SCENARIOS / sid

    def load_job(scenario_id: str) -> dict:  # type: ignore[misc]
        raise FileNotFoundError(scenario_id)

PLAYABLE_ALIASES = frozenset({"kanshan", "template"})


def audit_playability(path: Path) -> tuple[bool, list[str]]:
    """对生成剧本做轻量结构审计；不替代内容审核，只拦截明显不可玩的包。"""
    errors: list[str] = []
    try:
        scenario = json.loads((path / "scenario.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"scenario.json 无法解析：{type(exc).__name__}"]
    if not scenario.get("title"):
        errors.append("缺少剧本标题")
    acts = scenario.get("acts") or []
    if len(acts) < 2:
        errors.append("至少需要 2 个幕次")
    chars = list((path / "characters").glob("*.json")) if (path / "characters").is_dir() else []
    clues = list((path / "clues").glob("*.json")) if (path / "clues").is_dir() else []
    if len(chars) < 2:
        errors.append("角色数量不足（至少 2 名）")
    if len(clues) < 3:
        errors.append("线索数量不足（至少 3 条）")
    for required in ("truth.json", "timeline.json"):
        if not (path / required).is_file():
            errors.append(f"缺少 {required}")
    return not errors, errors


def resolve_session_scenario_dir(scenario_id: str | None) -> Path:
    """按 session 的 scenario_id 解析引擎装载目录（kanshan/template → kanshan）。"""
    sid = (scenario_id or "kanshan").strip() or "kanshan"
    if sid in PLAYABLE_ALIASES:
        return scenario_dir("kanshan")
    return scenario_dir(sid)


def validate_scenario_for_session(scenario_id: str | None) -> tuple[str, Path]:
    """校验 scenario_id 可开玩；返回 (持久化 id, 引擎目录)。非法 → ValueError。"""
    sid = (scenario_id or "kanshan").strip() or "kanshan"

    if sid in PLAYABLE_ALIASES:
        path = scenario_dir("kanshan")
        if not (path / "scenario.json").is_file():
            raise ValueError("剧本目录不存在或缺少 scenario.json：kanshan")
        return sid, path

    if sid.startswith("gen_"):
        path = scenario_dir(sid)
        if not path.is_dir() or not (path / "scenario.json").is_file():
            raise ValueError(f"剧本目录不存在或缺少 scenario.json：{sid}")
        try:
            job = load_job(sid)
        except FileNotFoundError as e:
            raise ValueError(f"剧本 job 不存在：{sid}") from e
        if job.get("status") != "ready":
            raise ValueError(
                f"剧本尚未就绪（status={job.get('status')}，需 ready 且 gate.ok）")
        if not (job.get("gate") or {}).get("ok"):
            raise ValueError("剧本闸门未通过（gate.ok=false），不可开玩")
        ok, errors = audit_playability(path)
        if not ok:
            raise ValueError("剧本结构审计未通过：" + "；".join(errors))
        return sid, path

    path = scenario_dir(sid)
    if path.is_dir() and (path / "scenario.json").is_file():
        raise ValueError(f"非法或不可玩 scenario_id：{sid}（仅 kanshan/template/gen_*）")

    raise ValueError(f"剧本目录不存在或缺少 scenario.json：{sid}")
