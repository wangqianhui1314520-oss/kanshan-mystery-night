"""agents — C Agent 组（DM / NPC / Judge / 一致性守卫 / llm_client / prompts）。

契约：docs/CONTRACTS.md §二 C。集成示例：
    from agents import LLMClient, DMAgent, NPCAgent, JudgeAgent, ConsistencyGuard
    llm = LLMClient()
    dm = DMAgent(llm)
"""
from .consistency_guard import ConsistencyGuard
from .dm_agent import DMAgent
from .judge_agent import JudgeAgent
from .llm_client import (DailyBudget, LLMCache, LLMClient, MockProvider,
                         OpenAICompatProvider, Provider, ZhidaProvider,
                         call_gateway, fallback_text, get_client,
                         read_prompt, render_template)
from .npc_agent import NPCAgent
from .segments_lib import SegmentsLibrary
from .showtime import ShowtimeDirector
from .agent_state import AgentState, rank_actions, validate_action

__all__ = [
    "ConsistencyGuard", "DMAgent", "JudgeAgent", "NPCAgent",
    "DailyBudget", "LLMCache", "LLMClient", "MockProvider",
    "OpenAICompatProvider", "Provider", "ZhidaProvider",
    "call_gateway", "fallback_text", "get_client", "read_prompt", "render_template",
    "SegmentsLibrary", "ShowtimeDirector",
    "AgentState", "rank_actions", "validate_action",
]
