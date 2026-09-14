# kanshan 剧本资产（D 内容组管辖）

《求真档案局 · 看山失踪夜》正式剧本目录。产出清单与格式见 `docs/CONTRACTS.md` §三，
剧情改编依据 `docs/STORY_ADAPTATION.md`（盐言三作缝合）、`docs/KNOWLEDGE_SYSTEM.md`（10 知识卡）、
`docs/DM_BOSS_DESIGN.md`（双层真相与 5 破绽）。

## 需产出

```
scenario.json          剧本元数据：3 幕 / 11 地点 / 模式（main/daily/quick）
truth.json             真相三层：表层（水军头子+芯片编辑者）/ 里层（看山设局）/ 伏笔链 flaw_1..5
timeline.json          案发夜全员行动轨迹（NPC 叙述必须一致）
characters/            8 张角色卡（schemas/character.example.json 格式，含 heartache 绑定）
memory/                8 角色记忆版本 V1-V3（双层 said/heart + 删除段，schemas/memory_version）
clues/                 32 条线索卡（含伪造 6 + boss_flaw 5，schemas/clue）
knowledge_cards/       10 张知识卡（schemas/knowledge_card，作者署名必填）
hotfeed/               40+ 热搜帖（schemas/hot_post，含水军帖与辟谣目标帖）
scripts/               三幕剧本文本 + 系统提示音台词 + 开导/诊室演出版式 + 署名表
```

## 素材源

- 官方正文（只读）：`content/worlds/yanyan_sources/`（盐言 4 + 知乎知识 10，含作者）
- 立绘/场景（已生成）：`content/assets/images/`（8 角色 + 9 场景，命名与角色卡 avatar 对应）

## 署名铁律

所有引用盐言/知识内容的位置，复盘页与开场页按 STORY_ADAPTATION.md §署名与合规 输出作者署名。
