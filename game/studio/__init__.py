"""剧本杀一键工作台。认约 docs/STUDIO_WORKBENCH.md。

分层：
  catalog     本型 / 机制 / 阵营目录
  brief       normalize / compose / apply
  casebook    钩子 → 圣经（lexicon / extract / narrative）
  mock_bible  无 LLM 入口，转 casebook.build
  llm_steps   有 LLM 时写中间稿，失败回退 mock
  compiler    圣经 → 引擎目录（零 LLM）
  validate    闸门
  pipeline    generate / list / load
  snapshot    /public 水合
"""

from .ids import make_scenario_id
from .paths import scenario_dir
from .brief import apply_brief, compose_seed, normalize_brief
from .pipeline import compile_bibles_and_gate as compile_bibles
from .pipeline import generate, list_book_covers, list_jobs, load_job, load_player_book
from .pipeline import public_of as public_snapshot
from .tiers import PRESET_SEEDS, TIERS
from .validate import validate_dir
from .ir import IR_VERSION, ScriptPackage, stable_hash
from .orchestrator import DEPENDENCIES, GenerationOrchestrator

__all__ = [
    "TIERS",
    "PRESET_SEEDS",
    "generate",
    "load_job",
    "list_jobs",
    "public_snapshot",
    "compile_bibles",
    "validate_dir",
    "make_scenario_id",
    "scenario_dir",
    "normalize_brief",
    "compose_seed",
    "apply_brief",
    "load_player_book",
    "list_book_covers",
]
