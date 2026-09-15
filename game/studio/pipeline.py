"""一键流水线：圣经 → 编译 → 闸门 → job。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import mock_bible
from .brief import apply_brief, compose_seed, normalize_brief
from .compiler import compile_bibles
from .ids import make_scenario_id
from .paths import SCENARIOS, job_path, scenario_dir
from .player_book import list_covers, load_book
from .snapshot import public_snapshot
from .tiers import TIERS
from .ir import stable_hash
from .validate import validate_dir


def generate(seed: str, *, tier: str = "demo", use_llm: bool = False,
             inner_boss: bool = False, llm=None, brief=None) -> dict:
    seed = " ".join((seed or "").split())
    brief_n = normalize_brief(brief, seed)
    if not seed:
        seed = brief_n.get("hook") or ""
    if not seed:
        raise ValueError("seed 不能为空")
    if tier not in TIERS:
        raise ValueError(f"P0 只支持 {TIERS}，收到 {tier!r}")

    inner_boss = bool(inner_boss or brief_n["modules"].get("inner_boss"))
    composed = compose_seed(brief_n) or seed

    provider = "mock"
    bibles = None
    if use_llm:
        try:
            from . import llm_steps  # noqa: WPS433
            bibles = llm_steps.generate_bibles(
                composed, tier=tier, llm=llm, inner_boss=inner_boss, brief=brief_n)
            provider = getattr(llm_steps, "LAST_PROVIDER", None) or "main"
        except Exception:  # noqa: BLE001
            bibles = None
            provider = "mock"
    if bibles is None:
        bibles = mock_bible.build(composed, inner_boss=inner_boss, brief=brief_n)
        provider = "mock"

    world, detail, acts = bibles["world"], bibles["detail"], bibles["acts"]
    apply_brief(world, detail, acts, brief_n)
    # Include the normalized brief in the deterministic id. Different pack
    # types/locations must never overwrite one another's compiled scenario.
    sid = make_scenario_id(
        world.get("title") or "pack",
        composed,
        variant=stable_hash(brief_n),
    )
    compile_bibles(world, detail, acts, scenario_id=sid)
    from .player_book import build_books
    detail["player_books"] = build_books(world, detail, acts)
    gate = validate_dir(scenario_dir(sid), tier)
    status = "ready" if gate["ok"] else "failed"
    job = {
        "id": sid,
        "status": status,
        "tier": tier,
        "seed": {
            "text": seed,
            "inner_boss": bool(inner_boss),
            "brief": brief_n,
            "composed": composed,
        },
        "modules": brief_n["modules"],
        "world": world,
        "detail": detail,
        "acts": acts,
        "gate": gate,
        "provider": provider,
        "scenario_dir": f"content/scenarios/{sid}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_job(job)
    return job


def compile_bibles_and_gate(world, detail, acts, *, scenario_id: str, tier: str = "demo") -> dict:
    compile_bibles(world, detail, acts, scenario_id=scenario_id)
    gate = validate_dir(scenario_dir(scenario_id), tier)
    job = load_job(scenario_id)
    job["world"] = world
    job["detail"] = detail
    job["acts"] = acts
    job["gate"] = gate
    job["status"] = "ready" if gate["ok"] else "failed"
    _save_job(job)
    return job


def load_job(scenario_id: str) -> dict:
    p = job_path(scenario_id)
    if not p.is_file():
        raise FileNotFoundError(scenario_id)
    return json.loads(p.read_text(encoding="utf-8"))


def list_jobs() -> list[dict]:
    items = []
    if not SCENARIOS.is_dir():
        return items
    for d in sorted(SCENARIOS.glob("gen_*")):
        jp = d / "_studio" / "job.json"
        if not jp.is_file():
            continue
        try:
            job = json.loads(jp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append({
            "id": job.get("id", d.name),
            "title": (job.get("world") or {}).get("title") or d.name,
            "status": job.get("status"),
            "ok": bool((job.get("gate") or {}).get("ok")),
            "provider": job.get("provider") or "",
            "created_at": job.get("created_at"),
        })
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items


def public_of(scenario_id: str) -> dict:
    job = load_job(scenario_id)
    playable = job.get("status") == "ready" and bool((job.get("gate") or {}).get("ok"))
    root = scenario_dir(scenario_id)
    pack = public_snapshot(root, playable=playable)
    if "books" not in pack:
        pack["books"] = list_covers(root)
    brief = ((job.get("seed") or {}).get("brief") or {})
    mods = job.get("modules") or brief.get("modules")
    if mods:
        pack["modules"] = mods
    if brief.get("pack_type"):
        pack["pack_type"] = brief["pack_type"]
    vibe = brief.get("vibe") or {}
    if vibe.get("mood"):
        pack["vibe"] = vibe["mood"]
    if brief.get("minis") is not None:
        pack["minis"] = list(brief.get("minis") or [])
    camp = brief.get("camp")
    if isinstance(camp, dict):
        pack["camp"] = {
            "pollution": camp.get("pollution") or "污染",
            "swayable": camp.get("swayable") or "可策反",
            "truth": camp.get("truth") or "求真",
            "public": bool(camp.get("public")),
        }
    return pack


def load_player_book(scenario_id: str, char_id: str) -> dict:
    """路由薄封装：scenario_id → 目录 → load_book（不存在则 FileNotFoundError）。"""
    return load_book(scenario_dir(scenario_id), char_id)


def list_book_covers(scenario_id: str) -> list[dict]:
    """路由薄封装：封面列表；旧 gen_* 无 scripts/ 时为 []。"""
    return list_covers(scenario_dir(scenario_id))


def _save_job(job: dict) -> None:
    p = job_path(job["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
