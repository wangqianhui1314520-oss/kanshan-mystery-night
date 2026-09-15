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
    """审计生成包的结构、证据可达性和 AI 闭卷契约。"""
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
    char_files = list((path / "characters").glob("*.json")) if (path / "characters").is_dir() else []
    clue_files = list((path / "clues").glob("*.json")) if (path / "clues").is_dir() else []
    if len(char_files) < 2:
        errors.append("角色数量不足（至少 2 名）")
    if len(clue_files) < 3:
        errors.append("线索数量不足（至少 3 条）")
    for required in ("truth.json", "timeline.json"):
        if not (path / required).is_file():
            errors.append(f"缺少 {required}")

    truth = _load_json(path / "truth.json")
    clues = {}
    for clue_path in clue_files:
        clue = _load_json(clue_path)
        if isinstance(clue, dict) and clue.get("id"):
            clues[str(clue["id"])] = clue
    truth_nodes = (truth or {}).get("truth_nodes") or []
    node_ids = {str(node.get("id")) for node in truth_nodes if isinstance(node, dict) and node.get("id")}
    linked: dict[str, set[str]] = {tid: set() for tid in node_ids}
    for cid, clue in clues.items():
        if clue.get("tier") == "fake":
            continue
        for tid in clue.get("linked_truth_nodes") or []:
            if str(tid) in linked:
                linked[str(tid)].add(cid)
    composeable = sum(1 for ids in linked.values() if len(ids) >= 3)
    if composeable < 2:
        errors.append(
            f"证据链不可玩：至少需要 2 个可合成节点（当前 {composeable}，每节点需 3 条有效线索）")
    for tid, ids in linked.items():
        if len(ids) < 3:
            errors.append(f"证据链不可玩：{tid} 有效 linked_truth_nodes={len(ids)}，需 ≥3")

    # Player books and AI books are separate schemas. Require the runtime
    # projection explicitly so a package cannot pass the author-book gate while
    # AI seats later fail with “没有这本闭卷”.
    char_ids = set()
    for char_path in char_files:
        char = _load_json(char_path)
        if isinstance(char, dict) and char.get("id"):
            char_ids.add(str(char["id"]))
    required_roles = char_ids | {"investigator"}
    booklet_dir = path / "booklets"
    if not booklet_dir.is_dir():
        errors.append("闭卷契约缺失：缺少 booklets/（runtime AI 闭卷）")
    else:
        for rid in sorted(required_roles):
            data = _load_json(booklet_dir / f"{rid}.json")
            covers = (data or {}).get("covers") if isinstance(data, dict) else None
            if not isinstance(data, dict) or str(data.get("id") or "") != rid:
                errors.append(f"闭卷契约缺失：booklets/{rid}.json 不存在或 id 不匹配")
                continue
            if not isinstance(covers, dict) or any(key not in covers for key in ("A", "B", "C")):
                errors.append(f"闭卷契约无效：{rid} 必须包含 covers A/B/C")
        public = _load_json(booklet_dir / "public.json")
        if not isinstance(public, dict) or str(public.get("id") or "") != "public":
            errors.append("闭卷契约缺失：booklets/public.json 不存在或 id 不匹配")
    return not errors, errors


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


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
