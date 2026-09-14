# 五层技术架构

> 对应 README 的目录结构。核心原则：规则引擎与 AI 分离、骨架 + AI 填充、多 Agent 分工。

## 分层

| 层 | 目录 | 职责 | 技术要点 |
|---|---|---|---|
| L5 交互层 | `frontend/` | 对话、搜证、角色面板、地图、房间 | WebSocket 实时；单页 HTML |
| L4 规则引擎 | `engine/` | 阶段状态机、证据链、时间线、裁决 | 确定性代码，无 AI |
| L3 AI Agent | `agents/` | DM 仲裁、NPC 扮演、推理裁判、一致性守卫 | 多 Agent + 提示词模板 |
| L2 内容知识 | `content/` | 剧本资产、世界观 RAG、素材 | 剧本 = 目录；schema 驱动 |
| L1 基础设施 | `server/` | 通信、API 网关、持久化、评测 | 知乎 API 限额缓存 |

## 一次搜证请求的完整链路

```
玩家（L5 点击搜证）
  → server 校验阶段/行动力（L4 规则引擎）
  → 证据链系统按条件从线索池发卡（L4）
  → DM Agent 生成场景反馈、NPC Agent 生成对应反应（L3）
  → 世界观 RAG 补充设定细节（L2）
  → 一致性守卫校验输出（L3）
  → 结果推送前端渲染（L5）→ 状态持久化（L1）
```

## 模块接口约定（骨架阶段）

- `engine/stage_machine.py`：`StageMachine.advance()`, `StageMachine.can(stage, action)`
- `engine/evidence_chain.py`：`EvidenceChain.release(clue_id, player)`, `EvidenceChain.check_contradiction(npc_statement)`
- `engine/timeline.py`：`Timeline.query(character, time_range)`, `Timeline.verify(statement)`
- `engine/resolver.py`：`Resolver.resolve_action()`, `Resolver.calc_ending(judge_result)`
- `agents/*.py`：`Agent.respond(context) -> str/JSON`

## 降级策略

- 知乎 API 限流 → 网关缓存最近回答，超时返回预写剧情兜底
- Agent 调用失败 → 规则引擎继续跑流程，AI 回复降级为模板文本
- 一致性守卫冲突 → 拒绝该输出，要求 Agent 重生成一次
