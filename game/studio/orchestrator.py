"""剧本生产阶段编排器。

编排器只管理状态，不执行 LLM、编译器、验证器或发布命令。实际生产者
通过 ``start`` 获取输入哈希、执行工作后调用 ``record_success`` 或
``record_failure``，从而可以安全地重试、暂停和人工审核。

阶段依赖固定为 ``truth -> cast -> acts -> assemble``。状态可用
``to_dict`` 持久化，也可从旧的草稿/状态字典恢复。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .ir import GenerationState, STAGE_NAMES, StageState, stable_hash


DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "truth": (),
    "cast": ("truth",),
    "acts": ("cast",),
    "assemble": ("acts",),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage(name: str) -> str:
    name = str(name or "").strip().lower()
    if name not in STAGE_NAMES:
        raise ValueError(f"未知生产阶段: {name}")
    return name


def _state(value: GenerationState | Mapping[str, Any]) -> GenerationState:
    if isinstance(value, GenerationState):
        return value
    return GenerationState.from_dict(value)


def _dependency_ready(state: GenerationState, stage: str) -> bool:
    """只有前置阶段显式锁定后，当前阶段才可开始。"""
    return all(
        state.stage_states[dependency].locked
        for dependency in DEPENDENCIES[stage]
    )


def _refresh_blocked(state: GenerationState) -> None:
    """根据依赖刷新尚未运行阶段的 blocked/pending 状态。"""
    for name in STAGE_NAMES:
        current = state.stage_states[name]
        if current.status in {"running", "succeeded", "awaiting_human"} or current.locked:
            continue
        if current.status == "failed":
            if current.retry < current.max_retries:
                continue
            # 重试预算耗尽后保留 failed，便于人工定位，而不是伪装成可运行的 pending。
            continue
        current.status = "pending" if _dependency_ready(state, name) else "blocked"


def create_state(draft_id: str, *, max_retries: int = 2) -> GenerationState:
    """创建新的生产状态；仅初始化内存对象，不写草稿文件。"""
    draft_id = str(draft_id or "").strip()
    if not draft_id:
        raise ValueError("draft_id 不能为空")
    state = GenerationState.create(draft_id, max_retries=max_retries)
    _refresh_blocked(state)
    return state


def from_dict(value: Mapping[str, Any] | None) -> GenerationState:
    """从持久化字典恢复状态，兼容 ``stages`` 列表和 ``stage_states`` 映射。"""
    return GenerationState.from_dict(value)


def to_dict(state: GenerationState | Mapping[str, Any]) -> dict[str, Any]:
    """导出 JSON 兼容状态字典。"""
    return _state(state).to_dict()


def can_start(state: GenerationState | Mapping[str, Any], stage: str) -> bool:
    """判断阶段当前是否能开始。

    已锁定、运行中、成功或等待人工审核的阶段不可重复开始；失败阶段仅在
    ``retry < max_retries`` 时可重试；所有前置阶段必须成功或已锁定。
    """
    state = _state(state)
    stage = _stage(stage)
    current = state.stage_states[stage]
    if current.locked or current.status in {"running", "succeeded", "awaiting_human"}:
        return False
    if current.status == "failed" and current.retry >= current.max_retries:
        return False
    return _dependency_ready(state, stage)


def start(
    state: GenerationState | Mapping[str, Any],
    stage: str,
    input_value: Any = None,
    *,
    input_hash: str | None = None,
    provider: str | None = None,
) -> GenerationState:
    """开始一个阶段并记录输入哈希、provider 和尝试次数。

    ``input_value`` 只在调用瞬间计算哈希，不会写入状态，避免把完整剧本或
    私密上下文复制到编排记录。传入 ``input_hash`` 可供调用方自行计算。
    """
    state = _state(state)
    stage = _stage(stage)
    if not can_start(state, stage):
        raise RuntimeError(f"阶段不可开始: {stage}")
    current = state.stage_states[stage]
    was_retry = current.status == "failed"
    current.status = "running"
    current.attempts += 1
    if was_retry:
        current.retry += 1
    current.input_hash = input_hash or (stable_hash(input_value) if input_value is not None else None)
    current.output_hash = None
    current.error = None
    if provider is not None:
        current.provider = str(provider)
    state.current_stage = stage
    state.status = "running"
    return state


def record_success(
    state: GenerationState | Mapping[str, Any],
    stage: str,
    output_value: Any = None,
    *,
    output_hash: str | None = None,
    provider: str | None = None,
    requires_human: bool | None = None,
) -> GenerationState:
    """记录阶段成功；需要人工审核时转为 ``awaiting_human``。

    输出内容不保存到状态，只保存哈希。``requires_human`` 未提供时沿用阶段
    的 ``human_gate`` 标志。
    """
    state = _state(state)
    stage = _stage(stage)
    current = state.stage_states[stage]
    if current.status != "running":
        raise RuntimeError(f"阶段未运行，不能记录成功: {stage}")
    current.output_hash = output_hash or (stable_hash(output_value) if output_value is not None else None)
    current.error = None
    if provider is not None:
        current.provider = str(provider)
    if requires_human is not None:
        current.human_gate = bool(requires_human)
        state.human_gates[stage] = bool(requires_human)
    current.status = "awaiting_human" if current.human_gate else "succeeded"
    if current.status == "awaiting_human":
        state.current_stage = stage
    else:
        _refresh_blocked(state)
        state.current_stage = next(
            (name for name in STAGE_NAMES if can_start(state, name)), None
        )
        if state.current_stage is None and all(
            state.stage_states[name].status in {"succeeded", "locked"}
            or state.stage_states[name].locked for name in STAGE_NAMES
        ):
            state.status = "succeeded"
    return state


def record_failure(
    state: GenerationState | Mapping[str, Any],
    stage: str,
    error: Any,
    *,
    retryable: bool = True,
) -> GenerationState:
    """记录失败并保留有限重试机会；不自动修复或改写生产内容。"""
    state = _state(state)
    stage = _stage(stage)
    current = state.stage_states[stage]
    if current.status != "running":
        raise RuntimeError(f"阶段未运行，不能记录失败: {stage}")
    current.status = "failed"
    current.error = str(error or "阶段执行失败")[:500]
    if not retryable:
        current.retry = current.max_retries
    _refresh_blocked(state)
    state.current_stage = stage
    state.status = "failed"
    return state


def lock_stage(
    state: GenerationState | Mapping[str, Any],
    stage: str,
    *,
    approved: bool = True,
) -> GenerationState:
    """锁定已成功阶段，作为下游可消费的人工/版本边界。

    ``locked_at`` 是锁定标志，保留 status ``succeeded`` 以兼容既有状态枚举。
    等待人工审核的阶段必须显式传 ``approved=True``；未批准会返回错误。
    """
    state = _state(state)
    stage = _stage(stage)
    current = state.stage_states[stage]
    if current.status == "awaiting_human" and not approved:
        raise PermissionError(f"阶段尚未通过人工门禁: {stage}")
    if current.status not in {"succeeded", "awaiting_human"}:
        raise RuntimeError(f"阶段未成功，不能锁定: {stage}")
    if current.human_gate and not approved:
        raise PermissionError(f"阶段尚未通过人工门禁: {stage}")
    current.status = "succeeded"
    current.locked_at = current.locked_at or _now()
    state.human_gates[stage] = True
    _refresh_blocked(state)
    state.current_stage = next(
        (name for name in STAGE_NAMES if can_start(state, name)), None
    )
    if state.current_stage is None and all(
        state.stage_states[name].locked for name in STAGE_NAMES
    ):
        state.status = "succeeded"
    return state


def unlock_stage(
    state: GenerationState | Mapping[str, Any],
    stage: str,
    *,
    clear_output: bool = True,
) -> GenerationState:
    """解锁阶段以便修改并重跑，同时阻塞所有依赖它的下游阶段。"""
    state = _state(state)
    stage = _stage(stage)
    current = state.stage_states[stage]
    current.locked_at = None
    current.status = "pending" if _dependency_ready(state, stage) else "blocked"
    current.error = None
    if clear_output:
        current.output_hash = None
    invalidated = False
    for name in STAGE_NAMES:
        if name == stage or stage in DEPENDENCIES[name] or invalidated:
            if name == stage:
                invalidated = True
                continue
            child = state.stage_states[name]
            # 上游解锁意味着下游产物可能过期；即使下游曾人工锁定，也必须
            # 清除旧锁后重新验证，防止 stale output 绕过 assemble 闸门。
            child.status = "blocked"
            child.locked_at = None
            child.output_hash = None
            child.error = None
            invalidated = True
    state.human_gates[stage] = current.human_gate
    state.current_stage = stage
    state.status = "draft"
    return state


def stage_snapshot(
    state: GenerationState | Mapping[str, Any],
    stage: str | None = None,
) -> dict[str, Any]:
    """返回单阶段快照，或返回所有阶段的公开快照。"""
    state = _state(state)
    if stage is not None:
        return state.stage_states[_stage(stage)].to_dict()
    return {name: state.stage_states[name].to_dict() for name in STAGE_NAMES}


class GenerationOrchestrator:
    """GenerationState 的轻量面向对象外观，便于服务层持有单个草稿。"""

    dependencies = DEPENDENCIES

    def __init__(self, state: GenerationState):
        self.state = state

    @classmethod
    def create_state(cls, draft_id: str, *, max_retries: int = 2) -> "GenerationOrchestrator":
        return cls(create_state(draft_id, max_retries=max_retries))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "GenerationOrchestrator":
        return cls(from_dict(value))

    def to_dict(self) -> dict[str, Any]:
        return to_dict(self.state)

    def can_start(self, stage: str) -> bool:
        return can_start(self.state, stage)

    def start(self, stage: str, input_value: Any = None, **kwargs: Any) -> GenerationState:
        self.state = start(self.state, stage, input_value, **kwargs)
        return self.state

    def record_success(self, stage: str, output_value: Any = None, **kwargs: Any) -> GenerationState:
        self.state = record_success(self.state, stage, output_value, **kwargs)
        return self.state

    def record_failure(self, stage: str, error: Any, **kwargs: Any) -> GenerationState:
        self.state = record_failure(self.state, stage, error, **kwargs)
        return self.state

    def lock_stage(self, stage: str, **kwargs: Any) -> GenerationState:
        self.state = lock_stage(self.state, stage, **kwargs)
        return self.state

    def unlock_stage(self, stage: str, **kwargs: Any) -> GenerationState:
        self.state = unlock_stage(self.state, stage, **kwargs)
        return self.state

    def stage_snapshot(self, stage: str | None = None) -> dict[str, Any]:
        return stage_snapshot(self.state, stage)


Orchestrator = GenerationOrchestrator


__all__ = [
    "DEPENDENCIES", "GenerationOrchestrator", "Orchestrator", "can_start",
    "create_state", "from_dict", "lock_stage", "record_failure",
    "record_success", "stage_snapshot", "start", "to_dict", "unlock_stage",
]
