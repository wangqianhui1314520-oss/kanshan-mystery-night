# 《求真档案局 · 看山失踪夜》· AI 原生欢乐阵营机制推理本

> 知乎黑客松 2026 校园新锐季 · 跨次元游乐场（AI 游戏与互动叙事）
> 玩家不读本，通过与 AI 角色对话、搜证、记忆修复、舆论博弈、知识开导，逐步还原双层真相——而 DM 刘看山，是最大的隐藏 Boss。

> V4 优化路线：首局采用 5 人 + AI 补位的 60 分钟欢乐垂直切片，加入三层角色目标、欢乐值、阵营技能和 AI 对话结构化事件。详见 [docs/OPTIMIZATION_ROADMAP.md](docs/OPTIMIZATION_ROADMAP.md)。

## 文档索引（按阅读顺序）

| 文档 | 内容 |
|---|---|
| [docs/GAME_DESIGN_V3.md](docs/GAME_DESIGN_V3.md) | 总设计：三幕框架、搜证详设、七个欢乐源、规模总表 |
| [docs/STORY_ADAPTATION.md](docs/STORY_ADAPTATION.md) | 官方素材改编：盐言三作缝合三幕 + 署名规范 |
| [docs/KNOWLEDGE_SYSTEM.md](docs/KNOWLEDGE_SYSTEM.md) | 知识卡系统：10 篇知乎知识 → 心病开导/辟谣弹药/心晴诊室 |
| [docs/DM_BOSS_DESIGN.md](docs/DM_BOSS_DESIGN.md) | 看山=DM=隐藏 Boss：双层真相、5 破绽伏笔链、终极结局 |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | **多窗口并发契约**：目录所有权、schema、事件协议、分工简报 |
| [docs/ASSETS_INVENTORY.md](docs/ASSETS_INVENTORY.md) | 官方素材清单与额度实测 |
| [docs/HACKATHON_CHECKLIST.md](docs/HACKATHON_CHECKLIST.md) | 赛程红线与提交检查 |
| docs/GAME_DESIGN.md / SCRIPT_TYPES.md / ARCHITECTURE.md | V1 时代文档，仅作流程规范参考 |

## 架构三铁律（不可动）

1. **规则引擎与 AI 分离**：阶段、线索、结局由 `engine/` 确定性代码裁决；AI 只生成对话与叙事；
2. **骨架 + AI 填充**：`content/` 是人工预置的确定性骨架，AI 在骨架内自由发挥；
3. **多 Agent 分工**：DM（看山系统音）/ NPC / Judge / 一致性守卫各司其职。

## 目录速览

```
game/
├── docs/          设计文档（A 窗口维护）
├── schemas/       权威 schema 示例（各窗口只读引用）
├── engine/        规则引擎：状态机/证据链/时间线/裁决/记忆(心声双层)/舆论场/知识卡
├── agents/        AI 层：DM/NPC/Judge/守卫 + LLM Provider 抽象 + 提示词
├── content/       剧本资产：scenarios/kanshan（本案）+ worlds/yanyan_sources（官方源文本）
├── frontend/      Vue3 + WebSocket 事件驱动客户端
├── server/        FastAPI + 房间 WS + 知乎网关（缓存/节流/降级）
├── tools/         资产生成管线（asset_gen.py：Agnes 图/视频）+ .env（不入库）
└── tests/         单测 + 端到端 + 平衡性
```

## 多窗口开发（谁该看什么）

开新窗口时，把 `docs/CONTRACTS.md` 第二节该窗口的「任务简报」整段粘进去即可。铁律：**每个窗口只写自己管辖目录，跨模块只走 schemas/ 与 WS 事件协议。**

## 快速开始（集成后）

```bash
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8899     # 后端
# 浏览器访问 http://127.0.0.1:8899/（不要直接双击 frontend/index.html）
```

前端图片、视频和音频统一使用 `/assets/...` 绝对路径，由 FastAPI 将它映射到
`game/content/assets/`。直接用 `file://` 打开 `frontend/index.html`，或只把
`frontend/` 目录作为静态根目录时，浏览器会请求错误的 `/assets` 地址，因此会出现
“界面能打开但美术资产全部 404”的情况。
