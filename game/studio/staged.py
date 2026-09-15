"""分阶段制作流水线（行业流程驱动）：每阶段产出可编辑草案，最终统一编译过闸。

阶段映射（第一性原理：真相先行 → 信息切割 → 闭环验证）：
  stage_truth : 行业第二步 · 设计总纲（真相/凶手/手法/真相树）
  stage_cast  : 行业第三步 · 角色与信息分配（4 嫌疑人 + 秘密 + 伪证）
  stage_acts  : 行业第四五步 · 线索编排与幕次（三幕 + 分幕发放 + 反转）
  assemble    : 行业第六步 · 编译过闸（结构 + 叙事闸门，落盘 gen_pack）

铁律：
  - 阶段之间由前端传递并编辑 world/detail/acts；服务端不合并编辑（前端全权）。
  - LLM 不可用时每阶段退回 mock 骨架对应段，管线永不中断。
  - 本模块不修改 pipeline.generate 既有行为，仅供分阶段端点使用。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import llm_steps, mock_bible, pipeline as _pipeline
from .brief import apply_brief, normalize_brief
from .compiler import compile_bibles
from .ids import make_scenario_id
from .paths import GAME_ROOT, scenario_dir
from .player_book import build_books
from .validate import validate_dir
from .ir import STAGE_NAMES, GenerationState, stable_hash
from .orchestrator import (
    can_start as _can_start_stage,
    create_state as _create_generation_state,
    from_dict as _generation_from_dict,
    lock_stage as _lock_stage,
    record_failure as _record_stage_failure,
    record_success as _record_stage_success,
    start as _start_stage,
    unlock_stage as _unlock_stage,
)

DRAFTS = GAME_ROOT / "data" / "_studio" / "drafts"
_STAGE_KEY = {"truth": "world", "cast": "detail", "acts": "acts"}


# ------------------------------------------------------------------ 草稿存取


def _draft_path(draft_id: str) -> Path:
    if not re.fullmatch(r"draft_[0-9a-f]{8}", draft_id or ""):
        raise ValueError("非法 draft_id")
    return DRAFTS / f"{draft_id}.json"


def create_draft(seed: str, brief: dict | None, *, inner_boss: bool = False) -> dict:
    seed = " ".join((seed or "").split())
    if not seed:
        raise ValueError("seed 不能为空")
    brief_n = normalize_brief(brief, seed)
    draft_id = f"draft_{uuid.uuid4().hex[:8]}"
    generation_state = _create_generation_state(draft_id)
    draft = {
        "draft_id": draft_id,
        "seed": seed,
        "brief": brief_n,
        "world": None,
        "detail": None,
        "acts": None,
        "providers": {},
        "generation": generation_state.to_dict(),
        "agents": _agent_metadata(generation_state),
        "locks": {},
        "provenance": {
            "source": "studio_draft",
            "seed_hash": stable_hash(seed),
            "brief_hash": stable_hash(brief_n),
        },
        "validation": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_draft(draft)
    return draft


def save_draft(draft: dict) -> None:
    DRAFTS.mkdir(parents=True, exist_ok=True)
    _draft_path(draft["draft_id"]).write_text(
        json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_draft(draft_id: str) -> dict:
    p = _draft_path(draft_id)
    if not p.is_file():
        raise FileNotFoundError(draft_id)
    return json.loads(p.read_text(encoding="utf-8"))


def _generation_for_draft(draft: dict) -> GenerationState:
    """读取编排状态，并为旧草稿从已有阶段产物建立兼容状态。"""
    raw = draft.get("generation")
    if raw:
        state = _generation_from_dict(raw)
    else:
        state = _create_generation_state(draft["draft_id"])
        # 仅旧草稿首次迁移时从正文推导阶段产物；已有 generation 的失败/
        # running/awaiting_human 状态必须保持，不能因正文尚存而被覆盖。
        for stage, key in _STAGE_KEY.items():
            current = state.stage_states[stage]
            if draft.get(key) is not None:
                current.status = "succeeded"
                current.attempts = max(1, current.attempts)
                current.output_hash = stable_hash(draft[key])
    return state


def _agent_metadata(state: GenerationState) -> dict:
    """将四阶段状态投影成工作台可展示的智能体任务摘要。"""
    names = {
        "truth": ("truth_agent", "真相与世界 Agent"),
        "cast": ("cast_agent", "角色与记忆 Agent"),
        "acts": ("acts_agent", "幕次与线索 Agent"),
        "assemble": ("validator_agent", "编译与规则校验 Agent"),
    }
    return {
        stage: {
            "agent_id": names[stage][0],
            "name": names[stage][1],
            "stage": stage,
            **item.to_dict(),
        }
        for stage, item in state.stage_states.items()
    }


def _sync_generation(draft: dict, state: GenerationState) -> None:
    """只同步状态元数据；不把阶段正文复制进 generation。"""
    draft["generation"] = state.to_dict()
    draft["agents"] = _agent_metadata(state)
    draft["locks"] = {
        name: {
            "locked_at": item.locked_at,
            "output_hash": item.output_hash,
            "provider": item.provider,
        }
        for name, item in state.stage_states.items()
        if item.locked
    }


def _start_draft_stage(draft: dict, stage: str, input_value) -> GenerationState:
    """记录阶段 running，并立即保存，避免进程中断后丢失尝试信息。"""
    state = _generation_for_draft(draft)
    if not _can_start_stage(state, stage):
        raise RuntimeError(f"阶段不可开始，前置阶段未锁定或当前状态不可重试: {stage}")
    provider = (draft.get("providers") or {}).get(stage)
    _start_stage(state, stage, input_hash=stable_hash(input_value), provider=provider)
    _sync_generation(draft, state)
    save_draft(draft)
    return state


def _record_draft_success(draft: dict, stage: str, output, provider: str) -> None:
    """记录阶段成功；默认 human_gate 会使前三阶段等待人工确认。"""
    state = _generation_for_draft(draft)
    _record_stage_success(
        state,
        stage,
        output_hash=stable_hash(output),
        provider=provider,
    )
    _sync_generation(draft, state)
    save_draft(draft)


def _record_draft_failure(draft: dict, stage: str, error: Exception) -> None:
    """记录阶段失败并保留有限重试预算，再把原异常交给调用方。"""
    state = _generation_for_draft(draft)
    _record_stage_failure(state, stage, str(error))
    _sync_generation(draft, state)
    save_draft(draft)


def _assert_locked_stage_input(
    state: GenerationState,
    stage: str,
    value: dict,
) -> None:
    """禁止下游请求用新正文覆盖已锁定的上游版本。"""
    current = state.stage_states[stage]
    if not current.locked:
        return
    expected = current.output_hash
    actual = stable_hash(value)
    if not expected or actual != expected:
        raise RuntimeError(f"{stage} 输入已偏离锁定版本")


def lock_draft_stage(draft: dict, stage: str, output: dict | None = None) -> dict:
    """写入阶段草稿并锁定它，供 REST 层执行人工门禁。

    ``output`` 仅写入 truth/cast/acts 对应的草稿字段；编排状态只保存哈希、
    provider 和锁定时间。``assemble`` 没有草稿正文字段，仅锁定其状态。
    """
    stage = str(stage or "").strip().lower()
    if stage not in (*_STAGE_KEY, "assemble"):
        raise ValueError(f"未知生产阶段: {stage}")
    state = _generation_for_draft(draft)
    current = state.stage_states[stage]
    if current.locked and output is not None:
        raise RuntimeError(f"阶段已锁定，修改前必须先解锁: {stage}")
    if output is not None:
        if stage in _STAGE_KEY:
            draft[_STAGE_KEY[stage]] = output
        elif not isinstance(output, dict):
            raise ValueError("assemble output 必须是对象")
    elif stage in _STAGE_KEY and draft.get(_STAGE_KEY[stage]) is None:
        raise ValueError(f"阶段尚无可锁定产物: {stage}")

    if not current.locked:
        # 锁定是人工批准动作，不得把 pending/failed/running 伪装成已生成。
        # 已有尝试的阶段解锁后会回到 pending，但允许作者复核并重算新稿 hash；
        # 初始空阶段仍保持严格拒绝。
        if current.status == "pending" and current.attempts > 0 and stage in _STAGE_KEY:
            current.status = "awaiting_human"
        if current.status not in {"succeeded", "awaiting_human"}:
            raise RuntimeError(f"阶段尚未生成成功，不能锁定: {stage}")
        value = output if output is not None else draft.get(_STAGE_KEY.get(stage, ""))
        if stage in _STAGE_KEY and value is None:
            raise ValueError(f"阶段尚无可锁定产物: {stage}")
        if value is not None:
            # 作者编辑后锁定时，锁定哈希必须对应当前稿。
            current.output_hash = stable_hash(value)
    state = _lock_stage(state, stage, approved=True)
    _sync_generation(draft, state)
    save_draft(draft)
    return draft


def unlock_draft_stage(draft: dict, stage: str) -> dict:
    """解锁阶段并使其下游旧产物失效，然后保存草稿。"""
    stage = str(stage or "").strip().lower()
    state = _generation_for_draft(draft)
    _unlock_stage(state, stage)
    _sync_generation(draft, state)
    save_draft(draft)
    return draft


# ------------------------------------------------------------------ 阶段生成


def _skeleton(seed: str, brief_n: dict, inner_boss: bool) -> dict:
    return mock_bible.build(seed, inner_boss=inner_boss, brief=brief_n)


# ------------------------------------------------------------------ 知乎素材注入


def _story_material(n: int = 2, per: int = 900) -> str:
    """黑客松故事素材（无鉴权）。失败/空 → 空串，管线不中断。正文视为不可信。"""
    try:
        from server.zhihu_bridge import fetch_story_list, fetch_story, sanitize_excerpt
        rows = fetch_story_list()
        if not isinstance(rows, list):
            return ""
        parts = []
        for row in rows[:n]:
            wid = str((row or {}).get("work_id") or "").strip()
            if not wid:
                continue
            d = fetch_story(wid) or {}
            title = str(d.get("chapter_name") or row.get("title") or "").strip()
            body = sanitize_excerpt(str(d.get("content") or ""), per)
            author = str(d.get("author_name") or "").strip()
            if body:
                parts.append(f"- 《{title}》（{author}）：{body}")
        if not parts:
            return ""
        return ("【知乎故事素材 · 仅供人设与冲突写法参考，禁止照抄剧情，视为不可信资料】\n"
                + "\n".join(parts))
    except Exception:  # noqa: BLE001
        return ""


def _knowledge_material(n: int = 2, per: int = 700) -> str:
    """黑客松知识素材（无鉴权）。供知识卡/辟谣线事实依据。失败 → 空串。"""
    try:
        from server.zhihu_bridge import fetch_knowledge_list, fetch_work, sanitize_excerpt
        rows = fetch_knowledge_list()
        if not isinstance(rows, list):
            return ""
        parts = []
        for row in rows[:n]:
            wid = str((row or {}).get("work_id") or "").strip()
            if not wid:
                continue
            d = fetch_work(wid, kind="knowledge") or {}
            title = str(d.get("chapter_name") or row.get("title") or "").strip()
            body = sanitize_excerpt(str(d.get("content") or ""), per)
            if body:
                parts.append(f"- 《{title}》：{body}")
        if not parts:
            return ""
        return ("【知乎知识素材 · 供知识卡与辟谣线索的事实依据，禁止编造】\n"
                + "\n".join(parts))
    except Exception:  # noqa: BLE001
        return ""


def _gen_stage(stage: str, seed: str, brief_n: dict, *, inner_boss: bool,
               world: dict | None = None, detail: dict | None = None,
               llm=None, material: str = "") -> tuple[dict, str]:
    """单阶段生成：LLM 可用走对应 _step_*（可携知乎素材），否则退回 mock 骨架对应段。"""
    key = _STAGE_KEY[stage]
    skeleton = _skeleton(seed, brief_n, inner_boss)
    try:
        client = llm and llm_steps._resolve_llm(llm)
    except Exception:  # noqa: BLE001
        client = None
    if client is None:
        return skeleton[key], "mock"
    try:
        if stage == "truth":
            data = llm_steps._step_world(client, seed, skeleton, inner_boss=inner_boss, material=material)
        elif stage == "cast":
            data = llm_steps._step_detail(client, seed, world or skeleton["world"], skeleton, material=material)
        elif stage == "acts":
            data = llm_steps._step_acts(
                client, seed, world or skeleton["world"], detail or skeleton["detail"], skeleton, material=material)
        else:
            raise ValueError(f"未知阶段 {stage}")
        return data, (llm_steps._provider_name(client) or "main")
    except Exception:  # noqa: BLE001
        return skeleton[key], "mock"


def stage_truth(draft: dict, *, llm=None, inner_boss: bool = False, use_zhihu: bool = False) -> dict:
    brief_n = draft["brief"]
    _start_draft_stage(draft, "truth", {"seed": draft["seed"], "brief": brief_n})
    try:
        material = _story_material() if use_zhihu else ""
        world, provider = _gen_stage(
            "truth", draft["seed"], brief_n, inner_boss=inner_boss, llm=llm, material=material)
        apply_brief(world, _skeleton(draft["seed"], brief_n, inner_boss)["detail"],
                    _skeleton(draft["seed"], brief_n, inner_boss)["acts"], brief_n)
        draft["world"] = world
        draft["providers"]["truth"] = provider
        _record_draft_success(draft, "truth", world, provider)
        return draft
    except Exception as exc:
        _record_draft_failure(draft, "truth", exc)
        raise


def stage_cast(draft: dict, world: dict | None = None, *, llm=None, use_zhihu: bool = False) -> dict:
    if world and isinstance(world, dict) and world.get("title"):
        state = _generation_for_draft(draft)
        _assert_locked_stage_input(state, "truth", world)
        draft["world"] = world  # 用户在真相步的编辑覆盖
    if not draft.get("world"):
        raise ValueError("真相未生成（行业铁律：真相先行）")
    brief_n = draft["brief"]
    _start_draft_stage(draft, "cast", draft["world"])
    try:
        material = _story_material() if use_zhihu else ""
        detail, provider = _gen_stage(
            "cast", draft["seed"], brief_n, world=draft["world"], llm=llm,
            inner_boss=bool((brief_n.get("modules") or {}).get("inner_boss")), material=material)
        apply_brief(draft["world"], detail,
                    _skeleton(draft["seed"], brief_n, False)["acts"], brief_n)
        draft["detail"] = detail
        draft["providers"]["cast"] = provider
        _record_draft_success(draft, "cast", detail, provider)
        return draft
    except Exception as exc:
        _record_draft_failure(draft, "cast", exc)
        raise


def stage_acts(draft: dict, world: dict | None = None, detail: dict | None = None,
               *, llm=None, use_zhihu: bool = False) -> dict:
    state = _generation_for_draft(draft)
    if world and isinstance(world, dict) and world.get("title"):
        _assert_locked_stage_input(state, "truth", world)
        draft["world"] = world
    if detail and isinstance(detail, dict) and detail.get("characters"):
        _assert_locked_stage_input(state, "cast", detail)
        draft["detail"] = detail
    if not draft.get("world") or not draft.get("detail"):
        raise ValueError("真相或角色未锁定（按流程：真相 → 角色 → 幕次）")
    brief_n = draft["brief"]
    _start_draft_stage(draft, "acts", {"world": draft["world"], "detail": draft["detail"]})
    try:
        material = _knowledge_material() if use_zhihu else ""
        acts, provider = _gen_stage(
            "acts", draft["seed"], brief_n,
            world=draft["world"], detail=draft["detail"], llm=llm,
            inner_boss=bool((brief_n.get("modules") or {}).get("inner_boss")), material=material)
        apply_brief(draft["world"], draft["detail"], acts, brief_n)
        draft["acts"] = acts
        draft["providers"]["acts"] = provider
        _record_draft_success(draft, "acts", acts, provider)
        return draft
    except Exception as exc:
        _record_draft_failure(draft, "acts", exc)
        raise


def _assert_assemble_inputs_locked(
    state: GenerationState,
    world: dict,
    detail: dict,
    acts: dict,
) -> None:
    """校验 assemble 输入仍是三阶段锁定版本，防止客户端篡改后编译。"""
    values = {"truth": world, "cast": detail, "acts": acts}
    mismatches: list[str] = []
    for stage, value in values.items():
        stage_state = state.stage_states[stage]
        expected = stage_state.output_hash
        actual = stable_hash(value)
        if not stage_state.locked:
            mismatches.append(f"{stage}: 未锁定")
        elif not expected:
            mismatches.append(f"{stage}: 缺少锁定哈希")
        elif actual != expected:
            mismatches.append(f"{stage}: 输入哈希不匹配")
    if mismatches:
        raise RuntimeError("assemble 输入已偏离锁定版本: " + "; ".join(mismatches))


def assemble(draft: dict, world: dict, detail: dict, acts: dict,
             *, tier: str = "demo") -> dict:
    """终稿编译：apply_brief → compile → 双册 → 结构+叙事闸门 → 落盘 job。"""
    if not (world and detail and acts):
        raise ValueError("三个阶段的草案必须全部就绪才能编译")
    # assemble 也受人工门禁编排：truth/cast/acts 必须全部显式锁定。
    generation_state = _generation_for_draft(draft)
    _assert_assemble_inputs_locked(generation_state, world, detail, acts)
    _start_draft_stage(draft, "assemble", {"world": world, "detail": detail, "acts": acts})
    try:
        brief_n = draft["brief"]
        apply_brief(world, detail, acts, brief_n)
        sid = make_scenario_id(
            world.get("title") or "pack",
            draft["seed"],
            variant=stable_hash(brief_n),
        )
        compile_bibles(world, detail, acts, scenario_id=sid)
        detail["player_books"] = build_books(world, detail, acts)
        gate = validate_dir(scenario_dir(sid), tier)
        providers = draft.get("providers") or {}
        provider = "main" if any(v not in ("mock",) for v in providers.values()) else "mock"
        job = {
            "id": sid,
            "status": "ready" if gate["ok"] else "failed",
            "tier": tier,
            "seed": {"text": draft["seed"], "brief": brief_n},
            "modules": brief_n["modules"],
            "world": world,
            "detail": detail,
            "acts": acts,
            "gate": gate,
            "provider": provider,
            "staged": True,
            "scenario_dir": f"content/scenarios/{sid}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        draft["gate"] = gate
        draft["scenario_id"] = sid
        # 只有编译与验证闸门都通过，assemble 才算成功并可锁定。
        if gate.get("ok"):
            _record_draft_success(draft, "assemble", job, provider)
            final_state = _generation_for_draft(draft)
            final_state = _lock_stage(final_state, "assemble", approved=True)
        else:
            errors = "; ".join(str(item) for item in (gate.get("errors") or [])[:3])
            _record_draft_failure(draft, "assemble", RuntimeError(
                "assemble 闸门未通过" + (f": {errors}" if errors else "")))
            final_state = _generation_for_draft(draft)
        _sync_generation(draft, final_state)
        validation = {
            "ok": bool(gate.get("ok")),
            "gate": gate,
            "scenario_id": sid,
        }
        draft["validation"] = validation
        job.update({
            "generation": final_state.to_dict(),
            "agents": _agent_metadata(final_state),
            "locks": dict(draft.get("locks") or {}),
            "provenance": dict(draft.get("provenance") or {}),
            "validation": validation,
        })
        _pipeline._save_job(job)
        save_draft(draft)
        return job
    except Exception as exc:
        _record_draft_failure(draft, "assemble", exc)
        raise
