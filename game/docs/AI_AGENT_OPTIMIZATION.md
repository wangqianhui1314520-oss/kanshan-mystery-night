# AI 智能体优化落地说明

## 已落地

- `agents/agent_state.py`：统一 AgentState、行动力、目标、信念、关系、压力和最近动作。
- `rank_actions()`：按阶段目标、提示偏好、重复惩罚和证据条件进行确定性动作排序。
- `validate_action()`：LLM 与启发式动作共用协议校验，拦截空台词、缺地点、缺卡牌和证据不足投票。
- `PlayerAgent`：LLM 输出先经过动作校验，失败自动回退本地规划器；每次决策记录最近动作，减少循环行为。
- `engine_driver.py`：服务端再次拒绝少于两张证据卡的投票，并校验证据属于当前玩家。

## 接入约定

Agent 只提交动作意图；剧情事实、资源消耗、门控和结局必须由 Engine 裁决。新增 Agent 时应调用 `AgentState.from_dict()`、`rank_actions()` 和 `validate_action()`，不要在 prompt 中复制引擎规则。

## 后续数据字段

NPC 可逐步补充 `goals`、`beliefs`、`relations`、`stress` 和 `recent_actions`，这些字段只影响行动偏好和台词语气，不得直接改变证据或结局。
