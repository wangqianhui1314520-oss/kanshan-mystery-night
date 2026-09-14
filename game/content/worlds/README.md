# 世界观知识库（RAG 素材）

> 用途：存放盐言 IP 世界观的设定素材，供 NPC/DM Agent 检索，防止 AI 编造设定。
> 建议格式：Markdown 分片，每片 ≤ 500 字，便于向量化。

## 目录约定

```
worlds/
├── {world_id}/                  # 每个世界观一个目录（如 wucheng/ 雾城）
│   ├── world_overview.md        # 世界观总览（时代、地理、基调）
│   ├── characters.md            # 重要角色档案（含 NPC 背景）
│   ├── locations.md             # 地点设定（场景描述素材）
│   ├── factions.md              # 势力/派系关系
│   └── timeline_history.md      # 事件史（案件背景）
```

## 使用方式

1. 将盐言小说关键设定按上述模板拆片
2. 向量化入库（如 Chroma/LanceDB），检索 top-k 注入 Agent 上下文
3. 一致性守卫用本库校验 AI 输出中出现的设定名词

## 注意

- 只收录"可公开"的设定；真相/凶手信息放剧本目录（scenarios/），不放世界观库，避免泄密检索
- 与剧本冲突的旧设定以剧本为准，并在文件中标注
