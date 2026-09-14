# tests（G 测试组管辖）

测试矩阵（对应 docs/CONTRACTS.md §四验收）：

1. **引擎单测**：stage_machine 三幕流转 / evidence_chain 发卡与合成与伪造 / timeline 一致性 / resolver 行动力与 8 结局矩阵（含 boss_layer、指认 DM 分支）/ memory_system 双层与篡改点 / opinion_feed 热度与辟谣校验 / knowledge_cards 抽卡与心病匹配与诊室结算 / party 阵营分配器 / difficulty 动态难度；
2. **schema 校验**：D 产出的全部 JSON 对照 schemas/ 校验（另含跨文件引用完整性独立复跑）；
3. **端到端**：单人 8 NPC 三幕全流程一局脚本（含 boss 触发链 5 破绽 → 指认 DM → 终极结局）+ 服务重启回放确定性 + 负路径；
4. **平衡性**：阵营胜率模拟（污染/求真 45-55%）、知识开导收益曲线；
5. **API 降级演练**：直答 429/超时 → 兜底文案生效；热榜失败 → 每日挑战灰化；
6. **增量（GAMEPLAY_V31 §九 G）**：party 多人端到端（test_party_e2e.py）、P1 环节单测（test_p1_segments.py）、报告与成就判定（test_report_achievements.py）、D 资产增量校验（test_d_assets_increment.py）。

运行：

```bash
cd game
python -m pytest tests/ -v                 # 全量（约 5s，零 AI、零网络）
python -m pytest tests/ -m "e2e" -v        # 按标记过滤
```

标记：engine / schema / e2e / balance / degradation / party / p1 / achievements / assets。
环境：venv `C:\Users\Administrator\.workbuddy\binaries\python\envs\default`（fastapi/httpx/pytest/pytest-asyncio）。
交付状态与发现清单（Issue 分级 / 平衡数据 / 可行性矩阵）：见 tests/STATUS.md。
