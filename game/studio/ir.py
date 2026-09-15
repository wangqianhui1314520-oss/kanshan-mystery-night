"""剧本生产流水线的中间表示（IR）与可持久化状态。

本模块只描述数据，不调用 LLM、文件系统或规则引擎。旧版 studio job
仍是兼容边界；新增字段仅承载编排元数据、哈希和公开诊断摘要。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping


IR_VERSION = "1.0"
STAGE_NAMES = ("truth", "cast", "acts", "assemble")
STAGE_STATUSES = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "awaiting_human",
)


def stable_hash(value: Any) -> str:
    """返回与字典顺序和空白无关的 SHA-256 哈希。

    结构化值使用规范 JSON；无法 JSON 序列化的值退回其稳定字符串表示。
    该哈希只用于阶段输入/输出变更检测，不是安全签名。
    """
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=lambda item: str(item),
        )
    except (TypeError, ValueError):
        payload = repr(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _public_metadata(value: Any, *, depth: int = 0) -> Any:
    """复制公开元数据，丢弃明显的全文/私密字段。

    IR 的 provenance、agents 和 validation 面向工作台状态展示，不应成为
    角色秘密、心声或原始提示词的旁路。内容字段由旧版 job 自己继续承载。
    """
    if depth > 3:
        return "…"
    if isinstance(value, Mapping):
        private_keys = {
            "secret", "secrets", "guilt", "motive", "inner_truth", "heart",
            "prompt", "system_prompt", "user_prompt", "raw", "full_text",
            "private", "token", "access_secret", "api_key",
        }
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in private_keys:
                continue
            result[key_text] = _public_metadata(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_public_metadata(item, depth=depth + 1) for item in list(value)[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:500]
    return str(value)[:500]


@dataclass
class Diagnostic:
    """一条公开诊断信息；不保存模型原始响应或私密全文。"""

    severity: str = "error"
    code: str = "UNKNOWN"
    message: str = ""
    stage: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": _bounded_text(self.message) or "",
            "stage": self.stage,
            "details": _public_metadata(self.details),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "Diagnostic":
        value = value or {}
        return cls(
            severity=str(value.get("severity") or "error"),
            code=str(value.get("code") or "UNKNOWN"),
            message=str(value.get("message") or ""),
            stage=(str(value["stage"]) if value.get("stage") is not None else None),
            details=dict(_public_metadata(value.get("details") or {})),
        )


@dataclass
class StageState:
    """单阶段的状态、重试和人工门禁元数据。"""

    stage: str
    status: str = "pending"
    attempts: int = 0
    retry: int = 0
    max_retries: int = 2
    provider: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    error: str | None = None
    human_gate: bool = False
    locked_at: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in STAGE_NAMES:
            raise ValueError(f"未知生产阶段: {self.stage}")
        if self.status not in STAGE_STATUSES and self.status != "locked":
            raise ValueError(f"未知阶段状态: {self.status}")
        self.attempts = max(0, int(self.attempts))
        self.retry = max(0, int(self.retry))
        self.max_retries = max(0, int(self.max_retries))
        self.error = _bounded_text(self.error)

    @property
    def locked(self) -> bool:
        return self.status == "locked" or bool(self.locked_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "attempts": self.attempts,
            "retry": self.retry,
            "max_retries": self.max_retries,
            "provider": self.provider,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "error": self.error,
            "human_gate": self.human_gate,
            "locked_at": self.locked_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None, *, stage: str | None = None) -> "StageState":
        value = value or {}
        name = str(value.get("stage") or stage or "truth")
        return cls(
            stage=name,
            status=str(value.get("status") or "pending"),
            attempts=value.get("attempts", 0),
            retry=value.get("retry", 0),
            max_retries=value.get("max_retries", 2),
            provider=(str(value["provider"]) if value.get("provider") is not None else None),
            input_hash=(str(value["input_hash"]) if value.get("input_hash") else None),
            output_hash=(str(value["output_hash"]) if value.get("output_hash") else None),
            error=value.get("error"),
            human_gate=bool(
                value.get("human_gate", name in {"truth", "cast", "acts"})
            ),
            locked_at=value.get("locked_at"),
        )


@dataclass
class GenerationState:
    """整个剧本生成任务的可序列化状态。"""

    draft_id: str
    status: str = "draft"
    current_stage: str | None = "truth"
    stage_states: dict[str, StageState] = field(default_factory=dict)
    human_gates: dict[str, bool] = field(default_factory=dict)
    retry_policy: dict[str, Any] = field(
        default_factory=lambda: {"max_retries": 2, "backoff": "exponential"}
    )

    def __post_init__(self) -> None:
        if not self.stage_states:
            max_retries = int(self.retry_policy.get("max_retries", 2))
            self.stage_states = {
                name: StageState(
                    name,
                    max_retries=max_retries,
                    human_gate=name in {"truth", "cast", "acts"},
                )
                for name in STAGE_NAMES
            }
        else:
            self.stage_states = {
                name: (value if isinstance(value, StageState)
                       else StageState.from_dict(value, stage=name))
                for name, value in self.stage_states.items()
                if name in STAGE_NAMES
            }
            for name in STAGE_NAMES:
                self.stage_states.setdefault(
                    name,
                    StageState(name, human_gate=name in {"truth", "cast", "acts"}),
                )
        self.human_gates = {
            name: bool(self.human_gates.get(name, self.stage_states[name].human_gate))
            for name in STAGE_NAMES
        }
        for name, required in self.human_gates.items():
            self.stage_states[name].human_gate = required

    @classmethod
    def create(cls, draft_id: str, *, max_retries: int = 2) -> "GenerationState":
        policy = {"max_retries": max(0, int(max_retries)), "backoff": "exponential"}
        # 真相、角色和幕次必须逐阶段人工确认；assemble 由最终验证/发布门禁控制。
        stage_states = {
            name: StageState(
                name,
                max_retries=policy["max_retries"],
                human_gate=name in {"truth", "cast", "acts"},
            )
            for name in STAGE_NAMES
        }
        return cls(
            draft_id=str(draft_id),
            retry_policy=policy,
            stage_states=stage_states,
            human_gates={name: name in {"truth", "cast", "acts"} for name in STAGE_NAMES},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "stage_states": {name: state.to_dict() for name, state in self.stage_states.items()},
            "human_gates": dict(self.human_gates),
            "retry_policy": _public_metadata(self.retry_policy),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "GenerationState":
        value = value or {}
        raw_states = value.get("stage_states") or value.get("stages") or {}
        if isinstance(raw_states, list):
            raw_states = {
                row.get("stage"): row for row in raw_states
                if isinstance(row, Mapping) and row.get("stage")
            }
        current_stage = value["current_stage"] if "current_stage" in value else "truth"
        state = cls(
            draft_id=str(value.get("draft_id") or value.get("id") or ""),
            status=str(value.get("status") or "draft"),
            current_stage=current_stage,
            stage_states={
                str(name): StageState.from_dict(row, stage=str(name))
                for name, row in raw_states.items()
                if str(name) in STAGE_NAMES and isinstance(row, Mapping)
            },
            human_gates=dict(value.get("human_gates") or {}),
            retry_policy=dict(value.get("retry_policy") or {"max_retries": 2}),
        )
        return state


@dataclass
class ScriptPackage:
    """统一剧本包 IR，并提供旧版 job 的双向适配。

    `world/detail/acts` 是现有编译器的权威输入；其余字段是工作台和工具链
    使用的稳定投影。这样可以先把一句话编译成结构化包，再逐步接入剧情图、
    局部重生成和线上运行，而不要求一次替换现有 scenario JSON。
    """

    id: str
    status: str = "draft"
    tier: str = "demo"
    seed: Any = field(default_factory=dict)
    world: Any = None
    detail: Any = None
    acts: Any = None
    gate: dict[str, Any] = field(default_factory=dict)
    provider: str = "mock"
    scenario_dir: str = ""
    created_at: str = ""
    package_id: str = ""
    ir_version: str = IR_VERSION
    title: str = ""
    players: dict[str, Any] = field(default_factory=dict)
    genre: list[str] = field(default_factory=list)
    duration_minutes: int | None = None
    difficulty: str = ""
    truth: dict[str, Any] = field(default_factory=dict)
    characters: list[Any] = field(default_factory=list)
    locations: list[Any] = field(default_factory=list)
    timeline: list[Any] = field(default_factory=list)
    clues: list[Any] = field(default_factory=list)
    scenes: list[Any] = field(default_factory=list)
    endings: list[Any] = field(default_factory=list)
    rules: dict[str, Any] = field(default_factory=dict)
    memories: dict[str, Any] = field(default_factory=dict)
    knowledge_cards: list[Any] = field(default_factory=list)
    hotfeed: list[Any] = field(default_factory=list)
    assets: dict[str, Any] = field(default_factory=dict)
    compile: dict[str, Any] = field(default_factory=dict)
    modules: dict[str, Any] = field(default_factory=dict)
    staged: bool | None = None
    generation: GenerationState | dict[str, Any] | None = None
    agents: dict[str, Any] = field(default_factory=dict)
    locks: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id or "")
        self.package_id = str(self.package_id or self.id)
        self.ir_version = str(self.ir_version or IR_VERSION)
        self.title = str(self.title or "")
        if isinstance(self.generation, Mapping):
            self.generation = GenerationState.from_dict(self.generation)
        if self.generation is None:
            self.generation = GenerationState.create(self.id)

    @classmethod
    def from_job(cls, job: Mapping[str, Any]) -> "ScriptPackage":
        """从旧版 job 构造 IR；缺少 generation 时创建兼容默认状态。"""
        job = job or {}
        generation = job.get("generation")
        if generation is None:
            generation = GenerationState.create(str(job.get("id") or "")).to_dict()
        validation = _public_metadata(job.get("validation") or {})
        if not validation and job.get("gate"):
            gate = job.get("gate") or {}
            validation = {
                "ok": bool(gate.get("ok")),
                "errors": [str(item)[:500] for item in gate.get("errors", [])[:32]],
                "warnings": [str(item)[:500] for item in gate.get("warnings", [])[:32]],
            }
        world = job.get("world") or {}
        detail = job.get("detail") or {}
        acts = job.get("acts") or {}
        sid = str(job.get("id") or "")
        return cls(
            id=sid,
            package_id=str(job.get("package_id") or sid),
            ir_version=str(job.get("ir_version") or IR_VERSION),
            status=str(job.get("status") or "draft"),
            tier=str(job.get("tier") or "demo"),
            seed=job.get("seed") if job.get("seed") is not None else {},
            world=world,
            detail=detail,
            acts=acts,
            gate=dict(job.get("gate") or {}),
            provider=str(job.get("provider") or "mock"),
            scenario_dir=str(job.get("scenario_dir") or ""),
            created_at=str(job.get("created_at") or ""),
            title=str(job.get("title") or world.get("title") or ""),
            players=dict(job.get("players") or {
                "min": len(detail.get("characters") or []) or 4,
                "max": len(detail.get("characters") or []) or 4,
            }),
            genre=list(job.get("genre") or ([world.get("genre")] if world.get("genre") else [])),
            duration_minutes=job.get("duration_minutes"),
            difficulty=str(job.get("difficulty") or ""),
            truth=dict(job.get("truth") or {
                "culprit": (detail.get("culprit") or {}).get("id") or (detail.get("culprit") or {}).get("character"),
                "victim": (detail.get("victim") or {}).get("id") or (detail.get("victim") or {}).get("character"),
                "method": (detail.get("culprit") or {}).get("method"),
                "motive": (detail.get("culprit") or {}).get("motive"),
            }),
            characters=list(job.get("characters") or detail.get("characters") or []),
            locations=list(job.get("locations") or world.get("locations") or []),
            timeline=list(job.get("timeline") or world.get("timeline") or detail.get("timeline") or []),
            clues=list(job.get("clues") or detail.get("clues") or []),
            scenes=list(job.get("scenes") or acts.get("acts") or []),
            endings=list(job.get("endings") or detail.get("endings") or []),
            rules=dict(job.get("rules") or {}),
            memories=dict(job.get("memories") or detail.get("memories") or {}),
            knowledge_cards=list(job.get("knowledge_cards") or detail.get("knowledge_cards") or []),
            hotfeed=list(job.get("hotfeed") or detail.get("hotfeed") or []),
            assets=dict(job.get("assets") or {}),
            compile=dict(job.get("compile") or {}),
            modules=dict(job.get("modules") or {}),
            staged=job.get("staged"),
            generation=generation,
            agents=dict(_public_metadata(job.get("agents") or {})),
            locks=dict(_public_metadata(job.get("locks") or {})),
            provenance=dict(_public_metadata(job.get("provenance") or {})),
            validation=dict(validation),
        )

    def to_legacy_job(self) -> dict[str, Any]:
        """导出可被现有 studio/server 消费的 job，同时附加公开 IR 元数据。"""
        generation = self.generation
        generation_dict = (
            generation.to_dict() if isinstance(generation, GenerationState)
            else dict(generation or {})
        )
        return {
            # 旧 job 契约：只增不改。
            "id": self.id,
            "status": self.status,
            "tier": self.tier,
            "seed": self.seed,
            "world": self.world,
            "detail": self.detail,
            "acts": self.acts,
            "gate": self.gate,
            "provider": self.provider,
            "scenario_dir": self.scenario_dir,
            "created_at": self.created_at,
            # ScriptPackage IR 投影。
            "ir_version": self.ir_version,
            "package_id": self.package_id,
            "title": self.title or ((self.world or {}).get("title") if isinstance(self.world, Mapping) else ""),
            "players": self.players,
            "genre": self.genre,
            "duration_minutes": self.duration_minutes,
            "difficulty": self.difficulty,
            "truth": self.truth,
            "characters": self.characters,
            "locations": self.locations,
            "timeline": self.timeline,
            "clues": self.clues,
            "scenes": self.scenes,
            "endings": self.endings,
            "rules": self.rules,
            "memories": self.memories,
            "knowledge_cards": self.knowledge_cards,
            "hotfeed": self.hotfeed,
            "assets": self.assets,
            "compile": self.compile,
            "modules": self.modules,
            "staged": self.staged,
            "generation": generation_dict,
            "agents": _public_metadata(self.agents),
            "locks": _public_metadata(self.locks),
            "provenance": _public_metadata(self.provenance),
            "validation": _public_metadata(self.validation),
        }


__all__ = [
    "Diagnostic", "GenerationState", "IR_VERSION", "ScriptPackage", "STAGE_NAMES",
    "STAGE_STATUSES", "StageState", "stable_hash",
]
